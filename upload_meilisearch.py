#!/usr/bin/env python3

import argparse
import json
import traceback
from pathlib import Path
from more_itertools import batched

import meilisearch
from tqdm import tqdm

from metadata_handler import normalize_metadata


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


def upload_documents_from_path(
    files_path: Path, meilisearch_config: dict, limit: int = None, prefix: str = "state_legislature_debates"
):
    """Upload documents from a state directory to Meilisearch

    Args:
        files_path: Path to state directory containing data
        meilisearch_config: Meilisearch configuration
        limit: Optional limit on number of documents to process
        prefix: Prefix for the index name
    """
    if not files_path.is_dir():
        print("Invalid path, expected a directory with files")
        return

    # Initialize Meilisearch client
    try:
        client = meilisearch.Client(
            meilisearch_config["host"], meilisearch_config.get("api_key")
        )
        # Test connection
        client.health()
    except Exception as e:
        print(f"Failed to connect to Meilisearch: {e}")
        return

    state_code = files_path.name

    # Read metadata
    metadata_file = files_path / "all_metadata.json"
    if not metadata_file.exists():
        print(f"Metadata file not found: {metadata_file}")
        return

    with open(metadata_file) as f:
        metadata_text = f.read()
    metadata = list(map(json.loads, metadata_text.splitlines()))

    responses = []
    metadata_errors = []

    # Collection name follows the same pattern as other upload scripts
    collection_name = f"{prefix}_{state_code.lower()}"

    # Create or get collection
    try:
        # Check if collection exists
        collection = client.get_index(collection_name)
        print(f"Using existing collection: {collection_name}")
    except meilisearch.errors.MeilisearchApiError:
        # Create new collection
        print(f"Creating new collection: {collection_name}")
        collection = client.index(collection_name)

        # Set up searchable and filterable attributes based on metadata schema
        from metadata_handler import METADATA_SCHEMA

        # Base searchable attributes
        searchable_attributes = ["__discussions", "title_en"]
        filterable_attributes = ["state_code", "year", "month", "day"]
        sortable_attributes = ["year", "month", "day"]

        # Add state-specific searchable attributes
        if state_code in METADATA_SCHEMA:
            for field in METADATA_SCHEMA[state_code]:
                field_name = field["name"]
                if field_name not in searchable_attributes:
                    searchable_attributes.append(field_name)
                if field.get("facet"):
                    filterable_attributes.append(field_name)

        # Update collection settings
        collection.update_searchable_attributes(searchable_attributes)
        collection.update_filterable_attributes(filterable_attributes)
        collection.update_sortable_attributes(sortable_attributes)
        # collection.update_distinct_attribute("file_name")

    # Process and upload documents
    metadata_to_process = metadata[:limit] if limit else metadata
    for item in tqdm(metadata_to_process, desc=f"Processing {state_code} documents"):
        # Find the DJVU text file
        file_name = None
        for file in item.get("files", []):
            if file["name"].endswith("_djvu.txt"):
                file_name = file["name"]
                break

        if not file_name:
            metadata_errors.append({"item": item, "error": "DJVU file not found"})
            continue

        try:
            # Normalize metadata
            metadata_dict = normalize_metadata(state_code, item["metadata"])
        except Exception as e:
            traceback.print_exc()
            metadata_errors.append({"file": file_name, "error": str(e)})
            continue

        # Read discussion text
        discussion_text_path = files_path / "downloads" / file_name
        if not discussion_text_path.exists():
            metadata_errors.append({"file": file_name, "error": "File not found"})
            continue

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
        if documents:
            try:
                # Use larger batch size for better performance
                batch_size = 1000  # Increased from 1000
                task_ids = []

                for i, batch in enumerate(batched(documents, batch_size)):
                    task = collection.add_documents(batch, primary_key="id")
                    task_ids.append(task.task_uid)
                    responses.append(
                        {
                            "success": True,
                            "batch": i,
                            "count": len(batch),
                            "task_id": task.task_uid,
                        }
                    )

                # Wait for all tasks to complete at the end (optional)
                # This can be commented out for even faster uploads
                # for task_id in task_ids:
                #     client.wait_for_task(task_id)

            except Exception as e:
                print(f"Error uploading documents: {e}")
                responses.append(
                    {"success": False, "error": str(e), "documents": len(documents)}
                )

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
        description="Upload legislative debate data to Meilisearch"
    )
    parser.add_argument("filename", help="Path to state directory containing data")
    parser.add_argument(
        "--host", default="http://localhost:7700", help="Meilisearch host URL"
    )
    parser.add_argument("--api-key", help="Meilisearch API key (if required)")
    parser.add_argument(
        "--limit", type=int, help="Optional limit on number of documents to process"
    )
    parser.add_argument("--prefix", default="state_legislature_debates", help="Prefix for the index name")

    args = parser.parse_args()

    # Meilisearch configuration
    meilisearch_config = {
        "host": args.host,
    }

    if args.api_key:
        meilisearch_config["api_key"] = args.api_key

    path = Path(args.filename)
    upload_documents_from_path(path, meilisearch_config, args.limit, args.prefix)


if __name__ == "__main__":
    main()
