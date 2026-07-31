"""Collection management service.

This module provides business logic for managing search collections/indexes.
It handles creation, deletion, and information retrieval for collections.
"""


from config.settings import Settings
from metadata_schema import get_metadata_schema
from search.base import SearchBackend


class CollectionService:
    """Service for managing search collections/indexes.

    This service provides operations for creating, deleting, and retrieving
    information about search collections. It uses the SearchBackend abstraction
    to work with different search backends.
    """

    def __init__(self, backend: SearchBackend, settings: Settings):
        """Initialize the collection service.

        Args:
            backend: The search backend to use for operations.
            settings: The settings object for configuration.
        """
        self.backend = backend
        self.settings = settings

    def get_index_configs(
        self,
        index_codes: list[str] | None = None,
        prefix: str = "state_legislature_debates",
    ) -> list[tuple[str, str, dict]]:
        """Get index configurations, optionally filtered by index codes.

        Args:
            index_codes: Optional list of index codes to filter by.
            prefix: Prefix for generated index names.

        Returns:
            List of (index_name, index_code, settings_dict) tuples.
        """
        all_index_configs = self.settings.get_index_configs(prefix)

        if index_codes:
            return [(n, ic, c) for n, ic, c in all_index_configs if ic in index_codes]
        return all_index_configs

    def create_collections(
        self,
        index_codes: list[str] | None = None,
        prefix: str = "state_legislature_debates",
    ) -> None:
        """Create collections for specified index codes, or update settings if they already exist.

        For each index, creates the collection if it doesn't exist, or updates its
        searchable, filterable, and sortable attributes, embedders, and typo tolerance
        settings if it does.

        Args:
            index_codes: Optional list of index codes to create. If None, creates all.
            prefix: Prefix for the index name.
        """
        index_configs = self.get_index_configs(index_codes, prefix)

        for index_name, index_code, config in index_configs:
            # Base searchable attributes
            searchable_attributes = []
            filterable_attributes = []
            sortable_attributes = []

            for field in get_metadata_schema(index_code):
                field_name = field["name"]
                if field_name not in searchable_attributes:
                    searchable_attributes.append(field_name)
                if field.get("facet"):
                    filterable_attributes.append(field_name)
                if field.get("searchable"):
                    searchable_attributes.append(field_name)

            searchable_attributes.append("__discussions")

            try:
                # Ensure index exists (Meilisearch creates lazily)
                self.backend.create_index(index_name)

                # Update collection settings
                self.backend.update_searchable_attributes(
                    index_name, searchable_attributes
                )
                self.backend.update_filterable_attributes(
                    index_name, filterable_attributes
                )
                self.backend.update_sortable_attributes(index_name, sortable_attributes)

                # Update embedders if configured
                embeddings_config = config.get("embeddings")
                if embeddings_config:
                    self.backend.update_embedders(index_name, embeddings_config)

                # Update typo tolerance if configured
                if "minWordSizeForTypos" in config:
                    typo_config = {"minWordSizeForTypos": config["minWordSizeForTypos"]}
                    self.backend.update_typo_tolerance(index_name, typo_config)

                print(f"Created/updated collection: {index_name}")
                print(f"  Searchable attributes: {searchable_attributes}")
                print(f"  Filterable attributes: {filterable_attributes}")
                print(f"  Sortable attributes: {sortable_attributes}")
            except Exception as e:
                print(f"Could not create/update collection {index_name}: {e}")

    def delete_collections(
        self,
        index_names: list[str],
        index_codes: list[str] | None = None,
        prefix: str = "state_legislature_debates",
    ) -> None:
        """Delete collections by name or for specified index codes.

        Args:
            index_names: List of collection names to delete.
            index_codes: Optional list of index codes whose collections should be deleted.
            prefix: Prefix for generated index names.
        """
        # Build full list of indexes to delete
        indexes_to_delete = []

        if index_names:
            indexes_to_delete.extend(index_names)

        if index_codes:
            # Get all indexes for the specified index codes
            all_index_configs = self.settings.get_index_configs(prefix)
            index_code_indexes = [
                name for name, ic, _ in all_index_configs if ic in index_codes
            ]
            indexes_to_delete.extend(index_code_indexes)

        # Remove duplicates while preserving order
        seen = set()
        unique_indexes = []
        for idx in indexes_to_delete:
            if idx not in seen:
                seen.add(idx)
                unique_indexes.append(idx)

        for index_name in unique_indexes:
            print(f"Deleting: {index_name}")
            confirm = input("Press y to confirm: ")
            if confirm != "y":
                continue
            try:
                self.backend.delete_index(index_name)
                print(f"Deleted collection: {index_name}")
            except Exception as e:
                print(f"Could not delete collection {index_name}: {e}")

    def print_collections_info(
        self,
        index_codes: list[str] | None = None,
        prefix: str = "state_legislature_debates",
    ) -> None:
        """Print information about collections.

        Args:
            index_codes: Optional list of index codes to print info for.
            prefix: Prefix for generated index names.
        """
        index_configs = self.get_index_configs(index_codes, prefix)

        for index_name, index_code, config in index_configs:
            try:
                details = self.backend.get_index_info(index_name)
                print(f"Collection: {index_name}")
                print(f"  Index code: {index_code}")
                print(f"  Primary key: {details.get('primaryKey', 'id')}")
                print(f"  Documents: {details.get('numberOfDocuments', 0)}")
                print(
                    f"  Searchable attributes: {details.get('searchableAttributes', [])}"
                )
                print(
                    f"  Filterable attributes: {details.get('filterableAttributes', [])}"
                )
                print(f"  Sortable attributes: {details.get('sortableAttributes', [])}")
            except Exception as e:
                print(f"Collection {index_name} does not exist or error: {e}")
