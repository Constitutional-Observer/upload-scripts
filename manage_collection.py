import argparse
import json
import logging
import traceback
from collections.abc import Callable, Iterator
from pathlib import Path

import meilisearch
import meilisearch.errors
import meilisearch.index
import yaml
from more_itertools import batched
from tqdm import tqdm

from metadata_schema import get_metadata_schema
from processors.base import DocumentProcessor
from processors.functional_pipeline import (
    ChunkConfig,
    FetchConfig,
    process_index,
)
from processors.postprocessing import (
    PostprocessConfig,
    StepConfig,
    resolve_postprocess_config,
    step_registry,
)

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
    Parse index config into (index_name, index_code, settings) tuples.

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


def delete_collections(
    index_names: list[str], meilisearch_config: dict, index_codes: list[str] = None
):
    """Delete Meilisearch collections by name or for specified index codes"""
    client = get_client(meilisearch_config)

    # Build full list of indexes to delete
    indexes_to_delete = []

    if index_names:
        indexes_to_delete.extend(index_names)

    if index_codes:
        # Get all indexes for the specified index codes
        all_index_configs = get_index_configs(meilisearch_config)
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
            client.index(index_name).delete()
            print(f"Deleted collection: {index_name}")
        except meilisearch.errors.MeilisearchApiError:
            print(f"Collection {index_name} does not exist or already deleted")
        except Exception as e:
            print(f"Could not delete collection {index_name}: {e}")


def create_collections(
    index_codes, meilisearch_config: dict, prefix: str = "state_legislature_debates"
):
    """Create Meilisearch collections for specified index codes, or update settings if they already exist.

    For each index, creates the collection if it doesn't exist, or updates its
    searchable, filterable, and sortable attributes, embedders, and typo tolerance
    settings if it does.
    """
    client = get_client(meilisearch_config)

    # Get all index configs, filtered by index_codes if specified
    all_index_configs = get_index_configs(meilisearch_config, prefix)

    if index_codes:
        index_configs = [
            (n, ic, c) for n, ic, c in all_index_configs if ic in index_codes
        ]
    else:
        index_configs = all_index_configs

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
    index_codes, meilisearch_config: dict, prefix: str = "state_legislature_debates"
):
    """Print information about Meilisearch collections"""
    client = get_client(meilisearch_config)

    # Get all index configs, filtered by index_codes if specified
    all_index_configs = get_index_configs(meilisearch_config, prefix)

    if index_codes:
        index_configs = [
            (n, ic, c) for n, ic, c in all_index_configs if ic in index_codes
        ]
    else:
        index_configs = all_index_configs

    for index_name, index_code, config in index_configs:
        try:
            collection = client.index(index_name)
            details = collection.get_raw_info()
            print(f"Collection: {index_name}")
            print(f"  Index code: {index_code}")
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
    processor: DocumentProcessor,
    client: meilisearch.Client,
    index_name: str,
    batch_size: int = 1000,
    use_tqdm: bool = True,
    limit: int | None = None,
    progress_desc: str = "processing",
    total_for_progress: int | None = None,
) -> tuple[int, list[dict], list[dict]]:
    """Upload (upsert) documents from a DocumentProcessor to Meilisearch.

    Documents are added using Meilisearch's add_documents which performs an upsert:
    if a document with the same primary key (id) already exists, it is updated;
    otherwise, it is inserted.

    Args:
        processor: A DocumentProcessor instance (callable that yields document dicts)
        client: Meilisearch client instance
        index_name: Name of the Meilisearch index
        batch_size: Number of documents per batch
        use_tqdm: Whether to show progress bar
        limit: Maximum number of source items to process
        progress_desc: Description string for the progress bar
        total_for_progress: Total count for progress bar (optional)

    Returns:
        Tuple of (total_documents_uploaded, list of response dicts, list of file errors)
    """
    collection = client.index(index_name)

    responses = []
    task_ids = []
    total_count = 0
    file_errors: list[dict[str, str]] = []

    # Callback to collect file errors from processor
    def collect_error(file_identifier: str, error_msg: str):
        file_errors.append({"file": file_identifier, "error": error_msg})

    # Get document iterator from processor
    doc_iter = processor(limit=limit, on_error=collect_error)

    # Wrap with tqdm if requested - stream directly, don't collect all docs
    if use_tqdm:
        doc_iter = tqdm(
            doc_iter,
            desc=f"Processing {progress_desc}",
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
                f"(index_code: {progress_desc}, batch_size: {len(batch_list)}): {e}"
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


def do_upload(
    index_codes_to_process: list[str],
    client: meilisearch.Client,
    meilisearch_config: dict,
    args: argparse.Namespace,
    prefix: str,
) -> None:
    """Execute the upload (upsert) workflow for the given index codes.

    For each index code, processes documents through the configured processor
    and upserts them into Meilisearch. Uses add_documents which updates existing
    documents or inserts new ones based on the document id.
    """
    # Get all index configs
    all_index_configs = get_index_configs(meilisearch_config, prefix)

    for index_code in index_codes_to_process:
        # Get all indexes for this index_code
        index_code_index_configs = [
            (name, config) for name, ic, config in all_index_configs if ic == index_code
        ]

        if not index_code_index_configs:
            print(f"Warning: No index configs found for index code {index_code}")
            continue

        for index_name, index_config in index_code_index_configs:
            print(
                f"\n=== Uploading to index: {index_name} (index_code: {index_code}) ==="
            )

            # Resolve paths from index config (falling back to index_code config)
            files_path = resolve_files_path(
                args.files_path, index_code, meilisearch_config, index_config
            )
            metadata_path = resolve_metadata_path(
                args.metadata_path,
                index_code,
                meilisearch_config,
                files_path,
                index_config,
            )

            # Get processor type from config (default: functional)
            processor_name = index_config.get("processor", "functional")

            # Get total for progress bar
            total_for_progress = get_metadata_count(metadata_path, args.limit)

            # Create processor using factory
            processor = create_processor(
                processor_name=processor_name,
                index_code=index_code,
                files_path=files_path,
                metadata_path=metadata_path,
                meilisearch_config=meilisearch_config,
                index_config=index_config,
            )

            # Get batch size from config using centralized function
            batch_size = get_batch_size(meilisearch_config, index_code)

            # Upload documents
            try:
                total_count, responses, file_errors = upload_from_processor(
                    processor,
                    client,
                    index_name,
                    batch_size=batch_size,
                    use_tqdm=True,
                    limit=args.limit,
                    progress_desc=index_code,
                    total_for_progress=total_for_progress,
                )

                # Save batch responses for debugging
                with open(
                    f"meilisearch_upload_{index_code}_{index_name.replace(prefix + '_', '')}.json",
                    "w",
                ) as f:
                    json.dump(responses, f)

                # Save file errors to metadata errors file
                error_filename = f"metadata_errors_{index_code}.json"
                with open(error_filename, "w") as f:
                    json.dump(file_errors, f)

                # Count successful uploads
                success_count = sum(r["count"] for r in responses if r.get("success"))
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


def do_postprocess(
    index_codes_to_process: list[str],
    client: meilisearch.Client,
    meilisearch_config: dict,
    args: argparse.Namespace,
    prefix: str,
) -> None:
    """Apply postprocessing to existing documents in MeiliSearch.

    Fetches documents from MeiliSearch for the specified index codes and runs
    configured postprocessing steps on them. Documents are updated in place
    with the results of the postprocessing steps.

    Args:
        index_codes_to_process: List of index codes to process
        client: Meilisearch client instance
        meilisearch_config: Full Meilisearch configuration
        args: Parsed command-line arguments
        prefix: Index name prefix
    """

    # Get all index configs
    all_index_configs = get_index_configs(meilisearch_config, prefix)

    for index_code in index_codes_to_process:
        # Get all indexes for this index_code
        index_code_index_configs = [
            (name, ic, config)
            for name, ic, config in all_index_configs
            if ic == index_code
        ]

        if not index_code_index_configs:
            print(f"Warning: No index configs found for index code {index_code}")
            continue

        for index_name, _, index_config in index_code_index_configs:
            print(
                f"\n=== Postprocessing index: {index_name} (index_code: {index_code}) ==="
            )

            # Resolve postprocessing config for this index
            global_config = meilisearch_config.get("index_config", {}).get("global", {})
            index_code_config = meilisearch_config.get("index_config", {}).get(
                index_code, {}
            )

            postprocess_config = resolve_postprocess_config(
                global_config=global_config,
                index_code_config=index_code_config,
                variant_config=index_config,
            )

            if not postprocess_config.enabled:
                print(f"  Postprocessing disabled for {index_name}, skipping")
                continue

            if not postprocess_config.get_enabled_steps():
                print(f"  No enabled postprocessing steps for {index_name}, skipping")
                continue

            # Get the index
            collection = client.index(index_name)

            # Get total document count for progress tracking
            try:
                total_docs = collection.get_stats().number_of_documents
                print(f"  Processing {total_docs} documents...")
            except Exception as e:
                print(f"  Could not get document count: {e}")
                total_docs = None

            # Process documents in pages
            page_size = getattr(args, "page_size", 200)
            batch_size = getattr(args, "batch_size", 200)
            force = getattr(args, "force", False)

            processed = 0
            skipped = 0
            pending_updates: list[dict] = []

            def flush_updates():
                """Flush pending updates to MeiliSearch."""
                if pending_updates:
                    try:
                        collection.update_documents(pending_updates, primary_key="id")
                        pending_updates.clear()
                    except Exception as e:
                        print(f"  Failed to update batch: {e}")

            # Fetch and process documents
            offset = 0
            while True:
                try:
                    result = collection.get_documents(
                        {
                            "offset": offset,
                            "limit": page_size,
                        }
                    )
                    docs = result.results
                    if not docs:
                        break

                    for doc in docs:
                        doc_id = doc.get("id")
                        if not doc_id:
                            skipped += 1
                            continue

                        # Extract fields from document
                        text = doc.get("__discussions") or doc.get("discussions", "")
                        file_name = doc.get("file_name", "unknown")
                        chunk_id = doc.get("chunk_id", 0)
                        metadata = {
                            k: v
                            for k, v in doc.items()
                            if k
                            not in [
                                "id",
                                "__discussions",
                                "discussions",
                                "file_name",
                                "chunk_id",
                                "entities",
                                "_ner",
                            ]
                        }

                        # Check if already processed (skip unless force)
                        if not force:
                            # Check if any of the configured steps' output fields already exist
                            skip = True
                            for step_config in postprocess_config.get_enabled_steps():
                                output_field = step_config.config.get(
                                    "output_field", step_config.name
                                )
                                if output_field not in doc:
                                    skip = False
                                    break
                            if skip:
                                skipped += 1
                                continue

                        # Run postprocessing steps
                        from processors.postprocessing import run_postprocessing_steps

                        step_results = run_postprocessing_steps(
                            chunk=text,
                            file_name=file_name,
                            chunk_id=chunk_id,
                            metadata=metadata,
                            config=postprocess_config,
                            registry=step_registry,
                        )

                        if step_results:
                            update_doc = {"id": doc_id, **step_results}
                            pending_updates.append(update_doc)

                        processed += 1

                        # Flush if batch size reached
                        if len(pending_updates) >= batch_size:
                            flush_updates()

                    offset += len(docs)
                    if offset >= result.total:
                        break

                except Exception as e:
                    print(f"  Error fetching documents at offset {offset}: {e}")
                    break

            # Flush any remaining updates
            flush_updates()

            print(f"  Postprocessing completed for {index_name}")
            print(f"    Processed: {processed}, Skipped: {skipped}")


def create_processor(
    processor_name: str,
    index_code: str,
    files_path: Path,
    metadata_path: Path,
    meilisearch_config: dict,
    index_config: dict,
) -> DocumentProcessor:
    """Factory function to create document processors.

    This provides a single entry point for creating all types of processors,
    ensuring they all conform to the DocumentProcessor protocol.

    To add a new processor type (e.g., for API-based sources like Lok Sabha):
    1. Add a new case to the match statement below
    2. Create a metadata_iterator function that yields metadata dicts
    3. Create a file_resolver function: (file_name: str, metadata: dict) -> Path
    4. Pass both to process_index with appropriate fetch_config

    Args:
        processor_name: Name of the processor type ("functional", or custom)
        index_code: Index code (e.g., "AP", "KA")
        files_path: Path to directory containing data files (optional for some processors)
        metadata_path: Path to metadata JSONL file (optional for some processors)
        meilisearch_config: Full Meilisearch configuration
        index_config: Index-specific configuration (can contain custom keys for processors)

    Returns:
        A DocumentProcessor instance (callable that yields document dicts)

    Raises:
        ValueError: If processor_name is unknown
    """
    match processor_name:
        case "functional":
            # Extract configuration options
            use_ocr = index_config.get("use_ocr", False)
            run_ner = index_config.get("run_ner", False)
            chunk_config_dict = index_config.get("chunk_config", None)

            # NEW: Resolve postprocessing configuration
            global_config = meilisearch_config.get("index_config", {}).get("global", {})
            index_code_config = meilisearch_config.get("index_config", {}).get(
                index_code, {}
            )

            postprocess_config = resolve_postprocess_config(
                global_config=global_config,
                index_code_config=index_code_config,
                variant_config=index_config,
            )

            # If run_ner is True but postprocessing is disabled, enable it with NER step
            if run_ner and not postprocess_config.enabled:
                postprocess_config = PostprocessConfig(
                    enabled=True, steps=[StepConfig(name="ner", enabled=True)]
                )
            elif run_ner and not postprocess_config.has_step("ner"):
                # Add NER step if run_ner is True but NER step isn't configured
                postprocess_config.steps.append(StepConfig(name="ner", enabled=True))

            # Build fetch config (no file_resolver for file-based sources)
            fetch_config = FetchConfig(
                files_path=files_path,
                metadata_path=metadata_path,
                file_resolver=None,
            )

            # Build chunk config if provided
            chunk_config = (
                ChunkConfig(**chunk_config_dict) if chunk_config_dict else None
            )

            # Create a callable generator function that conforms to DocumentProcessor
            def functional_processor(
                limit: int | None = None,
                on_error: Callable[[str, str], None] | None = None,
            ) -> Iterator[dict]:
                """Generator function for functional pipeline."""

                # Create metadata iterator that reads from JSONL file line by line
                def metadata_iterator():
                    if not metadata_path.exists():
                        raise FileNotFoundError(
                            f"Metadata file not found: {metadata_path}"
                        )
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        for line in f:
                            yield json.loads(line)

                for doc in process_index(
                    index_code=index_code,
                    metadata_iterator=metadata_iterator(),
                    fetch_config=fetch_config,
                    limit=limit,
                    use_ocr=use_ocr,
                    chunk_config=chunk_config,
                    run_ner=run_ner,
                    on_error=on_error,
                    postprocess_config=postprocess_config,
                    step_registry=step_registry,
                ):
                    yield doc.to_dict()

            return functional_processor

        case _:
            raise ValueError(
                f"Unknown processor: {processor_name}. Known processors: functional"
            )


def main():
    parser = argparse.ArgumentParser(
        description="Manage Meilisearch collections for legislative debate data"
    )
    parser.add_argument(
        "action",
        choices=[
            "delete",
            "create",
            "print_schema",
            "upload",
            "add",
            "remove",
            "postprocess",
        ],
        help="Action to perform: delete, create (or update settings), print_schema, upload (upsert), add (create+upsert), remove (delete), or postprocess (run postprocessing on existing documents)",
    )
    parser.add_argument(
        "--index-codes",
        nargs="+",
        help="Index codes to perform action on (e.g. AP TS LS). Defaults to all if not specified.",
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
        help="Path to directory containing data all_metadata.json and downloads (default: index_codes_path from config)",
    )
    parser.add_argument("--index", help="index to delete")
    parser.add_argument(
        "--index-code",
        help="Index code (optional, can be derived from files_path)",
    )
    parser.add_argument(
        "--metadata-path",
        help="Absolute path to metadata JSONL file (default: index_codes_path/all_metadata.json or files_path/all_metadata.json)",
    )
    # Postprocessing-specific arguments
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-process documents even if already processed (for postprocess action)",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=200,
        help="Documents fetched per request (for postprocess action, default: 200)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Documents per update request (for postprocess action, default: 200)",
    )

    args = parser.parse_args()

    # Meilisearch configuration
    with open(args.config) as f:
        meilisearch_config = yaml.safe_load(f)

    index_codes = args.index_codes
    client = get_client(meilisearch_config)

    match args.action:
        case "delete" | "remove":
            delete_collections(
                [args.index] if args.index else [], meilisearch_config, index_codes
            )
        case "create":
            create_collections(index_codes, meilisearch_config, args.prefix)
        case "print_schema":
            print_collections_info(index_codes, meilisearch_config, args.prefix)
        case "add":
            # Create collections first, then upload
            create_collections(index_codes, meilisearch_config, args.prefix)
            index_codes_to_process = args.index_codes
            if not index_codes_to_process:
                raise ValueError("--index-codes is required for add action")
            do_upload(
                index_codes_to_process, client, meilisearch_config, args, args.prefix
            )
        case "upload":
            index_codes_to_process = args.index_codes
            if not index_codes_to_process:
                raise ValueError("--index-codes is required for upload action")
            do_upload(
                index_codes_to_process, client, meilisearch_config, args, args.prefix
            )
        case "postprocess":
            index_codes_to_process = args.index_codes
            if not index_codes_to_process:
                raise ValueError("--index-codes is required for postprocess action")
            do_postprocess(
                index_codes_to_process, client, meilisearch_config, args, args.prefix
            )
        case _:
            print("Unexpected argument:", args.action)


if __name__ == "__main__":
    main()
