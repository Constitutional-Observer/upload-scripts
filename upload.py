import argparse
import json
from pathlib import Path

import typesense
from tqdm import tqdm

from metadata_handler import normalize_metadata


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
    state_code = files_path.name
    metadata = files_path / "all_metadata.json"  # JSONL file
    with open(metadata) as f:
        metadata_text = f.read()
    metadata = list(map(json.loads, metadata_text.splitlines()))
    responses = []
    for item in tqdm(metadata):
        for file in item["files"]:
            if file["name"].endswith("_djvu.txt"):
                file_name = file["name"]
                break
        metadata = normalize_metadata(state_code, item["metadata"])
        discussion_text = files_path / "downloads" / file_name
        with open(discussion_text) as f:
            discussion_text = f.read()
        file_chunks = chunk_file(discussion_text)
        items_to_upload = []
        for chunk_id, chunk in enumerate(file_chunks):
            item_to_upload = metadata.copy()
            item_to_upload["id"] = f"{state_code}_{file_name}_{chunk_id}"
            item_to_upload["discussions"] = chunk
            item_to_upload["file_name"] = file_name
            items_to_upload.append(item_to_upload)
        response = client.collections[
            f"state_legislature_debates_{state_code.lower()}"
        ].documents.upsert(item_to_upload)
        responses.append(response)
    with open(f"typesense_upload_{state_code}.json", "w") as f:
        json.dump(responses, f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("filename")
    args = parser.parse_args()

    path = Path(args.filename)

    upload_documents_from_path(path)


if __name__ == "__main__":
    main()
