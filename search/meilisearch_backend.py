"""Meilisearch backend implementation.

This module provides the concrete Meilisearch implementation of the SearchBackend
abstract base class.
"""

from typing import Any

import meilisearch
import meilisearch.errors

from .base import SearchBackend


class MeilisearchBackend(SearchBackend):
    """Meilisearch implementation of the SearchBackend interface.

    This class wraps the Meilisearch Python client and provides all the
    operations defined in the SearchBackend abstract base class.
    """

    def __init__(self, config: dict):
        """Initialize the Meilisearch backend.

        Args:
            config: Dictionary containing Meilisearch configuration with
                   'connection' key having 'URL' and 'API_KEY'.

        Raises:
            meilisearch.errors.MeilisearchError: If connection to Meilisearch fails.
        """
        self.client = meilisearch.Client(
            config["connection"]["URL"],
            config["connection"]["API_KEY"],
        )
        # Test connection
        self.health_check()

    def health_check(self) -> bool:
        """Check if Meilisearch is healthy and reachable."""
        try:
            self.client.health()
            return True
        except meilisearch.errors.MeilisearchError:
            return False

    def get_index(self, index_name: str) -> meilisearch.index.Index:
        """Get a Meilisearch index reference.

        Args:
            index_name: The name of the Meilisearch index.

        Returns:
            A Meilisearch Index object.
        """
        return self.client.index(index_name)

    def create_index(self, index_name: str) -> bool:
        """Create a Meilisearch index if it doesn't exist.

        Args:
            index_name: The name of the index to create.

        Returns:
            True if the index exists or was created, False otherwise.
        """
        try:
            # Meilisearch creates indexes lazily, so we just check if we can access it
            index = self.client.index(index_name)
            # Try to get info to verify it exists
            try:
                index.get_raw_info()
                return True
            except meilisearch.errors.MeilisearchApiError:
                # Index doesn't exist yet, but will be created on first write
                return True
        except Exception:
            return False

    def delete_index(self, index_name: str) -> bool:
        """Delete a Meilisearch index.

        Args:
            index_name: The name of the index to delete.

        Returns:
            True if the index was deleted or didn't exist, False otherwise.
        """
        try:
            self.client.index(index_name).delete()
            return True
        except meilisearch.errors.MeilisearchApiError:
            # Index doesn't exist - that's fine
            return True
        except Exception:
            return False

    def index_exists(self, index_name: str) -> bool:
        """Check if a Meilisearch index exists.

        Args:
            index_name: The name of the index to check.

        Returns:
            True if the index exists, False otherwise.
        """
        try:
            self.client.index(index_name).get_raw_info()
            return True
        except meilisearch.errors.MeilisearchApiError:
            return False
        except Exception:
            return False

    def get_index_info(self, index_name: str) -> dict:
        """Get information about a Meilisearch index.

        Args:
            index_name: The name of the index.

        Returns:
            Dictionary containing index information.

        Raises:
            meilisearch.errors.MeilisearchApiError: If the index doesn't exist.
        """
        try:
            return self.client.index(index_name).get_raw_info()
        except meilisearch.errors.MeilisearchApiError:
            return {}

    def update_searchable_attributes(
        self, index_name: str, attributes: list[str]
    ) -> bool:
        """Update searchable attributes for a Meilisearch index.

        Args:
            index_name: The name of the index.
            attributes: List of attribute names that should be searchable.

        Returns:
            True if the update was successful.
        """
        try:
            self.client.index(index_name).update_searchable_attributes(attributes)
            return True
        except Exception:
            return False

    def update_filterable_attributes(
        self, index_name: str, attributes: list[str]
    ) -> bool:
        """Update filterable attributes for a Meilisearch index.

        Args:
            index_name: The name of the index.
            attributes: List of attribute names that should be filterable.

        Returns:
            True if the update was successful.
        """
        try:
            self.client.index(index_name).update_filterable_attributes(attributes)
            return True
        except Exception:
            return False

    def update_sortable_attributes(
        self, index_name: str, attributes: list[str]
    ) -> bool:
        """Update sortable attributes for a Meilisearch index.

        Args:
            index_name: The name of the index.
            attributes: List of attribute names that should be sortable.

        Returns:
            True if the update was successful.
        """
        try:
            self.client.index(index_name).update_sortable_attributes(attributes)
            return True
        except Exception:
            return False

    def update_embedders(self, index_name: str, embedders_config: dict) -> bool:
        """Update embedders configuration for a Meilisearch index.

        Args:
            index_name: The name of the index.
            embedders_config: Dictionary containing embedder configuration.

        Returns:
            True if the update was successful.
        """
        try:
            self.client.index(index_name).update_embedders(embedders_config)
            return True
        except Exception:
            return False

    def update_typo_tolerance(self, index_name: str, config: dict) -> bool:
        """Update typo tolerance configuration for a Meilisearch index.

        Args:
            index_name: The name of the index.
            config: Dictionary containing typo tolerance configuration.

        Returns:
            True if the update was successful.
        """
        try:
            self.client.index(index_name).update_typo_tolerance(config)
            return True
        except Exception:
            return False

    def add_documents(
        self, index_name: str, documents: list[dict], primary_key: str
    ) -> Any:
        """Add/upsert documents to a Meilisearch index.

        Args:
            index_name: The name of the index.
            documents: List of document dictionaries to add.
            primary_key: The name of the primary key field.

        Returns:
            A Meilisearch task object.
        """
        return self.client.index(index_name).add_documents(
            documents, primary_key=primary_key
        )

    def update_documents(
        self, index_name: str, documents: list[dict], primary_key: str
    ) -> Any:
        """Update existing documents in a Meilisearch index.

        Args:
            index_name: The name of the index.
            documents: List of document dictionaries to update.
            primary_key: The name of the primary key field.

        Returns:
            A Meilisearch task object.
        """
        return self.client.index(index_name).update_documents(
            documents, primary_key=primary_key
        )

    def get_documents(
        self, index_name: str, offset: int = 0, limit: int = 20
    ) -> tuple[list[dict], int]:
        """Fetch documents from a Meilisearch index with pagination.

        Args:
            index_name: The name of the index.
            offset: The offset to start from.
            limit: The maximum number of documents to return.

        Returns:
            A tuple of (list of documents, total count).
        """
        try:
            result = self.client.index(index_name).get_documents(
                {
                    "offset": offset,
                    "limit": limit,
                }
            )
            return result.results, result.total
        except Exception:
            return [], 0

    def get_stats(self, index_name: str) -> dict:
        """Get statistics for a Meilisearch index.

        Args:
            index_name: The name of the index.

        Returns:
            Dictionary containing index statistics.
        """
        try:
            return self.client.index(index_name).get_stats().to_dict()
        except Exception:
            return {}
