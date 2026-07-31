"""Abstract base class for search backends.

This module defines the SearchBackend interface that all concrete search
backend implementations must follow.
"""

from abc import ABC, abstractmethod
from typing import Any


class SearchBackend(ABC):
    """Abstract base class for search backend implementations.

    Concrete implementations must provide actual search backend operations.
    This abstraction allows switching between Meilisearch, Elasticsearch,
    or other search backends with minimal code changes.
    """

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the search backend is healthy and reachable.

        Returns:
            True if the backend is healthy, False otherwise.
        """
        ...

    @abstractmethod
    def get_index(self, index_name: str) -> Any:
        """Get a reference to an index/collection.

        Args:
            index_name: The name of the index/collection.

        Returns:
            A backend-specific index/collection object.
        """
        ...

    @abstractmethod
    def create_index(self, index_name: str) -> bool:
        """Create a new index/collection if it doesn't exist.

        Args:
            index_name: The name of the index/collection to create.

        Returns:
            True if the index was created or already exists, False otherwise.
        """
        ...

    @abstractmethod
    def delete_index(self, index_name: str) -> bool:
        """Delete an index/collection.

        Args:
            index_name: The name of the index/collection to delete.

        Returns:
            True if the index was deleted, False if it didn't exist.
        """
        ...

    @abstractmethod
    def index_exists(self, index_name: str) -> bool:
        """Check if an index/collection exists.

        Args:
            index_name: The name of the index/collection to check.

        Returns:
            True if the index exists, False otherwise.
        """
        ...

    @abstractmethod
    def get_index_info(self, index_name: str) -> dict:
        """Get information about an index/collection.

        Args:
            index_name: The name of the index/collection.

        Returns:
            A dictionary containing index information (settings, stats, etc.).
        """
        ...

    @abstractmethod
    def update_searchable_attributes(
        self, index_name: str, attributes: list[str]
    ) -> bool:
        """Update the searchable attributes for an index.

        Args:
            index_name: The name of the index/collection.
            attributes: List of attribute names that should be searchable.

        Returns:
            True if the update was successful.
        """
        ...

    @abstractmethod
    def update_filterable_attributes(
        self, index_name: str, attributes: list[str]
    ) -> bool:
        """Update the filterable attributes for an index.

        Args:
            index_name: The name of the index/collection.
            attributes: List of attribute names that should be filterable.

        Returns:
            True if the update was successful.
        """
        ...

    @abstractmethod
    def update_sortable_attributes(
        self, index_name: str, attributes: list[str]
    ) -> bool:
        """Update the sortable attributes for an index.

        Args:
            index_name: The name of the index/collection.
            attributes: List of attribute names that should be sortable.

        Returns:
            True if the update was successful.
        """
        ...

    @abstractmethod
    def update_embedders(self, index_name: str, embedders_config: dict) -> bool:
        """Update the embedders configuration for an index.

        Args:
            index_name: The name of the index/collection.
            embedders_config: Dictionary containing embedder configuration.

        Returns:
            True if the update was successful.
        """
        ...

    @abstractmethod
    def update_typo_tolerance(self, index_name: str, config: dict) -> bool:
        """Update the typo tolerance configuration for an index.

        Args:
            index_name: The name of the index/collection.
            config: Dictionary containing typo tolerance configuration.

        Returns:
            True if the update was successful.
        """
        ...

    @abstractmethod
    def add_documents(
        self, index_name: str, documents: list[dict], primary_key: str
    ) -> Any:
        """Add/upsert documents to an index.

        Args:
            index_name: The name of the index/collection.
            documents: List of document dictionaries to add.
            primary_key: The name of the primary key field.

        Returns:
            A backend-specific response object (e.g., task ID for async operations).
        """
        ...

    @abstractmethod
    def update_documents(
        self, index_name: str, documents: list[dict], primary_key: str
    ) -> Any:
        """Update existing documents in an index.

        Args:
            index_name: The name of the index/collection.
            documents: List of document dictionaries to update.
            primary_key: The name of the primary key field.

        Returns:
            A backend-specific response object.
        """
        ...

    @abstractmethod
    def get_documents(
        self, index_name: str, offset: int = 0, limit: int = 20
    ) -> tuple[list[dict], int]:
        """Fetch documents from an index with pagination.

        Args:
            index_name: The name of the index/collection.
            offset: The offset to start from.
            limit: The maximum number of documents to return.

        Returns:
            A tuple of (list of documents, total count).
        """
        ...

    @abstractmethod
    def get_stats(self, index_name: str) -> dict:
        """Get statistics for an index.

        Args:
            index_name: The name of the index/collection.

        Returns:
            A dictionary containing index statistics.
        """
        ...
