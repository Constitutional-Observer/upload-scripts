import argparse
import json
from more_itertools import chunked
from pathlib import Path

import typesense
from tqdm import tqdm

def create_collection():
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
        }
    )
    schema = {
        "name": "legislature_debates",
        "fields": [
            { "name": "state_code", "type": "string" },
            { "name": "file_name", "type": "string" },
            {
                "name": "discussion",
                "type": "string",
            },
        ],
    }

    try:
        client.collections['legislature_debates'].retrieve()
    except Exception:
        print("Collection does not exist, will be created")
        client.collections.create(schema)
        print("Created collection!")
    else:
        print("Collection already exists")

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
    state_code = files_path.stem[-2].split("-")[0]
    files = list(files_path.iterdir())
    failures = []

    for file_batch in tqdm(chunked(enumerate(files), 10), total=len(files) // 10):
        docs_to_upload = []
        for i, file in file_batch:
            with open(file) as f:
                text = f.read()
            docs_to_upload.append({"id": str(i), "state_code": state_code, "file_name": file.name, "discussion": text})
        result = client.collections["legislature_debates"].documents.import_(docs_to_upload)
        if not all(map(lambda x: x["success"], result)):
            print("failed to upload: ", file_batch)
            failures.append(result)

    if len(failures) > 0:
        print("Some errors occured while uploading the files. Error log will be written to 'errors.json'")
        with open("errors.json", "w") as f:
            json.dump(failures, f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("filename")
    args = parser.parse_args()

    path = Path(args.filename)

    create_collection()
    upload_documents_from_path(path)

if __name__ == "__main__":
    main()
