"""Document processor interface for document processing pipelines.

This module defines the DocumentProcessor protocol that all document processors
must conform to. The functional pipeline approach uses plain functions that
yield document dictionaries.
"""

from collections.abc import Callable, Iterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class DocumentProcessor(Protocol):
    """Protocol defining the interface for document processors.

    A document processor is a callable (function) that generates documents
    for Meilisearch indexing. All processors must accept limit and on_error
    parameters and yield document dictionaries.

    Example:
        def my_processor(limit=None, on_error=None) -> Iterator[dict]:
            for doc in ...:
                yield doc
    """

    def __call__(
        self,
        limit: int | None = None,
        on_error: Callable[[str, str], None] | None = None,
    ) -> Iterator[dict]:
        """Generate documents ready for Meilisearch indexing.

        Args:
            limit: Maximum number of source items to process (not chunks)
            on_error: Optional callback called with (file_identifier, error_msg)
                     for each error. file_identifier should be a unique string
                     identifying the source (file_name, doc_id, etc.)

        Yields:
            Dictionary with document structure:
            {
                "id": str,           # Unique document ID
                "index_code": str,   # Index identifier (e.g., "AP", "LS")
                "file_name": str,    # Original file name
                "chunk_id": int,     # Chunk index within the file
                "__discussions": str, # Text content of this chunk
                **metadata           # Normalized metadata fields
            }
        """
        ...
