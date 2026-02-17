import argparse
from pathlib import Path
import meilisearch
from tqdm import tqdm
import json

def chunk_file(file_text: str) -> list[str]:
    """Split file text into chunks by double newlines"""
    return list(file_text.split("\n\n"))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files_path")
    parser.add_argument("--host", default="http://localhost:7700", help="Meilisearch host URL")
    parser.add_argument("--api-key", help="Meilisearch API key (if required)")

    args = parser.parse_args()

    # Initialize Meilisearch client
    meilisearch_config = {
        "host": args.host,
    }
    
    if args.api_key:
        meilisearch_config["api_key"] = args.api_key

    try:
        client = meilisearch.Client(
            meilisearch_config["host"], meilisearch_config.get("api_key")
        )
        # Test connection
        client.health()
    except Exception as e:
        print(f"Failed to connect to Meilisearch: {e}")
        return

    state_code = Path(args.files_path).parents[0].name
    missing_chunks = []

    # Collection name follows the same pattern as upload script
    collection_name = f"state_legislature_debates_{state_code.lower()}"
    
    try:
        collection = client.get_index(collection_name)
    except meilisearch.errors.MeilisearchApiError:
        print(f"Collection {collection_name} does not exist")
        return

    # Read metadata to get file information
    metadata_file = Path(args.files_path) / "all_metadata.json"
    if not metadata_file.exists():
        print(f"Metadata file not found: {metadata_file}")
        return

    with open(metadata_file) as f:
        metadata_text = f.read()
    metadata = list(map(json.loads, metadata_text.splitlines()))

    # Process each metadata item and check for chunks
    for item in tqdm(metadata, desc=f"Checking {state_code} documents"):
        # Find the DJVU text file
        file_name = None
        for file in item.get("files", []):
            if file["name"].endswith("_djvu.txt"):
                file_name = file["name"]
                break

        if not file_name:
            missing_chunks.append({
                "file": "unknown",
                "error": "DJVU file not found in metadata"
            })
            continue

        # Read discussion text to determine chunks
        discussion_text_path = Path(args.files_path) / "downloads" / file_name
        if not discussion_text_path.exists():
            missing_chunks.append({
                "file": file_name,
                "error": "File not found"
            })
            continue

        with open(discussion_text_path) as f:
            discussion_text = f.read()

        file_chunks = chunk_file(discussion_text)

        # Check each chunk in Meilisearch
        for chunk_id, _ in enumerate(file_chunks):
            document_id = f"{state_code}_{file_name}_{chunk_id}"
            try:
                document = collection.get_document(document_id)
                if not document:
                    missing_chunks.append({
                        "file": file_name,
                        "chunk_id": chunk_id,
                        "error": "Document not found"
                    })
            except meilisearch.errors.MeilisearchApiError as e:
                missing_chunks.append({
                    "file": file_name,
                    "chunk_id": chunk_id,
                    "error": str(e)
                })

    with open("missing_chunks.json", "w") as f:
        json.dump(missing_chunks, f)

    print(f"Testing completed for {state_code}")
    print(f"Missing chunks: {len(missing_chunks)}")


if __name__ == "__main__":
    main()
