"""Document processors for legislative debate data.

This module provides a functional pipeline approach with explicit inputs and
dependency order for processing legislative debate data.
"""

from .base import DocumentProcessor
from .functional_pipeline import (
    ChunkConfig,
    ChunkResult,
    Document,
    ExtractResult,
    FetchConfig,
    FetchResult,
    NerResult,
    PipelineConfig,
    chunk_text,
    process_index,
    run_full_pipeline,
    run_postprocessing,
    run_preprocessing,
)
from .postprocessing import (
    DEFAULT_NER_MODEL,
    PostprocessConfig,
    PostprocessingStep,
    StepConfig,
    StepRegistry,
    resolve_postprocess_config,
    run_postprocessing_steps,
    step_registry,
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
    # Postprocessing
    "PostprocessingStep",
    "StepConfig",
    "PostprocessConfig",
    "StepRegistry",
    "step_registry",
    "resolve_postprocess_config",
    "run_postprocessing_steps",
    "DEFAULT_NER_MODEL",
]
