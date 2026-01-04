import argparse
from itertools import batched
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
        "name": "up_legislature",
        "fields": [
            {"name": "year", "type": "int32", "facet": True},
            {"name": "month", "type": "int32", "facet": True},
            {"name": "day", "type": "int32", "facet": True},
            {
                "name": "discussion",
                "type": "string",
                "locale": "hi",
            },
        ],
        "default_sorting_field": "year",
    }

    client.collections["up_legislature"].delete()
    client.collections.create(schema)

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
    files = list(files_path.iterdir())
    for file_batch in tqdm(batched(enumerate(files), 10), total=len(files) // 10):
        docs_to_upload = []
        for i, file in file_batch:
            day, month, year = map(int, file.name.split("_")[0].split("-"))
            with open(file) as f:
                text = f.read()
            docs_to_upload.append({"id": str(i), "year": year, "month": month, "day": day, "discussion": text})
        result = client.collections["up_legislature"].documents.import_(docs_to_upload)
        if not all(map(lambda x: x["success"], result)):
            print("failed to upload: ", file_batch)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("filename")
    args = parser.parse_args()

    path = Path(args.filename)

    create_collection()
    upload_documents_from_path(path)

if __name__ == "__main__":
    main()
