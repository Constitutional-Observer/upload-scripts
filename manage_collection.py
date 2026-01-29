import argparse
import typesense
from metadata_handler import STATE_CODES, BASE_FIELDS, METADATA_SCHEMA


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


def delete_collections(states):
    client = typesense.Client(TYPESENSE_CONFIG)
    for state_code in states:
        collection_name = f"state_legislature_debates_{state_code.lower()}"
        try:
            client.collections[collection_name].delete()
            print(f"Deleted collection: {collection_name}")
        except Exception as e:
            print(f"Could not delete collection {collection_name}: {e}")


def create_collections(states):
    client = typesense.Client(TYPESENSE_CONFIG)
    for state_code in states:
        collection_name = f"state_legislature_debates_{state_code.lower()}"
        fields = BASE_FIELDS.copy()
        if state_code in METADATA_SCHEMA:
            fields.extend(METADATA_SCHEMA[state_code])

        schema = {
            "name": collection_name,
            "fields": fields,
        }
        try:
            client.collections.create(schema)
            print(f"Created collection: {collection_name}")
        except Exception as e:
            print(f"Could not create collection {collection_name}: {e}")


def print_collections_info(states):
    client = typesense.Client(TYPESENSE_CONFIG)
    for state_code in states:
        collection_name = f"state_legislature_debates_{state_code.lower()}"
        try:
            details = client.collections[collection_name].retrieve()
            print(f"Collection: {collection_name}")
            print(details)
        except Exception as e:
            print(f"Could not retrieve collection {collection_name}: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["delete", "create", "print_schema"])
    parser.add_argument(
        "--states",
        nargs="+",
        help="States to perform action on (e.g. AP TS). Defaults to all if not specified.",
    )
    args = parser.parse_args()

    states = args.states if args.states else STATE_CODES

    match args.action:
        case "delete":
            delete_collections(states)
        case "create":
            create_collections(states)
        case "print_schema":
            print_collections_info(states)
        case _:
            print("Unexpected argument:", args.action)


if __name__ == "__main__":
    main()
