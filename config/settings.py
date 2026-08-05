"""Configuration and settings management.

This module provides centralized configuration loading and management,
including index configuration parsing and path resolution.
"""

from pathlib import Path

import yaml


def get_index_configs(
    meilisearch_config: dict, prefix: str = "state_legislature_debates"
) -> list[tuple[str, str, dict]]:
    """Parse index config into (index_name, index_code, settings) tuples.

    Now supports single index per index_code with multiple embeddings per index.

    Format:
        index_config:
          KA:
            index_name: "state_legislature_debates_ka"  # optional, defaults to prefix_index_code
            files_path: /path/to/KA
            embeddings:  # optional, can contain multiple embedder configs
              my_embedder_1:
                source: "rest"
                dimensions: 768
                url: "http://example.com/embeddings"
              my_embedder_2:
                source: "rest"
                dimensions: 384
                url: "http://another.com/embeddings"

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

        # Skip global config and embeddings config
        if index_code in ("global", "embeddings"):
            continue

        # Extract index_name from config or generate from index_code
        index_name = index_config_dict.get(
            "index_name", f"{prefix}_{index_code.lower()}"
        )

        # Remove index_name from the config as it's metadata, not a setting
        merged_config = {**index_config_dict}
        merged_config.pop("index_name", None)

        result.append((index_name, index_code, merged_config))

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


def resolve_embeddings_config(
    meilisearch_config: dict,
    index_code_config: dict | None,
) -> dict | None:
    """Resolve embeddings configuration by name references.

    Embedding providers are defined at the top level under `embeddings` key.
    Index configurations reference them by name using `embedding_refs` list.

    Args:
        meilisearch_config: Full configuration dictionary
        index_code_config: Index code-specific configuration

    Returns:
        Resolved embeddings dictionary, or None if no embeddings configured
    """
    if not index_code_config:
        return None

    # Get embedding references from index config
    embedding_refs = index_code_config.get("embedding_refs")
    if not embedding_refs:
        return None

    # Get the global embeddings catalog
    embeddings_catalog = meilisearch_config.get("embeddings")
    if not embeddings_catalog:
        return None

    # Build the resolved embeddings dict by looking up each reference
    resolved: dict = {}
    for ref_name in embedding_refs:
        if ref_name in embeddings_catalog:
            resolved[ref_name] = embeddings_catalog[ref_name]
        # Silently skip references that don't exist (could add warning if needed)

    return resolved if resolved else None


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

    def get_index_configs(
        self, prefix: str = "state_legislature_debates"
    ) -> list[tuple[str, str, dict]]:
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

    def get_metadata_count(
        self, metadata_path: Path, limit: int | None = None
    ) -> int | None:
        """Get metadata count for progress tracking.

        Args:
            metadata_path: Path to metadata JSONL file.
            limit: Optional limit on number of items.

        Returns:
            Count of metadata items, or None if error.
        """
        return get_metadata_count(metadata_path, limit)
