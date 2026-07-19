"""Document processors for legislative debate data.

This module provides a functional pipeline approach with explicit inputs and
dependency order for processing legislative debate data.
"""

from .base import DocumentProcessor
from .functional_pipeline import (
    FetchConfig,
    ChunkConfig,
    PipelineConfig,
    Document,
    FetchResult,
    ExtractResult,
    ChunkResult,
    NerResult,
    run_preprocessing,
    run_postprocessing,
    run_full_pipeline,
    process_index,
    chunk_text,
)

__all__ = [
    "DocumentProcessor",
    # Functional pipeline
    "FetchConfig",
    "ChunkConfig",
    "PipelineConfig",
    "Document",
    "FetchResult",
    "ExtractResult",
    "ChunkResult",
    "NerResult",
    "run_preprocessing",
    "run_postprocessing",
    "run_full_pipeline",
    "process_index",
    "chunk_text",
]
