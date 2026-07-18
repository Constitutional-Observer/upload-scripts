"""Base processor interface for document processing pipelines."""

from abc import ABC, abstractmethod
from typing import Callable, Optional, Iterator


class BaseProcessor(ABC):
    """Abstract base class for index-specific document processors.

    A processor is responsible for:
    1. Loading/fetching raw documents
    2. Extracting and normalizing metadata
    3. Extracting/processing text content
    4. Chunking text into Meilisearch-ready documents

    All processors yield documents with the same structure:
    {
        "id": str,           # Unique document ID
        "index_code": str,   # Index identifier (e.g., "AP", "LS", "PARIVESH")
        "file_name": str,    # Original file name
        "chunk_id": int,     # Chunk index within the file
        "__discussions": str, # Text content of this chunk
        **metadata           # Normalized metadata fields
    }
    """

    def __init__(self, index_code: str, config: dict):
        """Initialize the processor.

        Args:
            index_code: Index code (e.g., "AP", "LS", "PARIVESH")
            config: Full configuration dictionary from YAML
        """
        self.index_code = index_code
        self.config = config
        self.index_code_config = self._get_index_code_config()

    def _get_index_code_config(self) -> dict:
        """Get index_code-specific config with fallback to global defaults."""
        index_code_cfg = self.config.get("index_config", {}).get(self.index_code, {})
        global_cfg = self.config.get("index_config", {}).get("global", {})
        # Index_code config overrides global
        return {**global_cfg, **index_code_cfg}

    @abstractmethod
    def get_documents(
        self,
        limit: Optional[int] = None,
        on_error: Optional[Callable[[str, str], None]] = None,
    ) -> Iterator[dict]:
        """Generate documents ready for Meilisearch indexing.

        Args:
            limit: Maximum number of source items to process (not chunks)
            on_error: Optional callback called with (file, error_msg) for each error

        Yields:
            Dictionary with document structure as described in class docstring.
        """
        pass

    def get_chunk_config(self) -> dict:
        """Get chunking configuration for this index_code."""
        return self.index_code_config.get("chunking", {})
