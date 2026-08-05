"""Postprocessing service for document enrichment.

This module provides business logic for applying postprocessing steps to
 existing documents in the search backend.
"""

from typing import Any

from config.settings import Settings
from processors.postprocessing import (
    PostprocessConfig,
    resolve_postprocess_config,
    run_postprocessing_steps,
    step_registry,
)
from search.base import SearchBackend


class PostprocessService:
    """Service for applying postprocessing to existing documents.

    This service fetches documents from the search backend and runs configured
    postprocessing steps on them, then updates the documents with the results.
    """

    def __init__(self, backend: SearchBackend, settings: Settings):
        """Initialize the postprocess service.

        Args:
            backend: The search backend to use for operations.
            settings: The settings object for configuration.
        """
        self.backend = backend
        self.settings = settings

    def resolve_postprocess_config(
        self,
        index_code: str,
        index_config: dict,
    ) -> PostprocessConfig:
        """Resolve postprocessing configuration for an index.

        Args:
            index_code: The index code.
            index_config: Index-specific configuration.

        Returns:
            Resolved PostprocessConfig object.
        """
        global_config = self.settings.get_global_config()
        index_code_config = self.settings.get_index_code_config(index_code)

        return resolve_postprocess_config(
            global_config=global_config,
            index_code_config=index_code_config,
            variant_config=index_config,
        )

    def do_postprocess(
        self,
        index_codes_to_process: list[str],
        prefix: str,
        args: Any,
    ) -> None:
        """Apply postprocessing to existing documents in the search backend.

        Fetches documents from the search backend for the specified index codes and runs
        configured postprocessing steps on them. Documents are updated in place
        with the results of the postprocessing steps.

        Args:
            index_codes_to_process: List of index codes to process.
            prefix: Index name prefix.
            args: Command line arguments namespace.
        """
        # Get all index configs
        all_index_configs = self.settings.get_index_configs(prefix)

        for index_code in index_codes_to_process:
            # Get the single index config for this index_code
            index_code_index_configs = [
                (name, ic, config)
                for name, ic, config in all_index_configs
                if ic == index_code
            ]

            if not index_code_index_configs:
                print(f"Warning: No index configs found for index code {index_code}")
                continue

            # With the new structure, there should be only one index per index_code
            index_name, _, index_config = index_code_index_configs[0]
            print(
                f"\n=== Postprocessing index: {index_name} (index_code: {index_code}) ==="
            )

            # Resolve postprocessing config for this index
            postprocess_config = self.resolve_postprocess_config(
                index_code, index_config
            )

            if not postprocess_config.enabled:
                print(f"  Postprocessing disabled for {index_name}, skipping")
                continue

            if not postprocess_config.get_enabled_steps():
                print(f"  No enabled postprocessing steps for {index_name}, skipping")
                continue

            # Get total document count for progress tracking
            try:
                stats = self.backend.get_stats(index_name)
                total_docs = stats.get("numberOfDocuments", 0)
                print(f"  Processing {total_docs} documents...")
            except Exception as e:
                print(f"  Could not get document count: {e}")
                total_docs = None

            # Process documents in pages
            page_size = getattr(args, "page_size", 200)
            batch_size = getattr(args, "batch_size", 200)
            force = getattr(args, "force", False)

            processed = 0
            skipped = 0
            pending_updates: list[dict] = []

            def flush_updates():
                """Flush pending updates to search backend."""
                if pending_updates:
                    try:
                        self.backend.update_documents(
                            index_name, pending_updates, primary_key="id"
                        )
                        pending_updates.clear()
                    except Exception as e:
                        print(f"  Failed to update batch: {e}")

            # Fetch and process documents
            offset = 0
            while True:
                try:
                    docs, total = self.backend.get_documents(
                        index_name,
                        offset=offset,
                        limit=page_size,
                    )
                    if not docs:
                        break

                    for doc in docs:
                        doc_id = doc.get("id")
                        if not doc_id:
                            skipped += 1
                            continue

                        # Extract fields from document
                        text = doc.get("__discussions") or doc.get("discussions", "")
                        file_name = doc.get("file_name", "unknown")
                        chunk_id = doc.get("chunk_id", 0)
                        metadata = {
                            k: v
                            for k, v in doc.items()
                            if k
                            not in [
                                "id",
                                "__discussions",
                                "discussions",
                                "file_name",
                                "chunk_id",
                                "entities",
                                "_ner",
                            ]
                        }

                        # Check if already processed (skip unless force)
                        if not force:
                            # Check if any of the configured steps' output fields already exist
                            skip = True
                            for step_config in postprocess_config.get_enabled_steps():
                                output_field = step_config.config.get(
                                    "output_field", step_config.name
                                )
                                if output_field not in doc:
                                    skip = False
                                    break
                            if skip:
                                skipped += 1
                                continue

                        # Run postprocessing steps
                        step_results = run_postprocessing_steps(
                            chunk=text,
                            file_name=file_name,
                            chunk_id=chunk_id,
                            metadata=metadata,
                            config=postprocess_config,
                            registry=step_registry,
                        )

                        if step_results:
                            update_doc = {"id": doc_id, **step_results}
                            pending_updates.append(update_doc)

                        processed += 1

                        # Flush if batch size reached
                        if len(pending_updates) >= batch_size:
                            flush_updates()

                    offset += len(docs)
                    if total_docs and offset >= total_docs:
                        break

                except Exception as e:
                    print(f"  Error fetching documents at offset {offset}: {e}")
                    break

            # Flush any remaining updates
            flush_updates()

            print(f"  Postprocessing completed for {index_name}")
            print(f"    Processed: {processed}, Skipped: {skipped}")
