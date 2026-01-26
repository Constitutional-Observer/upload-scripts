import argparse
import json
from more_itertools import chunked
from pathlib import Path

import typesense
from tqdm import tqdm

from metadata_handler import get_state_metadata


def chunk_file(file_text: str) -> list[str]:
    return list(file_text.split("\n\n"))

def upload_documents_from_path(files_path: Path):
    if not files_path.is_dir():
        print("Invalid path, expected a directory with files")
    client = typesense.Client(
        {
            "nodes": [
                {
                    "host": "localhost",  # IP address of Typesense server
                    "port": "8108",  # Default port
                    "protocol": "http",  # or 'https'
                }
            ],
            "api_key": "xyz",  # API key for accessing your Typesense server
            "connection_timeout_seconds": 5,
        }
    )
    metadata = files_path / "all_metadata.json" # JSONL file
    with open(metadata) as f:
        metadata_text = f.read()
    metadata = map(json.loads, metadata_text.splitlines())
    for item in metadata:
        for file in item["files"]:
            if file["name"].endswith("_djvu.txt"):
                file_name = file["name"]
                break
        metadata = get_state_metadata(item["state_code"], item["metadata"])
        discussion_text = files_path / "downloads" / file_name
        with open(discussion_text) as f:
            discussion_text = f.read()
        file_chunks = chunk_file(discussion_text)
        for chunk_id, chunk in enumerate(file_chunks):
            item_to_upload = metadata.copy()
            item_to_upload["id"] = f"{item['state_code']}_{file_name}_{chunk_id}"
            item_to_upload["discussions"] = chunk
            client.collections["legislature"]["documents"].import_(item_to_upload)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("filename")
    args = parser.parse_args()

    path = Path(args.filename)

    create_collection()
    upload_documents_from_path(path)

if __name__ == "__main__":
    main()
