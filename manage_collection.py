#!/usr/bin/env python3

import argparse
import json
import logging
import traceback
from pathlib import Path
from typing import Optional
from more_itertools import batched

import meilisearch
import meilisearch.errors
import meilisearch.index
from tqdm import tqdm
import yaml

from metadata_schema import get_metadata_schema
from processors import FilesystemProcessor
from processors.base import BaseProcessor

logger = logging.getLogger(__name__)


def get_client(meilisearch_config: dict) -> meilisearch.Client:
    client = meilisearch.Client(
        meilisearch_config["connection"]["URL"],
        meilisearch_config["connection"]["API_KEY"],
    )
    # Test connection
    client.health()
    return client


def get_index_configs(
    meilisearch_config: dict, prefix: str = "state_legislature_debates"
) -> list[tuple[str, str, dict]]:
    """
    Parse index config into (index_name, state_code, settings) tuples.

    Supports two formats:
    - New format: state with indexes variants
        index_config:
          KA:
            files_path: /path/to/KA
            indexes:
              default: {embeddings: null}
              test: {embeddings: {...}}
    - Old format: single index per state (backward compatible)
        index_config:
          KA:
            files_path: /path/to/KA

    Args:
        meilisearch_config: Full config dict
        prefix: Prefix for generated index names

    Returns:
        List of (index_name, state_code, settings_dict) tuples
    """
    result = []
    index_config = meilisearch_config.get("index_config", {})

    for state_code, state_config in index_config.items():
        if not isinstance(state_config, dict):
            continue

        # Check if this state has variant indexes
        if "indexes" in state_config:
            # New format: multiple indexes per state
            for variant_name, variant_config in state_config["indexes"].items():
                # Index name from variant config, or generate from variant name
                index_name = variant_config.get(
                    "index_name", f"{prefix}_{state_code.lower()}_{variant_name}"
                )
                # Merge state-level defaults with variant-specific config
                merged_config = {**state_config, **variant_config}
                # Remove indexes key as it's organizational, not settings
                merged_config.pop("indexes", None)
                merged_config.pop(
                    "index_name", None
                )  # index_name is metadata, not a setting
                result.append((index_name, state_code, merged_config))
        else:
            # Old format: single index per state
            index_name = state_config.get(
                "index_name", f"{prefix}_{state_code.lower()}"
            )
            result.append((index_name, state_code, state_config))

    return result


def delete_collections(
    index_names: list[str], meilisearch_config: dict, states: list[str] = None
):
    """Delete Meilisearch collections by name or for specified states"""
    client = get_client(meilisearch_config)

    # Build full list of indexes to delete
    indexes_to_delete = []

    if index_names:
        indexes_to_delete.extend(index_names)

    if states:
        # Get all indexes for the specified states
        all_index_configs = get_index_configs(meilisearch_config)
        state_indexes = [name for name, sc, _ in all_index_configs if sc in states]
        indexes_to_delete.extend(state_indexes)

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
            client.index(index_name).delete()
            print(f"Deleted collection: {index_name}")
        except meilisearch.errors.MeilisearchApiError:
            print(f"Collection {index_name} does not exist or already deleted")
        except Exception as e:
            print(f"Could not delete collection {index_name}: {e}")


def create_collections(
    states, meilisearch_config: dict, prefix: str = "state_legislature_debates"
):
    """Create Meilisearch collections for specified states"""
    client = get_client(meilisearch_config)

    # Get all index configs, filtered by states if specified
    all_index_configs = get_index_configs(meilisearch_config, prefix)

    if states:
        index_configs = [(n, sc, c) for n, sc, c in all_index_configs if sc in states]
    else:
        index_configs = all_index_configs

    for index_name, state_code, config in index_configs:
        # Base searchable attributes
        searchable_attributes = []
        filterable_attributes = []
        sortable_attributes = []

        for field in get_metadata_schema(state_code):
            field_name = field["name"]
            if field_name not in searchable_attributes:
                searchable_attributes.append(field_name)
            if field.get("facet"):
                filterable_attributes.append(field_name)
            if field.get("searchable"):
                searchable_attributes.append(field_name)

        searchable_attributes.append("__discussions")

        try:
            # Create collection
            collection = client.index(index_name)

            # Update collection settings
            collection.update_searchable_attributes(searchable_attributes)
            collection.update_filterable_attributes(filterable_attributes)
            collection.update_sortable_attributes(sortable_attributes)

            # Update embedders if configured
            embeddings_config = config.get("embeddings")
            if embeddings_config:
                collection.update_embedders(embeddings_config)

            # Update typo tolerance if configured
            if "minWordSizeForTypos" in config:
                typo_config = {"minWordSizeForTypos": config["minWordSizeForTypos"]}
                collection.update_typo_tolerance(typo_config)

            print(f"Created/updated collection: {index_name}")
            print(f"  Searchable attributes: {searchable_attributes}")
            print(f"  Filterable attributes: {filterable_attributes}")
            print(f"  Sortable attributes: {sortable_attributes}")
        except Exception as e:
            print(f"Could not create/update collection {index_name}: {e}")


def print_collections_info(
    states, meilisearch_config: dict, prefix: str = "state_legislature_debates"
):
    """Print information about Meilisearch collections"""
    client = get_client(meilisearch_config)

    # Get all index configs, filtered by states if specified
    all_index_configs = get_index_configs(meilisearch_config, prefix)

    if states:
        index_configs = [(n, sc, c) for n, sc, c in all_index_configs if sc in states]
    else:
        index_configs = all_index_configs

    for index_name, state_code, config in index_configs:
        try:
            collection = client.index(index_name)
            details = collection.get_raw_info()
            print(f"Collection: {index_name}")
            print(f"  State: {state_code}")
            print(f"  Primary key: {details.get('primaryKey', 'id')}")
            print(f"  Documents: {details.get('numberOfDocuments', 0)}")
            print(f"  Searchable attributes: {details.get('searchableAttributes', [])}")
            print(f"  Filterable attributes: {details.get('filterableAttributes', [])}")
            print(f"  Sortable attributes: {details.get('sortableAttributes', [])}")
        except meilisearch.errors.MeilisearchApiError:
            print(f"Collection {index_name} does not exist")
        except Exception as e:
            print(f"Could not retrieve collection {index_name}: {e}")


def upload_from_processor(
    processor: BaseProcessor,
    client: meilisearch.Client,
    index_name: str,
    batch_size: int = 1000,
    use_tqdm: bool = True,
    limit: Optional[int] = None,
) -> tuple[int, list[dict], list[dict]]:
    """Upload documents from a processor to Meilisearch.

    Args:
        processor: A processor instance that yields documents
        client: Meilisearch client instance
        index_name: Name of the Meilisearch index
        batch_size: Number of documents per batch
        use_tqdm: Whether to show progress bar
        limit: Maximum number of source items to process

    Returns:
        Tuple of (total_documents_uploaded, list of response dicts, list of file errors)
    """
    collection = client.index(index_name)

    responses = []
    task_ids = []
    total_count = 0
    file_errors: list[dict[str, str]] = []

    # Callback to collect file errors from processor
    def collect_error(file: str, error_msg: str):
        file_errors.append({"file": file, "error": error_msg})

    # For FilesystemProcessor, we can get the metadata count for accurate progress
    total_for_progress = None
    if hasattr(processor, "_load_metadata"):
        try:
            metadata = processor._load_metadata()
            if limit:
                total_for_progress = min(limit, len(metadata))
            else:
                total_for_progress = len(metadata)
        except Exception as e:
            logger.error(
                f"Failed to load metadata for progress tracking "
                f"(state: {processor.state_code}): {e}"
            )

    # Get the document iterator with error callback
    doc_iter = processor.get_documents(limit=limit, on_error=collect_error)

    # Wrap with tqdm if requested - stream directly, don't collect all docs
    if use_tqdm:
        doc_iter = tqdm(
            doc_iter,
            desc=f"Processing {processor.state_code}",
            total=total_for_progress,
        )

    # Stream directly into batches - NEVER collect all docs in memory
    for batch in batched(doc_iter, batch_size):
        batch_list = list(batch)

        if not batch_list:
            continue

        try:
            task = collection.add_documents(batch_list, primary_key="id")
            task_ids.append(task.task_uid)
            total_count += len(batch_list)
            responses.append(
                {"success": True, "count": len(batch_list), "task_id": task.task_uid}
            )
        except Exception as e:
            logger.error(
                f"Failed to upload batch to {index_name} "
                f"(state: {processor.state_code}, batch_size: {len(batch_list)}): {e}"
            )
            responses.append(
                {"success": False, "error": str(e), "count": len(batch_list)}
            )
            # Record errors for all documents in this failed batch
            for doc in batch_list:
                file_errors.append(
                    {"file": doc.get("file_name", "unknown"), "error": str(e)}
                )

    return total_count, responses, file_errors


def resolve_files_path(
    args_files_path: str | None,
    state_code: str,
    meilisearch_config: dict,
    index_config: dict | None = None,
) -> Path:
    """Resolve the files path from args, index config, state config, or global config."""
    if args_files_path:
        return Path(args_files_path)

    # Check index-specific config first (for variants)
    if index_config:
        files_path_str = index_config.get("files_path")
        if files_path_str:
            return Path(files_path_str)

    # Fall back to state config
    state_config = meilisearch_config.get("index_config", {}).get(state_code, {})
    files_path_str = state_config.get("files_path")
    if files_path_str:
        return Path(files_path_str)

    global_path = meilisearch_config.get("state_path")
    if global_path:
        return Path(global_path)

    raise ValueError(
        f"files_path must be provided as argument, or files_path under index_config.{state_code}, "
        f"or state_path at config root"
    )


def resolve_metadata_path(
    args_metadata_path: str | None,
    state_code: str,
    meilisearch_config: dict,
    files_path: Path,
    index_config: dict | None = None,
) -> Path:
    """Resolve the metadata path from args, index config, state config, or defaults."""
    if args_metadata_path:
        return Path(args_metadata_path)

    # Check index-specific config first (for variants)
    if index_config:
        metadata_path_str = index_config.get("metadata_path")
        if metadata_path_str:
            return Path(metadata_path_str)

    # Fall back to state config
    state_config = meilisearch_config.get("index_config", {}).get(state_code, {})
    metadata_path_str = state_config.get("metadata_path")
    if metadata_path_str:
        return Path(metadata_path_str)

    global_metadata_path = meilisearch_config.get("metadata_path")
    if global_metadata_path:
        return Path(global_metadata_path)

    # Default to files_path/all_metadata.json
    return files_path / "all_metadata.json"


def get_batch_size(meilisearch_config: dict, state_code: str | None = None) -> int:
    """Get batch size from config hierarchy: state > global > default."""
    default_batch_size = 1000

    if state_code:
        state_config = meilisearch_config.get("index_config", {}).get(state_code, {})
        if "batch_size" in state_config:
            return int(state_config["batch_size"])

    global_config = meilisearch_config.get("index_config", {}).get("global", {})
    if "batch_size" in global_config:
        return int(global_config["batch_size"])

    return default_batch_size


def main():
    parser = argparse.ArgumentParser(
        description="Manage Meilisearch collections for legislative debate data"
    )
    parser.add_argument(
        "action",
        choices=["delete", "create", "print_schema", "upload"],
        help="Action to perform: delete, create, print_schema, or upload",
    )
    parser.add_argument(
        "--states",
        nargs="+",
        help="States to perform action on (e.g. AP TS). Defaults to all if not specified.",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to Meilisearch config YAML file",
        default="meilisearch_config.yaml",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional limit on number of documents to process (for upload action)",
    )
    parser.add_argument(
        "--prefix",
        default="state_legislature_debates",
        help="Prefix for the index name (for upload action)",
    )
    parser.add_argument(
        "--files-path",
        help="Path to directory containing data all_metadata.json and downloads (default: state_path from config)",
    )
    parser.add_argument("--index", help="index to delete")
    parser.add_argument(
        "--state-code",
        help="State code (optional, can be derived from files_path)",
    )
    parser.add_argument(
        "--metadata-path",
        help="Absolute path to metadata JSONL file (default: state_path/all_metadata.json or files_path/all_metadata.json)",
    )

    args = parser.parse_args()

    # Meilisearch configuration
    with open(args.config) as f:
        meilisearch_config = yaml.safe_load(f)

    states = args.states
    client = get_client(meilisearch_config)

    match args.action:
        case "delete":
            delete_collections(
                [args.index] if args.index else [], meilisearch_config, states
            )
        case "create":
            create_collections(states, meilisearch_config, args.prefix)
        case "print_schema":
            print_collections_info(states, meilisearch_config, args.prefix)
        case "upload":
            states_to_process = args.states
            if not states_to_process:
                raise ValueError("--states is required for upload action")

            # Get all index configs
            all_index_configs = get_index_configs(meilisearch_config, args.prefix)

            for state in states_to_process:
                # Get all indexes for this state
                state_index_configs = [
                    (name, config)
                    for name, sc, config in all_index_configs
                    if sc == state
                ]

                if not state_index_configs:
                    print(f"Warning: No index configs found for state {state}")
                    continue

                for index_name, index_config in state_index_configs:
                    print(
                        f"\n=== Uploading to index: {index_name} (state: {state}) ==="
                    )

                    # Resolve paths from index config (falling back to state config)
                    files_path = resolve_files_path(
                        args.files_path, state, meilisearch_config, index_config
                    )
                    metadata_path = resolve_metadata_path(
                        args.metadata_path,
                        state,
                        meilisearch_config,
                        files_path,
                        index_config,
                    )

                    # Get processor type from config (default: filesystem)
                    processor_name = index_config.get("processor", "filesystem")

                    # Create the appropriate processor using match/case
                    match processor_name:
                        case "filesystem":
                            processor = FilesystemProcessor(
                                state_code=state,
                                config=meilisearch_config,
                                files_path=files_path,
                                metadata_path=metadata_path,
                            )
                        case "lok_sabha":
                            from processors.lok_sabha import LokSabhaProcessor

                            processor = LokSabhaProcessor(
                                state_code=state,
                                config=meilisearch_config,
                                files_path=files_path,
                                metadata_path=metadata_path,
                            )
                        case _:
                            raise ValueError(
                                f"Unknown processor: {processor_name}. "
                                f"Known processors: filesystem, lok_sabha"
                            )

                    # Get batch size from config
                    batch_size = index_config.get(
                        "batch_size",
                        meilisearch_config.get("index_config", {})
                        .get("global", {})
                        .get("batch_size", 1000),
                    )

                    # Upload documents
                    try:
                        total_count, responses, file_errors = upload_from_processor(
                            processor,
                            client,
                            index_name,
                            batch_size=batch_size,
                            use_tqdm=True,
                            limit=args.limit,
                        )

                        # Save batch responses for debugging
                        with open(
                            f"meilisearch_upload_{state}_{index_name.replace(args.prefix + '_', '')}.json",
                            "w",
                        ) as f:
                            json.dump(responses, f)

                        # Save file errors to metadata errors file
                        error_filename = f"metadata_errors_{state}.json"
                        with open(error_filename, "w") as f:
                            json.dump(file_errors, f)

                        # Count successful uploads
                        success_count = sum(
                            r["count"] for r in responses if r.get("success")
                        )
                        error_count = sum(1 for r in responses if not r.get("success"))

                        print(f"Upload completed for {index_name}")
                        print(f"  Total chunks uploaded: {total_count}")
                        print(
                            f"  Batch responses: {len(responses)} ({success_count} successful, {error_count} errors)"
                        )
                        print(f"  File errors saved to: {error_filename}")

                    except Exception as e:
                        print(f"Error processing index {index_name}: {e}")
                        traceback.print_exc()
        case _:
            print("Unexpected argument:", args.action)


if __name__ == "__main__":
    main()
