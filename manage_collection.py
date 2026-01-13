import argparse
import typesense


TYPESENSE_CONFIG = {
    "nodes": [
        {
            "host": "localhost",
            "port": "8108",
            "protocol": "http",
        }
    ],
    "api_key": "xyz",
}


def delete_collection():
    client = typesense.Client(TYPESENSE_CONFIG)
    client.collections['legislature_debates'].delete()


def create_collection():
    client = typesense.Client(TYPESENSE_CONFIG)
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
    client.collections.create(schema)


def print_collection_info():
    client = typesense.Client(TYPESENSE_CONFIG)
    details = client.collections['legislature_debates'].retrieve()
    print(details)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["delete", "create", "print_schema"])
    args = parser.parse_args()

    match args.action:
        case "delete":
            delete_collection()
        case "create":
            create_collection()
        case "print_schema":
            print_collection_info()
        case _:
            print("Unexpected argument:", args.action)


if __name__ == "__main__":
    main()
