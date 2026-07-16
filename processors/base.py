"""Base processor interface for document processing pipelines."""

from abc import ABC, abstractmethod
from typing import Optional, Iterator

import meilisearch


class BaseProcessor(ABC):
    """Abstract base class for state-specific document processors.

    A processor is responsible for:
    1. Loading/fetching raw documents
    2. Extracting and normalizing metadata
    3. Extracting/processing text content
    4. Chunking text into Meilisearch-ready documents

    All processors yield documents with the same structure:
    {
        "id": str,           # Unique document ID
        "state_code": str,   # State identifier (e.g., "AP", "LS")
        "file_name": str,    # Original file name
        "chunk_id": int,     # Chunk index within the file
        "__discussions": str, # Text content of this chunk
        **metadata           # Normalized metadata fields
    }
    """

    def __init__(self, state_code: str, config: dict, ms_client: meilisearch.Client):
        """Initialize the processor.

        Args:
            state_code: Two-letter state code (e.g., "AP", "LS")
            config: Full configuration dictionary from YAML
            ms_client: Meilisearch client instance
        """
        self.state_code = state_code
        self.config = config
        self.ms_client = ms_client
        self.state_config = self._get_state_config()

    def _get_state_config(self) -> dict:
        """Get state-specific config with fallback to global defaults."""
        state_cfg = self.config.get("index_config", {}).get(self.state_code, {})
        global_cfg = self.config.get("index_config", {}).get("global", {})
        # State config overrides global
        return {**global_cfg, **state_cfg}

    @abstractmethod
    def get_documents(self, limit: Optional[int] = None) -> Iterator[dict]:
        """Generate documents ready for Meilisearch indexing.

        Args:
            limit: Maximum number of source items to process (not chunks)

        Yields:
            Dictionary with document structure as described in class docstring.
        """
        pass

    def get_chunk_config(self) -> dict:
        """Get chunking configuration for this state."""
        return self.state_config.get("chunking", {})
