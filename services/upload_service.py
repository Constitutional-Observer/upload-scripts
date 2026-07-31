"""Upload service for document indexing.

This module provides business logic for uploading documents to the search backend.
It handles batching, progress tracking, and error management.
"""

import json
import logging
from typing import Any

from more_itertools import batched
from tqdm import tqdm

from config.settings import Settings
from processors.base import DocumentProcessor
from search.base import SearchBackend

logger = logging.getLogger(__name__)


class UploadService:
    """Service for uploading documents to the search backend.

    This service handles the orchestration of document uploads, including
    batching, progress tracking, and error management.
    """

    def __init__(self, backend: SearchBackend, settings: Settings):
        """Initialize the upload service.

        Args:
            backend: The search backend to use for uploads.
            settings: The settings object for configuration.
        """
        self.backend = backend
        self.settings = settings

    def upload_from_processor(
        self,
        processor: DocumentProcessor,
        index_name: str,
        batch_size: int = 1000,
        use_tqdm: bool = True,
        limit: int | None = None,
        progress_desc: str = "processing",
        total_for_progress: int | None = None,
        prefix: str = "state_legislature_debates",
    ) -> tuple[int, list[dict], list[dict]]:
        """Upload (upsert) documents from a DocumentProcessor to the search backend.

        Documents are added using the backend's add_documents method which performs
        an upsert: if a document with the same primary key (id) already exists, it is
        updated; otherwise, it is inserted.

        Args:
            processor: A DocumentProcessor instance (callable that yields document dicts)
            index_name: Name of the search index
            batch_size: Number of documents per batch
            use_tqdm: Whether to show progress bar
            limit: Maximum number of source items to process
            progress_desc: Description string for the progress bar
            total_for_progress: Total count for progress bar (optional)
            prefix: Prefix for index names (used for saving response files)

        Returns:
            Tuple of (total_documents_uploaded, list of response dicts, list of file errors)
        """
        responses = []
        task_ids = []
        total_count = 0
        file_errors: list[dict[str, str]] = []

        # Callback to collect file errors from processor
        def collect_error(file_identifier: str, error_msg: str):
            file_errors.append({"file": file_identifier, "error": error_msg})

        # Get document iterator from processor
        doc_iter = processor(limit=limit, on_error=collect_error)

        # Wrap with tqdm if requested - stream directly, don't collect all docs
        if use_tqdm:
            doc_iter = tqdm(
                doc_iter,
                desc=f"Processing {progress_desc}",
                total=total_for_progress,
            )

        # Stream directly into batches - NEVER collect all docs in memory
        for batch in batched(doc_iter, batch_size):
            batch_list = list(batch)

            if not batch_list:
                continue

            try:
                task = self.backend.add_documents(
                    index_name, batch_list, primary_key="id"
                )
                task_uid = task.task_uid if hasattr(task, "task_uid") else str(task)
                task_ids.append(task_uid)
                total_count += len(batch_list)
                responses.append(
                    {"success": True, "count": len(batch_list), "task_id": task_uid}
                )
            except Exception as e:
                logger.error(
                    f"Failed to upload batch to {index_name} "
                    f"(index_code: {progress_desc}, batch_size: {len(batch_list)}): {e}"
                )
                responses.append(
                    {"success": False, "error": str(e), "count": len(batch_list)}
                )
                # Record errors for all documents in this failed batch
                for doc in batch_list:
                    file_errors.append(
                        {"file": doc.get("file_name", "unknown"), "error": str(e)}
                    )

        return total_count, responses, file_errors

    def do_upload(
        self,
        index_codes_to_process: list[str],
        prefix: str,
        args: Any,
    ) -> None:
        """Execute the upload (upsert) workflow for the given index codes.

        For each index code, processes documents through the configured processor
        and upserts them into the search backend.

        Args:
            index_codes_to_process: List of index codes to process.
            prefix: Prefix for index names.
            args: Command line arguments namespace.
        """
        from services.processor_service import create_processor

        # Get all index configs
        all_index_configs = self.settings.get_index_configs(prefix)

        for index_code in index_codes_to_process:
            # Get all indexes for this index_code
            index_code_index_configs = [
                (name, config)
                for name, ic, config in all_index_configs
                if ic == index_code
            ]

            if not index_code_index_configs:
                print(f"Warning: No index configs found for index code {index_code}")
                continue

            for index_name, index_config in index_code_index_configs:
                print(
                    f"\n=== Uploading to index: {index_name} (index_code: {index_code}) ==="
                )

                # Resolve paths from index config (falling back to index_code config)
                files_path = self.settings.resolve_files_path(
                    args.files_path if hasattr(args, "files_path") else None,
                    index_code,
                    index_config,
                )
                metadata_path = self.settings.resolve_metadata_path(
                    args.metadata_path if hasattr(args, "metadata_path") else None,
                    index_code,
                    files_path,
                    index_config,
                )

                # Get processor type from config (default: functional)
                processor_name = index_config.get("processor", "functional")

                # Get total for progress bar
                total_for_progress = self.settings.get_metadata_count(
                    metadata_path, args.limit if hasattr(args, "limit") else None
                )

                # Create processor using factory
                processor = create_processor(
                    processor_name=processor_name,
                    index_code=index_code,
                    files_path=files_path,
                    metadata_path=metadata_path,
                    meilisearch_config=self.settings.config,
                    index_config=index_config,
                )

                # Get batch size from config
                batch_size = self.settings.get_batch_size(index_code)

                # Upload documents
                try:
                    total_count, responses, file_errors = self.upload_from_processor(
                        processor,
                        index_name,
                        batch_size=batch_size,
                        use_tqdm=True,
                        limit=args.limit if hasattr(args, "limit") else None,
                        progress_desc=index_code,
                        total_for_progress=total_for_progress,
                        prefix=prefix,
                    )

                    # Save batch responses for debugging
                    response_filename = f"meilisearch_upload_{index_code}_{index_name.replace(prefix + '_', '')}.json"
                    with open(response_filename, "w") as f:
                        json.dump(responses, f)

                    # Save file errors to metadata errors file
                    error_filename = f"metadata_errors_{index_code}.json"
                    with open(error_filename, "w") as f:
                        json.dump(file_errors, f)

                    # Count successful uploads
                    success_count = sum(
                        r["count"] for r in responses if r.get("success")
                    )
                    error_count = sum(1 for r in responses if not r.get("success"))

                    print(f"Upload completed for {index_name}")
                    print(f"  Total chunks uploaded: {total_count}")
                    print(
                        f"  Batch responses: {len(responses)} ({success_count} successful, {error_count} errors)"
                    )
                    print(f"  File errors saved to: {error_filename}")

                except Exception as e:
                    print(f"Error processing index {index_name}: {e}")
                    import traceback

                    traceback.print_exc()
