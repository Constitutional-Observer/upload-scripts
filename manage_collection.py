#!/usr/bin/env python3

import argparse
import json
import traceback
from pathlib import Path
from more_itertools import batched

import meilisearch
import meilisearch.errors
import meilisearch.index
from tqdm import tqdm
import yaml

from metadata_schema import get_metadata_schema
from metadata_handler import normalize_metadata


def get_client(meilisearch_config: dict) -> meilisearch.Client:
    client = meilisearch.Client(
        meilisearch_config["connection"]["URL"], meilisearch_config["connection"]["API_KEY"]
    )
    # Test connection
    client.health()
    return client


def chunk_file(file_text: str) -> list[str]:
    """Split file text into chunks by double newlines"""
    import re

    MAX_CHUNK_LEN = 200  # 200 words
    current_chunk = ""
    current_chunk_word_count = 0

    # Split on double newlines, preserving empty paragraphs for now
    raw_split_file = re.split(r"\n\n", file_text)
    chunks = []

    for raw_split in raw_split_file:
        # Skip completely empty paragraphs (only whitespace)
        if not raw_split.strip():
            continue

        # Count words using regex that handles all Unicode whitespace
        # This includes regular spaces, non-breaking spaces, tabs, etc.
        words = re.split(r"\s+", raw_split.strip())
        raw_split_word_count = len(words)

        if raw_split_word_count + current_chunk_word_count > MAX_CHUNK_LEN:
            # Start new chunk if current one would exceed limit
            if current_chunk:  # Only add if we have content
                chunks.append(current_chunk)
            current_chunk = raw_split
            current_chunk_word_count = raw_split_word_count
        else:
            # Add to current chunk
            if current_chunk:
                current_chunk += "\n\n" + raw_split
            else:
                current_chunk = raw_split
            current_chunk_word_count += raw_split_word_count

    # Add final chunk if it has content
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


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


def create_collections(states, meilisearch_config: dict, prefix: str = "state_legislature_debates"):
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

            print(f"Created/updated collection: {collection_name}")
            print(f"  Searchable attributes: {searchable_attributes}")
            print(f"  Filterable attributes: {filterable_attributes}")
            print(f"  Sortable attributes: {sortable_attributes}")
        except Exception as e:
            print(f"Could not create/update collection {collection_name}: {e}")

    if (
        "index_config" in meilisearch_config
        and "embeddings" in meilisearch_config["index_config"]
    ):
        collection.update_embedders(meilisearch_config["index_config"]["embeddings"])


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


def _get_metadata(metadata_file: Path) -> list[dict]:
    """
    Fetch metadata JSONL file
    """
    if not metadata_file.exists():
        raise FileNotFoundError(f"Metadata file not found: {metadata_file}")

    with open(metadata_file) as f:
        metadata_text = f.read()
    metadata = list(map(json.loads, metadata_text.splitlines()))
    return metadata


def _find_djvu_file(files: list[dict[str, str]]) -> str | None:
    file_name = None
    for file in files:
        if file["name"].endswith("_djvu.txt"):
            file_name = file["name"]
            break

    return file_name


def _upload_one_document(
    item: dict,
    state_code: str,
    files_path: Path,
    collection: meilisearch.index.Index,
):
    # Find the DJVU text file
    file_name = _find_djvu_file(item.get("files", []))

    if not file_name:
        metadata_error = {"item": item, "error": "DJVU file not found"}
        return metadata_error, {}

    try:
        # Normalize metadata
        metadata_dict = normalize_metadata(state_code, item["metadata"])
    except Exception as e:
        traceback.print_exc()
        return {"file": file_name, "error": str(e)}

    # Read discussion text
    discussion_text_path = files_path / "downloads" / file_name
    if not discussion_text_path.exists():
        return {"file": file_name, "error": "File not found"}

    with open(discussion_text_path) as f:
        discussion_text = f.read()

    file_chunks = chunk_file(discussion_text)

    # Prepare documents for Meilisearch
    documents = []
    for chunk_id, chunk in enumerate(file_chunks):
        document = {
            "id": f"{state_code}_{file_name.replace('.', '_')}_{chunk_id}",
            "state_code": state_code,
            "file_name": file_name,
            "chunk_id": chunk_id,
            "__discussions": chunk,
            **metadata_dict,
        }
        documents.append(document)

    # Upload documents in batches
    try:
        # Use larger batch size for better performance
        batch_size = 100000
        task_ids = []
        counts = 0

        for i, batch in enumerate(batched(documents, batch_size)):
            task = collection.add_documents(batch, primary_key="id")
            task_ids.append(task.task_uid)
            counts += len(batch)

        return {}, {
            "success": True,
            "count": counts,
            "task_ids": task_ids
        }

        # Wait for all tasks to complete at the end (optional)
        # This can be commented out for even faster uploads
        # for task_id in task_ids:
        #     client.wait_for_task(task_id)

    except Exception as e:
        print(f"Error uploading documents: {e}")
        return {}, {"success": False, "error": str(e), "documents": len(documents)}


def upload_documents_from_path(
    files_path: Path,
    meilisearch_config: dict,
    limit: int | None = None,
    prefix: str = "state_legislature_debates",
) -> None:
    """Upload documents from a state directory to Meilisearch

    Args:
        files_path: Path to state directory containing data
        meilisearch_config: Meilisearch configuration
        limit: Optional limit on number of documents to process
        prefix: Prefix for the index name
    """
    state_code = files_path.name

    metadata_file = files_path / "all_metadata.json"
    metadata = _get_metadata(metadata_file)
    client = get_client(meilisearch_config)

    responses = []
    metadata_errors = []

    collection_name = f"{prefix}_{state_code.lower()}"

    try:
        collection = client.get_index(collection_name)
    except meilisearch.errors.MeilisearchApiError as e:
        print(f"Unable to get collection: {e}")
        return

    metadata_to_process = metadata[:limit] if limit else metadata

    for item in tqdm(metadata_to_process, desc=f"Processing {state_code} documents"):
        results = _upload_one_document(item, state_code, files_path, collection)
        responses.append(results[1])

    # Save responses and errors
    with open(f"meilisearch_upload_{state_code}.json", "w") as f:
        json.dump(responses, f)
    with open(f"{state_code}_metadata_errors.json", "w") as f:
        json.dump(metadata_errors, f)

    print(f"Upload completed for {state_code}")
    print(
        f"Total documents processed: {sum(r.get('count', 0) for r in responses if r.get('success'))}"
    )
    print(f"Metadata errors: {len(metadata_errors)}")


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
        default="meilisearch_config.yaml"
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
        "files_path",
        nargs="?",
        help="Path to directory containing data all_metadata.json and downloads (required for upload action)",
    )
    parser.add_argument(
        "--index",
        help="index to delete"
    )

    args = parser.parse_args()

    # Meilisearch configuration
    with open(args.config) as f:
        meilisearch_config = yaml.safe_load(f)

    states = args.states

    match args.action:
        case "delete":
            delete_collections([args.index], meilisearch_config)
        case "create":
            create_collections(states, meilisearch_config, args.prefix)
        case "print_schema":
            print_collections_info(states, meilisearch_config)
        case "upload":
            if not args.files_path:
                parser.error("--files_path is required for upload action")
            path = Path(args.files_path)
            upload_documents_from_path(path, meilisearch_config, args.limit, args.prefix)
        case _:
            print("Unexpected argument:", args.action)


if __name__ == "__main__":
    main()
