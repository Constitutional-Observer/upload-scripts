"""Functional pipeline for document processing.

This module implements a functional approach to the document processing pipeline
with explicit inputs and dependency order, split into:
- Preprocessing: fetch -> extract_text -> chunk
- Postprocessing: configurable steps -> format_document

Each stage has explicit function signatures with typed parameters,
making the data flow clear and composable.
"""

import json
import logging
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from metadata_handler import normalize_metadata

if TYPE_CHECKING:
    from .postprocessing import PostprocessConfig, StepRegistry

logger = logging.getLogger(__name__)


# =============================================================================
# Type Definitions
# =============================================================================


@dataclass
class FetchResult:
    """Result of fetching a document."""

    path: Path
    file_name: str
    metadata: dict


@dataclass
class ExtractResult:
    """Result of extracting text from a document."""

    text: str
    file_name: str
    metadata: dict


@dataclass
class ChunkResult:
    """Result of chunking text."""

    chunks: list[str]
    file_name: str
    metadata: dict


@dataclass
class NerResult:
    """Result of NER processing on a chunk."""

    chunk: str
    entities: list[dict]
    file_name: str
    chunk_id: int
    metadata: dict


@dataclass
class Document:
    """Final document ready for indexing.

    Note: __discussions is stored as a regular field but accessible with the
    double underscore prefix for compatibility with Meilisearch.
    """

    id: str
    index_code: str
    file_name: str
    chunk_id: int
    metadata: dict
    entities: list[dict] = field(default_factory=list)
    discussions: str = ""

    @property
    def __discussions(self) -> str:
        """Access discussions with double underscore for Meilisearch compatibility."""
        return self.discussions

    @__discussions.setter
    def __discussions(self, value: str):
        """Set discussions with double underscore."""
        self.discussions = value

    def to_dict(self) -> dict:
        """Convert document to dictionary for Meilisearch indexing.

        Returns:
            Dictionary with all document fields, including __discussions.
        """
        result = {
            "id": self.id,
            "index_code": self.index_code,
            "file_name": self.file_name,
            "chunk_id": self.chunk_id,
            "__discussions": self.discussions,
            "entities": self.entities,
        }
        # Add all metadata fields
        result.update(self.metadata)

        # Add any additional attributes that were set via setattr (from postprocessing steps)
        # These are fields like _ner or any custom step output fields
        standard_fields = {
            "id",
            "index_code",
            "file_name",
            "chunk_id",
            "discussions",
            "entities",
            "metadata",
            "__discussions",
        }
        for key, value in self.__dict__.items():
            if key not in standard_fields and not key.startswith("_"):
                result[key] = value

        return result


# =============================================================================
# Configuration Types
# =============================================================================


@dataclass
class ChunkConfig:
    """Configuration for chunking."""

    max_chunk_len: int = 200


@dataclass
class FetchConfig:
    """Configuration for fetching."""

    files_path: Path = None
    metadata_path: Path = None
    file_resolver: Callable[[str, dict], Path] | None = None


@dataclass
class PipelineConfig:
    """Full pipeline configuration."""

    index_code: str
    chunk_config: ChunkConfig = None
    fetch_config: FetchConfig = None
    run_ner: bool = False
    extractor: str = "text"


# =============================================================================
# Stage 0: Metadata Normalization (always first)
# =============================================================================


def normalize_metadata_stage(index_code: str, raw_metadata: dict) -> dict:
    """Normalize metadata using the existing handler.

    Args:
        index_code: The index code (e.g., "AP", "KA")
        raw_metadata: Raw metadata dictionary from source

    Returns:
        Normalized metadata dictionary
    """
    return normalize_metadata(index_code, raw_metadata)


# =============================================================================
# Preprocessing Stages
# =============================================================================

# --- Stage 1: Fetch ---


def fetch_from_filesystem(
    files_path: Path, metadata_path: Path, file_name: str, raw_metadata: dict
) -> FetchResult:
    """Fetch a document from the filesystem.

    Args:
        files_path: Path to directory containing text files
        metadata_path: Path to metadata JSONL file
        file_name: Name of the file to fetch
        raw_metadata: Raw metadata for this file

    Returns:
        FetchResult with path, file_name, and metadata
    """
    document_path = files_path / file_name
    if not document_path.exists():
        raise FileNotFoundError(f"Text file not found: {document_path}")

    return FetchResult(path=document_path, file_name=file_name, metadata=raw_metadata)


def fetch_stage(
    index_code: str, fetch_config: FetchConfig, file_name: str, raw_metadata: dict
) -> FetchResult:
    """Fetch stage - dispatches to appropriate fetch method.

    Supports both filesystem and custom file resolvers (e.g., API-based fetching).

    Args:
        index_code: The index code
        fetch_config: Configuration for fetching (includes optional file_resolver)
        file_name: Name of the file to fetch
        raw_metadata: Raw metadata for this file

    Returns:
        FetchResult with the document path and metadata
    """
    if fetch_config.file_resolver:
        document_path = fetch_config.file_resolver(file_name, raw_metadata)
    else:
        document_path = fetch_config.files_path / file_name

    if not document_path.exists():
        raise FileNotFoundError(f"Text file not found: {document_path}")

    return FetchResult(path=document_path, file_name=file_name, metadata=raw_metadata)


# --- Stage 2: Extract Text ---


def read_text_from_path(path: Path) -> str:
    """Read text from a plain text file path.

    Args:
        path: Path to the text file

    Returns:
        Text content of the file
    """
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def extract_text_from_pdf(path: Path) -> str:
    """Extract text from PDF using pymupdf.

    Args:
        path: Path to the PDF file

    Returns:
        Extracted text content
    """
    import fitz

    doc = fitz.open(path)
    return "\n".join([page.get_text() for page in doc])


def extract_text_from_ocr(path: Path) -> str:
    """OCR a document from path.

    Placeholder for OCR implementation.
    In practice, this would call an OCR library like pytesseract, easyocr, etc.

    Args:
        path: Path to the document (PDF, image, etc.)

    Returns:
        Extracted text
    """
    # Placeholder - actual OCR implementation goes here
    raise NotImplementedError(f"OCR extraction not implemented for {path}")


# Static mapping of extractor names to functions
EXTRACTOR_MAP: dict[str, Callable[[Path], str]] = {
    "text": read_text_from_path,
    "pymupdf": extract_text_from_pdf,
    "ocr": extract_text_from_ocr,
}


def extract_text_stage(
    fetch_result: FetchResult, extractor: str = "text"
) -> ExtractResult:
    """Extract text from a fetched document using the configured extractor.

    Uses the statically configured extractor. No file type detection or fallback.

    Args:
        fetch_result: Result from fetch stage
        extractor: Name of extractor to use - "text", "pymupdf", or "ocr"

    Returns:
        ExtractResult with extracted text, file_name, and metadata
    """
    extract_func = EXTRACTOR_MAP[extractor]
    text = extract_func(fetch_result.path)
    return ExtractResult(
        text=text, file_name=fetch_result.file_name, metadata=fetch_result.metadata
    )


# --- Stage 3: Chunk ---


def chunk_text(text: str, max_chunk_len: int = 200) -> list[str]:
    """Split text into chunks by double newlines, respecting word count limits.

    Args:
        text: The text to chunk
        max_chunk_len: Maximum word count per chunk (default: 200)

    Returns:
        List of text chunks
    """
    current_chunk = ""
    current_chunk_word_count = 0
    chunks = []

    # Split on double newlines, preserving empty paragraphs for now
    raw_split_file = re.split(r"\n\n", text)

    for raw_split in raw_split_file:
        # Skip completely empty paragraphs (only whitespace)
        if not raw_split.strip():
            continue

        # Count words using regex that handles all Unicode whitespace
        words = re.split(r"\s+", raw_split.strip())
        raw_split_word_count = len(words)

        if raw_split_word_count + current_chunk_word_count > max_chunk_len:
            # Start new chunk if current one would exceed limit
            if current_chunk:  # Only add if we have content
                chunks.append(current_chunk)
            current_chunk = raw_split
            current_chunk_word_count = raw_split_word_count
        else:
            # Add to current chunk
            if current_chunk:
                current_chunk += "\n\n" + raw_split
            else:
                current_chunk = raw_split
            current_chunk_word_count += raw_split_word_count

    # Add final chunk if it has content
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def chunk_stage(
    extract_result: ExtractResult, chunk_config: ChunkConfig = None
) -> ChunkResult:
    """Chunk extracted text into manageable pieces.

    Args:
        extract_result: Result from extract_text stage
        chunk_config: Configuration for chunking (default: max_chunk_len=200)

    Returns:
        ChunkResult with list of chunks, file_name, and metadata
    """
    if chunk_config is None:
        chunk_config = ChunkConfig()

    chunks = chunk_text(extract_result.text, max_chunk_len=chunk_config.max_chunk_len)

    return ChunkResult(
        chunks=chunks,
        file_name=extract_result.file_name,
        metadata=extract_result.metadata,
    )


# =============================================================================
# Preprocessing Pipeline Orchestration
# =============================================================================


def run_preprocessing(
    index_code: str,
    fetch_config: FetchConfig,
    file_name: str,
    raw_metadata: dict,
    chunk_config: ChunkConfig = None,
    extractor: str = "text",
) -> ChunkResult:
    """Run the complete preprocessing pipeline: normalize -> fetch -> extract -> chunk.

    Args:
        index_code: The index code (e.g., "AP", "KA")
        fetch_config: Configuration for fetching
        file_name: Name of the file to process
        raw_metadata: Raw metadata for the file
        chunk_config: Configuration for chunking (default: max_chunk_len=200)
        extractor: Name of text extractor to use - "text", "pymupdf", or "ocr"

    Returns:
        ChunkResult with chunks ready for postprocessing
    """
    # Stage 0: Normalize metadata
    normalized_metadata = normalize_metadata_stage(index_code, raw_metadata)

    # Stage 1: Fetch
    fetch_result = fetch_stage(index_code, fetch_config, file_name, normalized_metadata)

    # Stage 2: Extract text
    extract_result = extract_text_stage(fetch_result, extractor=extractor)

    # Stage 3: Chunk
    chunk_result = chunk_stage(extract_result, chunk_config)

    return chunk_result


# =============================================================================
# Postprocessing Stages
# =============================================================================

# --- Stage 4: NER ---


def add_ner_stage(
    chunk: str, file_name: str, chunk_id: int, metadata: dict
) -> NerResult:
    """Add Named Entity Recognition to a chunk.

    This is a placeholder that can be extended to use actual NER models.
    For now, it returns an empty list of entities.

    Args:
        chunk: The text chunk to process
        file_name: Original file name
        chunk_id: Chunk index within the file
        metadata: Normalized metadata

    Returns:
        NerResult with chunk, extracted entities, and metadata
    """
    # Placeholder: In a real implementation, this would call an NER model
    # For example: spaCy, transformers, or a custom model
    entities = []  # List of dicts with entity info: {"text": ..., "label": ..., "start": ..., "end": ...}

    logger.info(f"NER placeholder - no entities extracted for {file_name}:{chunk_id}")

    return NerResult(
        chunk=chunk,
        entities=entities,
        file_name=file_name,
        chunk_id=chunk_id,
        metadata=metadata,
    )


# --- Stage 5: Format Document ---


def format_document_stage(
    ner_result: NerResult | None,
    index_code: str,
    chunk: str,
    file_name: str,
    chunk_id: int,
    metadata: dict,
    **extra_fields,
) -> Document:
    """Format a chunk into a final document ready for indexing.

    Args:
        ner_result: Optional result from NER stage (if NER was run) - for backward compat
        index_code: The index code
        chunk: The text chunk
        file_name: Original file name
        chunk_id: Chunk index within the file
        metadata: Normalized metadata
        **extra_fields: Additional fields from postprocessing steps (e.g., entities)

    Returns:
        Document ready for Meilisearch indexing
    """
    # Extract entities from NER result if available (backward compatibility)
    entities = []
    if ner_result is not None:
        entities = ner_result.entities

    # Override with entities from extra_fields if provided
    if "entities" in extra_fields:
        entities = extra_fields.pop("entities")

    # Create document ID
    doc_id = f"{index_code}_{file_name.replace('.', '_')}_{chunk_id}"

    # Build initial document
    doc = Document(
        id=doc_id,
        index_code=index_code,
        file_name=file_name,
        chunk_id=chunk_id,
        discussions=chunk,
        metadata=metadata,
        entities=entities,
    )

    # Add any additional fields from postprocessing steps
    # These will be added as attributes to the Document
    for key, value in extra_fields.items():
        setattr(doc, key, value)

    return doc


# =============================================================================
# Postprocessing Pipeline Orchestration
# =============================================================================


def run_postprocessing(
    chunk_result: ChunkResult,
    index_code: str,
    run_ner: bool = False,
    postprocess_config: PostprocessConfig | None = None,
    step_registry: StepRegistry | None = None,
) -> Iterator[Document]:
    """Run the complete postprocessing pipeline: configurable steps -> format.

    Args:
        chunk_result: Result from preprocessing (ChunkResult)
        index_code: The index code
        run_ner: Whether to run NER stage (default: False) - for backward compatibility
        postprocess_config: Configuration for postprocessing steps (optional)
        step_registry: Registry of available postprocessing steps (optional)

    Yields:
        Document objects ready for indexing
    """
    file_name = chunk_result.file_name
    metadata = chunk_result.metadata

    for chunk_id, chunk in enumerate(chunk_result.chunks):
        # Collect results from all postprocessing steps
        step_results: dict = {}

        # Backward compatibility: run old NER if requested
        if run_ner:
            ner_result = add_ner_stage(
                chunk=chunk, file_name=file_name, chunk_id=chunk_id, metadata=metadata
            )
            step_results["entities"] = ner_result.entities

        # Run configurable postprocessing steps if provided
        if postprocess_config and postprocess_config.enabled:
            from .postprocessing import run_postprocessing_steps

            step_results.update(
                run_postprocessing_steps(
                    chunk=chunk,
                    file_name=file_name,
                    chunk_id=chunk_id,
                    metadata=metadata,
                    config=postprocess_config,
                    registry=step_registry,
                )
            )

        # Stage 5: Format document
        document = format_document_stage(
            ner_result=None,
            index_code=index_code,
            chunk=chunk,
            file_name=file_name,
            chunk_id=chunk_id,
            metadata=metadata,
            **step_results,
        )

        yield document


# =============================================================================
# Full Pipeline
# =============================================================================


def run_full_pipeline(
    index_code: str,
    fetch_config: FetchConfig,
    file_name: str,
    raw_metadata: dict,
    chunk_config: ChunkConfig = None,
    run_ner: bool = False,
    extractor: str = "text",
    postprocess_config: PostprocessConfig | None = None,
    step_registry: StepRegistry | None = None,
) -> Iterator[Document]:
    """Run the complete pipeline: preprocessing + postprocessing.

    This is the main entry point for processing a single file through the entire
    pipeline from raw metadata to final indexed documents.

    Args:
        index_code: The index code (e.g., "AP", "KA")
        fetch_config: Configuration for fetching (files_path, metadata_path)
        file_name: Name of the file to process
        raw_metadata: Raw metadata for the file
        chunk_config: Configuration for chunking (default: max_chunk_len=200)
        run_ner: Whether to run NER stage (default: False) - for backward compatibility
        extractor: Name of text extractor to use - "text", "pymupdf", or "ocr"
        postprocess_config: Configuration for postprocessing steps (optional)
        step_registry: Registry of available postprocessing steps (optional)

    Yields:
        Document objects ready for Meilisearch indexing
    """
    # Run preprocessing
    chunk_result = run_preprocessing(
        index_code=index_code,
        fetch_config=fetch_config,
        file_name=file_name,
        raw_metadata=raw_metadata,
        chunk_config=chunk_config,
        extractor=extractor,
    )

    # Run postprocessing
    yield from run_postprocessing(
        chunk_result=chunk_result,
        index_code=index_code,
        run_ner=run_ner,
        postprocess_config=postprocess_config,
        step_registry=step_registry,
    )


# =============================================================================
# Multi-file Pipeline
# =============================================================================


def load_metadata_items(metadata_path: Path) -> list[dict]:
    """Load metadata items from a JSONL file.

    Args:
        metadata_path: Path to metadata JSONL file

    Returns:
        List of metadata item dictionaries
    """

    if not metadata_path.exists():
        raise FileNotFoundError(f"Metadata file not found: {metadata_path}")

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata_text = f.read()

    return list(map(json.loads, metadata_text.splitlines()))


def find_text_file(files: list[dict]) -> str | None:
    """Find the text file from a list of file entries.

    Looks for files ending with _djvu.txt by default.

    Args:
        files: List of file entry dictionaries with "name" key

    Returns:
        File name if found, None otherwise
    """
    for file in files:
        if file["name"].endswith("_djvu.txt"):
            return file["name"]
    return None


def process_index(
    index_code: str,
    metadata_iterator: Iterator[dict],
    fetch_config: FetchConfig,
    limit: int | None = None,
    chunk_config: ChunkConfig = None,
    run_ner: bool = False,
    extractor: str = "text",
    on_error: Callable[[str, str], None] | None = None,
    postprocess_config: PostprocessConfig | None = None,
    step_registry: StepRegistry | None = None,
) -> Iterator[Document]:
    """Process all files for a given index code.

    This is the main entry point for the functional pipeline. It accepts a
    source-agnostic metadata iterator, making it work with both file-based
    and API-based sources. The fetch_config can include a custom file_resolver
    for non-filesystem sources (e.g., downloading from APIs).

    Args:
        index_code: The index code (e.g., "AP", "KA")
        metadata_iterator: Iterator yielding metadata dicts. Each dict should have
            a "files" key (list of file entries) and "metadata" key (raw metadata).
            For file-based: created from JSONL lines. For API-based: yields from API.
        fetch_config: Configuration for fetching. Use file_resolver for custom
            sources that need to download/locate files differently.
        limit: Maximum number of files to process (default: None = all)
        chunk_config: Configuration for chunking
        run_ner: Whether to run NER (default: False) - for backward compatibility
        extractor: Name of text extractor to use - "text", "pymupdf", or "ocr"
        on_error: Optional callback for errors: (file_identifier, error_msg)
        postprocess_config: Configuration for postprocessing steps (optional)
        step_registry: Registry of available postprocessing steps (optional)

    Yields:
        Document objects ready for Meilisearch indexing
    """

    def report_error(file: str, error_msg: str):
        logger.error(error_msg)
        if on_error:
            on_error(file, error_msg)

    # Process each metadata item from the iterator (streaming-friendly)
    count = 0
    for item in metadata_iterator:
        if limit and count >= limit:
            break

        # Find the text file
        file_name = find_text_file(item.get("files", []))
        if not file_name:
            item_id = item.get("metadata", {}).get("id", "unknown")
            error_msg = (
                f"No _djvu.txt file found in files list for index_code {index_code}, "
                f"item: {item_id}"
            )
            report_error(item_id, error_msg)
            continue

        # Get raw metadata
        raw_metadata = item.get("metadata", {})

        try:
            # Process through full pipeline
            yield from run_full_pipeline(
                index_code=index_code,
                fetch_config=fetch_config,
                file_name=file_name,
                raw_metadata=raw_metadata,
                chunk_config=chunk_config,
                run_ner=run_ner,
                extractor=extractor,
                postprocess_config=postprocess_config,
                step_registry=step_registry,
            )
        except Exception as e:
            error_msg = (
                f"Failed to process file {file_name} for index_code {index_code}: {e}"
            )
            report_error(file_name, error_msg)

        count += 1
