"""Configuration and settings management.

This module provides centralized configuration loading and management,
including index configuration parsing and path resolution.
"""

import yaml
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from metadata_schema import get_metadata_schema


def get_index_configs(
    meilisearch_config: dict, prefix: str = "state_legislature_debates"
) -> list[tuple[str, str, dict]]:
    """Parse index config into (index_name, index_code, settings) tuples.

    Supports two formats:
    - New format: index_code with indexes variants
        index_config:
          KA:
            files_path: /path/to/KA
            indexes:
              default: {embeddings: null}
              test: {embeddings: {...}}
    - Old format: single index per index_code (backward compatible)
        index_config:
          KA:
            files_path: /path/to/KA

    Args:
        meilisearch_config: Full config dict
        prefix: Prefix for generated index names

    Returns:
        List of (index_name, index_code, settings_dict) tuples
    """
    result = []
    index_config = meilisearch_config.get("index_config", {})

    for index_code, index_config_dict in index_config.items():
        if not isinstance(index_config_dict, dict):
            continue

        # Check if this index_code has variant indexes
        if "indexes" in index_config_dict:
            # New format: multiple indexes per index_code
            for variant_name, variant_config in index_config_dict["indexes"].items():
                # Index name from variant config, or generate from variant name
                index_name = variant_config.get(
                    "index_name", f"{prefix}_{index_code.lower()}_{variant_name}"
                )
                # Merge index_code-level defaults with variant-specific config
                merged_config = {**index_config_dict, **variant_config}
                # Remove indexes key as it's organizational, not settings
                merged_config.pop("indexes", None)
                merged_config.pop(
                    "index_name", None
                )  # index_name is metadata, not a setting
                result.append((index_name, index_code, merged_config))
        else:
            # Old format: single index per index_code
            index_name = index_config_dict.get(
                "index_name", f"{prefix}_{index_code.lower()}"
            )
            result.append((index_name, index_code, index_config_dict))

    return result


def resolve_files_path(
    args_files_path: str | None,
    index_code: str,
    meilisearch_config: dict,
    index_config: dict | None = None,
) -> Path:
    """Resolve the files path from args, index config, index_code config, or global config."""
    if args_files_path:
        return Path(args_files_path)

    # Check index-specific config first (for variants)
    if index_config:
        files_path_str = index_config.get("files_path")
        if files_path_str:
            return Path(files_path_str)

    # Fall back to index_code config
    index_code_config = meilisearch_config.get("index_config", {}).get(index_code, {})
    files_path_str = index_code_config.get("files_path")
    if files_path_str:
        return Path(files_path_str)

    global_path = meilisearch_config.get("index_codes_path")
    if global_path:
        return Path(global_path)

    raise ValueError(
        f"files_path must be provided as argument, or files_path under index_config.{index_code}, "
        f"or index_codes_path at config root"
    )


def resolve_metadata_path(
    args_metadata_path: str | None,
    index_code: str,
    meilisearch_config: dict,
    files_path: Path,
    index_config: dict | None = None,
) -> Path:
    """Resolve the metadata path from args, index config, index_code config, or defaults."""
    if args_metadata_path:
        return Path(args_metadata_path)

    # Check index-specific config first (for variants)
    if index_config:
        metadata_path_str = index_config.get("metadata_path")
        if metadata_path_str:
            return Path(metadata_path_str)

    # Fall back to index_code config
    index_code_config = meilisearch_config.get("index_config", {}).get(index_code, {})
    metadata_path_str = index_code_config.get("metadata_path")
    if metadata_path_str:
        return Path(metadata_path_str)

    global_metadata_path = meilisearch_config.get("metadata_path")
    if global_metadata_path:
        return Path(global_metadata_path)

    # Default to files_path/all_metadata.json
    return files_path / "all_metadata.json"


def get_batch_size(meilisearch_config: dict, index_code: str | None = None) -> int:
    """Get batch size from config hierarchy: index_code > global > default."""
    default_batch_size = 1000

    if index_code:
        index_code_config = meilisearch_config.get("index_config", {}).get(
            index_code, {}
        )
        if "batch_size" in index_code_config:
            return int(index_code_config["batch_size"])

    global_config = meilisearch_config.get("index_config", {}).get("global", {})
    if "batch_size" in global_config:
        return int(global_config["batch_size"])

    return default_batch_size


def get_metadata_count(metadata_path: Path, limit: int | None = None) -> int | None:
    """Get total metadata count for progress tracking.

    Args:
        metadata_path: Path to metadata JSONL file
        limit: Optional limit on number of items to process

    Returns:
        Total count of metadata items (respecting limit), or None if error
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        if not metadata_path.exists():
            logger.warning(
                f"Metadata file not found for progress tracking: {metadata_path}"
            )
            return None

        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata_text = f.read()

        line_count = len(metadata_text.splitlines())

        if limit is not None:
            return min(limit, line_count)
        return line_count
    except Exception as e:
        logger.error(f"Failed to count metadata items at {metadata_path}: {e}")
        return None


class Settings:
    """Centralized settings management for the application.

    This class provides a single point for accessing configuration values
    and derived settings.
    """

    def __init__(self, config_path: str):
        """Initialize settings from a YAML configuration file.

        Args:
            config_path: Path to the YAML configuration file.
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """Load configuration from the YAML file."""
        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def get_index_configs(self, prefix: str = "state_legislature_debates") -> list[tuple[str, str, dict]]:
        """Get all index configurations.

        Args:
            prefix: Prefix for generated index names.

        Returns:
            List of (index_name, index_code, settings_dict) tuples.
        """
        return get_index_configs(self.config, prefix)

    def get_index_codes(self) -> list[str]:
        """Get all configured index codes.

        Returns:
            List of index code strings.
        """
        return list(self.config.get("index_config", {}).keys())

    def get_meilisearch_config(self) -> dict:
        """Get the Meilisearch-specific configuration.

        Returns:
            Dictionary containing Meilisearch configuration.
        """
        return self.config

    def get_index_code_config(self, index_code: str) -> dict:
        """Get configuration for a specific index code.

        Args:
            index_code: The index code to get configuration for.

        Returns:
            Dictionary containing configuration for the index code.
        """
        return self.config.get("index_config", {}).get(index_code, {})

    def get_global_config(self) -> dict:
        """Get global configuration.

        Returns:
            Dictionary containing global configuration.
        """
        return self.config.get("index_config", {}).get("global", {})

    def resolve_files_path(
        self,
        args_files_path: str | None = None,
        index_code: str | None = None,
        index_config: dict | None = None,
    ) -> Path:
        """Resolve the files path using the settings.

        Args:
            args_files_path: Files path from command line arguments.
            index_code: The index code.
            index_config: Index-specific configuration.

        Returns:
            Resolved files path as a Path object.
        """
        if index_code is None:
            raise ValueError("index_code is required to resolve files path")
        return resolve_files_path(
            args_files_path, index_code, self.config, index_config
        )

    def resolve_metadata_path(
        self,
        args_metadata_path: str | None = None,
        index_code: str | None = None,
        files_path: Path | None = None,
        index_config: dict | None = None,
    ) -> Path:
        """Resolve the metadata path using the settings.

        Args:
            args_metadata_path: Metadata path from command line arguments.
            index_code: The index code.
            files_path: The files path (for default resolution).
            index_config: Index-specific configuration.

        Returns:
            Resolved metadata path as a Path object.
        """
        if index_code is None:
            raise ValueError("index_code is required to resolve metadata path")
        if files_path is None:
            files_path = self.resolve_files_path(None, index_code, index_config)
        return resolve_metadata_path(
            args_metadata_path, index_code, self.config, files_path, index_config
        )

    def get_batch_size(self, index_code: str | None = None) -> int:
        """Get batch size from configuration hierarchy.

        Args:
            index_code: Optional index code for per-index configuration.

        Returns:
            Batch size as an integer.
        """
        return get_batch_size(self.config, index_code)

    def get_metadata_count(self, metadata_path: Path, limit: int | None = None) -> int | None:
        """Get metadata count for progress tracking.

        Args:
            metadata_path: Path to metadata JSONL file.
            limit: Optional limit on number of items.

        Returns:
            Count of metadata items, or None if error.
        """
        return get_metadata_count(metadata_path, limit)
