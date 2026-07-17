"""Filesystem-based document processor.

Processes pre-existing debate text files from the filesystem.
This is the default processor for states with files already downloaded.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional, Iterator

from metadata_handler import normalize_metadata
from .base import BaseProcessor

logger = logging.getLogger(__name__)


class FilesystemProcessor(BaseProcessor):
    """Processor for pre-existing files on disk.

    Expects:
    - A metadata JSONL file containing items with "metadata" and "files" fields
    - Text files (default: *_djvu.txt) in the files_path directory

    Each metadata item should have:
    {
        "metadata": {...},  # Raw metadata to be normalized
        "files": [{"name": "..._djvu.txt"}, ...]
    }
    """

    def __init__(
        self,
        state_code: str,
        config: dict,
        files_path: Path,
        metadata_path: Path,
    ):
        """Initialize the filesystem processor.

        Args:
            state_code: State code (e.g., "AP")
            config: Full configuration dictionary
            files_path: Path to directory containing text files
            metadata_path: Path to metadata JSONL file
        """
        super().__init__(state_code, config)
        self.files_path = Path(files_path)
        self.metadata_path = Path(metadata_path)

    def _find_djvu_file(self, files: list[dict]) -> Optional[str]:
        """Find the DJVU text file from a list of file entries."""
        for file in files:
            if file["name"].endswith("_djvu.txt"):
                return file["name"]
        return None

    def _chunk_file(self, file_text: str, chunk_config: dict) -> list[str]:
        """Split file text into chunks by double newlines.

        Args:
            file_text: The text to chunk
            chunk_config: Dictionary with 'max_chunk_len' key

        Returns:
            List of text chunks
        """
        MAX_CHUNK_LEN = chunk_config.get("max_chunk_len", 200)
        current_chunk = ""
        current_chunk_word_count = 0

        # Split on double newlines, preserving empty paragraphs for now
        raw_split_file = re.split(r"\n\n", file_text)
        chunks = []

        for raw_split in raw_split_file:
            # Skip completely empty paragraphs (only whitespace)
            if not raw_split.strip():
                continue

            # Count words using regex that handles all Unicode whitespace
            words = re.split(r"\s+", raw_split.strip())
            raw_split_word_count = len(words)

            if raw_split_word_count + current_chunk_word_count > MAX_CHUNK_LEN:
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

    def _load_metadata(self) -> list[dict]:
        """Load metadata from JSONL file."""
        if not self.metadata_path.exists():
            raise FileNotFoundError(f"Metadata file not found: {self.metadata_path}")

        with open(self.metadata_path, "r", encoding="utf-8") as f:
            metadata_text = f.read()
        return list(map(json.loads, metadata_text.splitlines()))

    def get_documents(self, limit: Optional[int] = None) -> Iterator[dict]:
        """Generate documents from filesystem files.

        Args:
            limit: Maximum number of metadata items to process

        Yields:
            Meilisearch-ready document dictionaries
        """
        metadata = self._load_metadata()

        if limit:
            metadata = metadata[:limit]

        chunk_config = self.get_chunk_config()

        for item in metadata:
            # Find the text file
            file_name = self._find_djvu_file(item.get("files", []))
            if not file_name:
                # Skip items without a DJVU text file
                logger.error(
                    f"No _djvu.txt file found in files list for state {self.state_code}, "
                    f"item: {item.get('metadata', {}).get('id', 'unknown')}"
                )
                continue

            # Normalize metadata using state-specific handler
            try:
                metadata_dict = normalize_metadata(self.state_code, item["metadata"])
            except Exception as e:
                # Log and skip malformed metadata
                logger.error(
                    f"Failed to normalize metadata for state {self.state_code}, "
                    f"file: {file_name}: {e}"
                )
                continue

            # Read the discussion text
            discussion_text_path = self.files_path / file_name
            if not discussion_text_path.exists():
                logger.error(
                    f"Text file not found: {discussion_text_path} "
                    f"(state: {self.state_code})"
                )
                continue

            with open(discussion_text_path, "r", encoding="utf-8") as f:
                discussion_text = f.read()

            # Chunk the text
            file_chunks = self._chunk_file(discussion_text, chunk_config)

            # Yield one document per chunk
            for chunk_id, chunk in enumerate(file_chunks):
                yield {
                    "id": f"{self.state_code}_{file_name.replace('.', '_')}_{chunk_id}",
                    "state_code": self.state_code,
                    "file_name": file_name,
                    "chunk_id": chunk_id,
                    "__discussions": chunk,
                    **metadata_dict,
                }
