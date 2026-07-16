#!/usr/bin/env python3

import argparse
import json
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


def get_client(meilisearch_config: dict) -> meilisearch.Client:
    client = meilisearch.Client(
        meilisearch_config["connection"]["URL"],
        meilisearch_config["connection"]["API_KEY"],
    )
    # Test connection
    client.health()
    return client


def delete_collections(index_names: list[str], meilisearch_config: dict):
    """Delete Meilisearch collections for specified states"""
    client = get_client(meilisearch_config)

    for index_name in index_names:
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

    for state_code in states:
        collection_name = f"{prefix}_{state_code.lower()}"

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
            collection = client.index(collection_name)

            # Update collection settings
            collection.update_searchable_attributes(searchable_attributes)
            collection.update_filterable_attributes(filterable_attributes)
            collection.update_sortable_attributes(sortable_attributes)

            # Update embedders if configured (state-specific first, then global)
            index_config = meilisearch_config.get("index_config", {})
            state_embeddings = index_config.get(state_code, {}).get("embeddings")
            global_embeddings = index_config.get("global", {}).get("embeddings")
            embeddings_config = state_embeddings or global_embeddings

            if embeddings_config:
                collection.update_embedders(embeddings_config)

            # Update typo tolerance if configured
            if (
                "index_config" in meilisearch_config
                and "global" in meilisearch_config["index_config"]
                and "minWordSizeForTypos"
                in meilisearch_config["index_config"]["global"]
            ):
                typo_config = {
                    "minWordSizeForTypos": meilisearch_config["index_config"]["global"][
                        "minWordSizeForTypos"
                    ]
                }
                collection.update_typo_tolerance(typo_config)

            print(f"Created/updated collection: {collection_name}")
            print(f"  Searchable attributes: {searchable_attributes}")
            print(f"  Filterable attributes: {filterable_attributes}")
            print(f"  Sortable attributes: {sortable_attributes}")
        except Exception as e:
            print(f"Could not create/update collection {collection_name}: {e}")


def print_collections_info(states, meilisearch_config: dict):
    """Print information about Meilisearch collections"""
    client = get_client(meilisearch_config)

    for state_code in states:
        collection_name = f"state_legislature_debates_{state_code.lower()}"
        try:
            collection = client.index(collection_name)
            details = collection.get_raw_info()
            print(f"Collection: {collection_name}")
            print(f"  Primary key: {details.get('primaryKey', 'id')}")
            print(f"  Documents: {details.get('numberOfDocuments', 0)}")
            print(f"  Searchable attributes: {details.get('searchableAttributes', [])}")
            print(f"  Filterable attributes: {details.get('filterableAttributes', [])}")
            print(f"  Sortable attributes: {details.get('sortableAttributes', [])}")
        except meilisearch.errors.MeilisearchApiError:
            print(f"Collection {collection_name} does not exist")
        except Exception as e:
            print(f"Could not retrieve collection {collection_name}: {e}")


def upload_from_processor(
    processor: BaseProcessor,
    index_name: str,
    batch_size: int = 100000,
    use_tqdm: bool = True,
    limit: Optional[int] = None,
) -> tuple[int, list[dict]]:
    """Upload documents from a processor to Meilisearch.

    Args:
        processor: A processor instance that yields documents
        index_name: Name of the Meilisearch index
        batch_size: Number of documents per batch
        use_tqdm: Whether to show progress bar
        limit: Maximum number of source items to process

    Returns:
        Tuple of (total_documents_uploaded, list of response dicts)
    """
    client = processor.ms_client
    collection = client.index(index_name)

    responses = []
    task_ids = []
    total_count = 0

    # Collect all documents from processor
    all_docs = []
    doc_iter = processor.get_documents(limit=limit)
    if use_tqdm:
        # For filesystem processor, we can count metadata items
        # For now, just iterate without count
        doc_iter = tqdm(doc_iter, desc=f"Processing {processor.state_code}")

    for doc in doc_iter:
        all_docs.append(doc)

    # Upload in batches
    for i, batch in enumerate(batched(all_docs, batch_size)):
        batch_list = list(batch)
        try:
            task = collection.add_documents(batch_list, primary_key="id")
            task_ids.append(task.task_uid)
            total_count += len(batch_list)
            responses.append(
                {"success": True, "count": len(batch_list), "task_id": task.task_uid}
            )
        except Exception as e:
            responses.append(
                {"success": False, "error": str(e), "count": len(batch_list)}
            )

    return total_count, responses


def resolve_files_path(
    args_files_path: str | None,
    state_code: str,
    meilisearch_config: dict,
) -> Path:
    """Resolve the files path from args, state config, or global config."""
    if args_files_path:
        return Path(args_files_path)

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
) -> Path:
    """Resolve the metadata path from args, state config, or defaults."""
    if args_metadata_path:
        return Path(args_metadata_path)

    state_config = meilisearch_config.get("index_config", {}).get(state_code, {})
    metadata_path_str = state_config.get("metadata_path")
    if metadata_path_str:
        return Path(metadata_path_str)

    global_metadata_path = meilisearch_config.get("metadata_path")
    if global_metadata_path:
        return Path(global_metadata_path)

    # Default to files_path/all_metadata.json
    return files_path / "all_metadata.json"


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
            delete_collections([args.index], meilisearch_config)
        case "create":
            create_collections(states, meilisearch_config, args.prefix)
        case "print_schema":
            print_collections_info(states, meilisearch_config)
        case "upload":
            states_to_process = args.states
            if not states_to_process:
                raise ValueError("--states is required for upload action")

            for state in states_to_process:
                print(f"\n=== Processing state: {state} ===")

                # Resolve paths
                files_path = resolve_files_path(
                    args.files_path, state, meilisearch_config
                )
                metadata_path = resolve_metadata_path(
                    args.metadata_path, state, meilisearch_config, files_path
                )

                # Get processor type from config (default: filesystem)
                state_config = meilisearch_config.get("index_config", {}).get(state, {})
                processor_name = state_config.get("processor", "filesystem")

                # Create the appropriate processor using match/case
                match processor_name:
                    case "filesystem":
                        processor = FilesystemProcessor(
                            state_code=state,
                            config=meilisearch_config,
                            ms_client=client,
                            files_path=files_path,
                            metadata_path=metadata_path,
                        )
                    case "lok_sabha":
                        from processors.lok_sabha import LokSabhaProcessor

                        processor = LokSabhaProcessor(
                            state_code=state,
                            config=meilisearch_config,
                            ms_client=client,
                            files_path=files_path,
                            metadata_path=metadata_path,
                        )
                    case _:
                        raise ValueError(
                            f"Unknown processor: {processor_name}. "
                            f"Known processors: filesystem, lok_sabha"
                        )

                # Build index name
                collection_name = f"{args.prefix}_{state.lower()}"

                # Upload documents
                try:
                    total_count, responses = upload_from_processor(
                        processor, collection_name, use_tqdm=True, limit=args.limit
                    )

                    # Save responses for debugging
                    with open(f"meilisearch_upload_{state}.json", "w") as f:
                        json.dump(responses, f)

                    # Count successful uploads
                    success_count = sum(
                        r["count"] for r in responses if r.get("success")
                    )
                    error_count = sum(1 for r in responses if not r.get("success"))

                    print(f"Upload completed for {state}")
                    print(f"  Total chunks uploaded: {total_count}")
                    print(
                        f"  Batch responses: {len(responses)} ({success_count} successful, {error_count} errors)"
                    )

                except Exception as e:
                    print(f"Error processing state {state}: {e}")
                    traceback.print_exc()
        case _:
            print("Unexpected argument:", args.action)


if __name__ == "__main__":
    main()
