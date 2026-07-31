"""CLI presentation layer for managing search collections.

This module provides the command-line interface for managing Meilisearch
collections. It is a thin presentation layer that delegates all business
logic to the service layer.

Usage:
    python manage_collection.py <action> [options]

Actions:
    delete      Delete collections
    create     Create/update collections
    print_schema  Print collection information
    upload     Upload/upsert documents
    add        Create collections then upload
    remove     Delete collections (alias for delete)
    postprocess Apply postprocessing to existing documents
"""

import argparse
import sys
import traceback

from config.settings import Settings
from search.meilisearch_backend import MeilisearchBackend
from services.collection_service import CollectionService
from services.postprocess_service import PostprocessService
from services.upload_service import UploadService


def main():
    """Main entry point for the collection management CLI."""
    parser = argparse.ArgumentParser(
        description="Manage Meilisearch collections for legislative debate data"
    )

    # Action argument
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

    # Index selection arguments
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
        "--prefix",
        default="state_legislature_debates",
        help="Prefix for the index name",
    )

    # Upload-specific arguments
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional limit on number of documents to process (for upload action)",
    )
    parser.add_argument(
        "--files-path",
        help="Path to directory containing data all_metadata.json and downloads (default: index_codes_path from config)",
    )
    parser.add_argument(
        "--metadata-path",
        help="Absolute path to metadata JSONL file (default: index_codes_path/all_metadata.json or files_path/all_metadata.json)",
    )

    # Delete-specific argument
    parser.add_argument("--index", help="index to delete")
    parser.add_argument(
        "--index-code",
        help="Index code (optional, can be derived from files_path)",
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

    # Initialize application components
    settings = Settings(args.config)
    backend = MeilisearchBackend(settings.config)

    collection_service = CollectionService(backend, settings)
    upload_service = UploadService(backend, settings)
    postprocess_service = PostprocessService(backend, settings)

    index_codes = args.index_codes

    # Dispatch action to appropriate service
    try:
        match args.action:
            case "delete" | "remove":
                index_names = [args.index] if args.index else []
                collection_service.delete_collections(
                    index_names=index_names,
                    index_codes=index_codes,
                    prefix=args.prefix,
                )

            case "create":
                collection_service.create_collections(
                    index_codes=index_codes,
                    prefix=args.prefix,
                )

            case "print_schema":
                collection_service.print_collections_info(
                    index_codes=index_codes,
                    prefix=args.prefix,
                )

            case "add":
                # Create collections first, then upload
                collection_service.create_collections(
                    index_codes=index_codes,
                    prefix=args.prefix,
                )
                if not index_codes:
                    raise ValueError("--index-codes is required for add action")
                upload_service.do_upload(
                    index_codes_to_process=index_codes,
                    prefix=args.prefix,
                    args=args,
                )

            case "upload":
                if not index_codes:
                    raise ValueError("--index-codes is required for upload action")
                upload_service.do_upload(
                    index_codes_to_process=index_codes,
                    prefix=args.prefix,
                    args=args,
                )

            case "postprocess":
                if not index_codes:
                    raise ValueError("--index-codes is required for postprocess action")
                postprocess_service.do_postprocess(
                    index_codes_to_process=index_codes,
                    prefix=args.prefix,
                    args=args,
                )

            case _:
                print(f"Unexpected argument: {args.action}")
                sys.exit(1)

    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
