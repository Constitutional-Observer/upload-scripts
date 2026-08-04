"""Processor service for document processing.

This module provides the processor factory functionality and document processing
capabilities, extracting this logic from the presentation layer.
"""

import json
from collections.abc import Callable, Iterator
from pathlib import Path

from processors.base import DocumentProcessor
from processors.functional_pipeline import (
    ChunkConfig,
    FetchConfig,
    process_index,
)
from processors.postprocessing import (
    PostprocessConfig,
    StepConfig,
    resolve_postprocess_config,
    step_registry,
)


def create_processor(
    processor_name: str,
    index_code: str,
    files_path: Path,
    metadata_path: Path,
    meilisearch_config: dict,
    index_config: dict,
) -> DocumentProcessor:
    """Factory function to create document processors.

    This provides a single entry point for creating all types of processors,
    ensuring they all conform to the DocumentProcessor protocol.

    To add a new processor type (e.g., for API-based sources like Lok Sabha):
    1. Add a new case to the match statement below
    2. Create a metadata_iterator function that yields metadata dicts
    3. Create a file_resolver function: (file_name: str, metadata: dict) -> Path
    4. Pass both to process_index with appropriate fetch_config

    Args:
        processor_name: Name of the processor type ("functional", or custom)
        index_code: Index code (e.g., "AP", "KA")
        files_path: Path to directory containing data files (optional for some processors)
        metadata_path: Path to metadata JSONL file (optional for some processors)
        meilisearch_config: Full Meilisearch configuration
        index_config: Index-specific configuration (can contain custom keys for processors)

    Returns:
        A DocumentProcessor instance (callable that yields document dicts)

    Raises:
        ValueError: If processor_name is unknown
    """
    match processor_name:
        case "functional":
            # Extract configuration options
            run_ner = index_config.get("run_ner", False)
            chunk_config_dict = index_config.get("chunk_config", None)
            extractor = index_config.get("extractor", "text")

            # NEW: Resolve postprocessing configuration
            global_config = meilisearch_config.get("index_config", {}).get("global", {})
            index_code_config = meilisearch_config.get("index_config", {}).get(
                index_code, {}
            )

            postprocess_config = resolve_postprocess_config(
                global_config=global_config,
                index_code_config=index_code_config,
                variant_config=index_config,
            )

            # If run_ner is True but postprocessing is disabled, enable it with NER step
            if run_ner and not postprocess_config.enabled:
                postprocess_config = PostprocessConfig(
                    enabled=True, steps=[StepConfig(name="ner", enabled=True)]
                )
            elif run_ner and not postprocess_config.has_step("ner"):
                # Add NER step if run_ner is True but NER step isn't configured
                postprocess_config.steps.append(StepConfig(name="ner", enabled=True))

            # Build fetch config (no file_resolver for file-based sources)
            fetch_config = FetchConfig(
                files_path=files_path,
                metadata_path=metadata_path,
                file_resolver=None,
            )

            # Build chunk config if provided
            chunk_config = (
                ChunkConfig(**chunk_config_dict) if chunk_config_dict else None
            )

            # Create a callable generator function that conforms to DocumentProcessor
            def functional_processor(
                limit: int | None = None,
                on_error: Callable[[str, str], None] | None = None,
            ) -> Iterator[dict]:
                """Generator function for functional pipeline."""

                # Create metadata iterator that reads from JSONL file line by line
                def metadata_iterator():
                    if not metadata_path.exists():
                        raise FileNotFoundError(
                            f"Metadata file not found: {metadata_path}"
                        )
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        for line in f:
                            yield json.loads(line)

                for doc in process_index(
                    index_code=index_code,
                    metadata_iterator=metadata_iterator(),
                    fetch_config=fetch_config,
                    limit=limit,
                    chunk_config=chunk_config,
                    run_ner=run_ner,
                    extractor=extractor,
                    on_error=on_error,
                    postprocess_config=postprocess_config,
                    step_registry=step_registry,
                ):
                    yield doc.to_dict()

            return functional_processor

        case _:
            raise ValueError(
                f"Unknown processor: {processor_name}. Known processors: functional"
            )
