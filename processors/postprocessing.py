"""Postprocessing framework for document processing pipeline.

This module provides a modular postprocessing system where each step is a callable
that takes document data and returns fields to merge into the final document.

Steps run sequentially and each returns a dictionary of fields to add or update.
The system supports configurable postprocessing at global, index_code, and variant levels.
"""

import logging
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Default model for NER
DEFAULT_NER_MODEL = "ai4bharat/IndicNER"


@runtime_checkable
class PostprocessingStep(Protocol):
    """Protocol for postprocessing steps.

    A postprocessing step is a callable that processes a chunk of text
    and returns a dictionary of fields to merge into the document.
    """

    def __call__(
        self, chunk: str, file_name: str, chunk_id: int, metadata: dict, **kwargs
    ) -> dict:
        """Process a chunk and return fields to merge into the document.

        Args:
            chunk: The text chunk to process
            file_name: Original file name
            chunk_id: Chunk index within the file
            metadata: Normalized metadata dictionary
            **kwargs: Step-specific configuration

        Returns:
            Dictionary with fields to add or update on the document.
        """
        ...


@dataclass
class StepConfig:
    """Configuration for a single postprocessing step."""

    name: str
    enabled: bool = True
    # Additional step-specific configuration
    config: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> StepConfig:
        """Create StepConfig from dictionary."""
        return cls(
            name=data.get("name", ""),
            enabled=data.get("enabled", True),
            config={k: v for k, v in data.items() if k not in ("name", "enabled")},
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {"name": self.name, "enabled": self.enabled}
        result.update(self.config)
        return result


@dataclass
class PostprocessConfig:
    """Configuration for postprocessing pipeline.

    This configuration supports hierarchical merging from global, index_code,
    and variant-level settings.
    """

    enabled: bool = False
    steps: list[StepConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict | None) -> PostprocessConfig:
        """Create PostprocessConfig from dictionary or None."""
        if data is None:
            return cls()

        steps = []
        if "steps" in data:
            for step_data in data["steps"]:
                if isinstance(step_data, dict):
                    steps.append(StepConfig.from_dict(step_data))

        return cls(enabled=data.get("enabled", True), steps=steps)

    def merge_with(self, other: PostprocessConfig) -> PostprocessConfig:
        """Merge another config into this one, with other taking precedence.

        Steps are merged by name: if a step with the same name exists in other,
        it replaces the one in self. Otherwise, it's appended.
        """
        if not other:
            return self

        # Determine if enabled
        enabled = other.enabled if hasattr(other, "enabled") else self.enabled

        # Build merged steps list
        # Start with steps from self that aren't overridden by other
        self_steps_by_name = {s.name: s for s in self.steps if s.name}
        other_steps_by_name = {s.name: s for s in other.steps if s.name}

        # Other's steps take precedence
        merged_steps = []

        # First, add steps from other
        for step in other.steps:
            merged_steps.append(step)

        # Then add steps from self that aren't in other
        for name, step in self_steps_by_name.items():
            if name not in other_steps_by_name:
                merged_steps.append(step)

        return PostprocessConfig(enabled=enabled, steps=merged_steps)

    def get_enabled_steps(self) -> list[StepConfig]:
        """Return only enabled steps."""
        return [s for s in self.steps if s.enabled]

    def has_step(self, name: str) -> bool:
        """Check if a step with the given name is configured and enabled."""
        return any(s.name == name and s.enabled for s in self.steps)


# =============================================================================
# Built-in Postprocessing Steps
# =============================================================================


def ner_step(
    chunk: str,
    file_name: str,
    chunk_id: int,
    metadata: dict,
    model: str = DEFAULT_NER_MODEL,
    output_field: str = "entities",
    device: str | None = None,
    **kwargs,
) -> dict:
    """Run Named Entity Recognition on a text chunk.

    This is a built-in step that uses the IndicNER model for entity extraction.
    Results are returned in a dictionary with the specified output field.

    Args:
        chunk: The text chunk to process
        file_name: Original file name
        chunk_id: Chunk index within the file
        metadata: Normalized metadata
        model: HuggingFace model identifier
        output_field: Name of the field to store entities in
        device: Torch device (cuda, mps, cpu, or None for auto)
        **kwargs: Additional step configuration (ignored)

    Returns:
        Dictionary with the output field containing the list of entities
    """
    # Lazy import to avoid loading torch/transformers at module load time
    from .ner_step_impl import extract_ner_entities

    if not chunk or not chunk.strip():
        logger.debug(f"Skipping NER for empty chunk: {file_name}:{chunk_id}")
        return {output_field: []}

    try:
        entities = extract_ner_entities(chunk, model=model, device=device)
        logger.debug(f"Extracted {len(entities)} entities from {file_name}:{chunk_id}")
        return {output_field: entities}
    except Exception as e:
        logger.error(f"NER failed for {file_name}:{chunk_id}: {e}")
        return {output_field: []}


# Registry of built-in postprocessing steps
BUILTIN_STEPS: dict[str, PostprocessingStep] = {
    "ner": ner_step,
}


# =============================================================================
# Step Registry and Resolution
# =============================================================================


class StepRegistry:
    """Registry for postprocessing steps, supporting both built-in and custom steps."""

    def __init__(self):
        self._steps: dict[str, PostprocessingStep] = dict(BUILTIN_STEPS)
        self._custom_steps: dict[str, PostprocessingStep] = {}

    def register(self, name: str, step: PostprocessingStep) -> None:
        """Register a custom postprocessing step."""
        self._custom_steps[name] = step

    def get(self, name: str) -> PostprocessingStep | None:
        """Get a step by name. Checks custom steps first, then built-in."""
        if name in self._custom_steps:
            return self._custom_steps[name]
        return self._steps.get(name)

    def has(self, name: str) -> bool:
        """Check if a step with the given name is registered."""
        return name in self._custom_steps or name in self._steps

    def list_steps(self) -> list[str]:
        """List all registered step names."""
        return list(self._custom_steps.keys()) + list(self._steps.keys())


# Global step registry instance
step_registry = StepRegistry()


# =============================================================================
# Helper Functions
# =============================================================================


def resolve_postprocess_config(
    global_config: dict | None,
    index_code_config: dict | None,
    variant_config: dict | None,
) -> PostprocessConfig:
    """Resolve postprocessing configuration from hierarchy.

    Priority order (highest to lowest):
    1. Variant-level config
    2. Index code-level config
    3. Global config
    4. Built-in defaults (disabled, no steps)

    Args:
        global_config: Global postprocessing config from index_config.global
        index_code_config: Index code-specific postprocessing config
        variant_config: Variant-specific postprocessing config

    Returns:
        Resolved PostprocessConfig
    """
    # Start with built-in defaults (disabled)
    resolved = PostprocessConfig()

    # Apply global config
    global_pp_config = global_config.get("postprocessing") if global_config else None
    if global_pp_config:
        resolved = PostprocessConfig.from_dict(global_pp_config)

    # Apply index code config
    index_pp_config = (
        index_code_config.get("postprocessing") if index_code_config else None
    )
    if index_pp_config:
        index_config = PostprocessConfig.from_dict(index_pp_config)
        resolved = resolved.merge_with(index_config)

    # Apply variant config
    variant_pp_config = variant_config.get("postprocessing") if variant_config else None
    if variant_pp_config:
        variant_config_obj = PostprocessConfig.from_dict(variant_pp_config)
        resolved = resolved.merge_with(variant_config_obj)

    return resolved


def run_postprocessing_steps(
    chunk: str,
    file_name: str,
    chunk_id: int,
    metadata: dict,
    config: PostprocessConfig,
    registry: StepRegistry | None = None,
) -> dict:
    """Run all enabled postprocessing steps and return merged results.

    Steps run sequentially. Each step receives the original chunk and metadata
    (not the modified version from previous steps). All step outputs are merged
    into a single dictionary.

    Args:
        chunk: The text chunk to process
        file_name: Original file name
        chunk_id: Chunk index within the file
        metadata: Normalized metadata
        config: Postprocessing configuration with enabled steps
        registry: Step registry (defaults to global registry)

    Returns:
        Dictionary with all fields from all steps, ready to merge into document
    """
    if registry is None:
        registry = step_registry

    result: dict = {}

    for step_config in config.get_enabled_steps():
        step = registry.get(step_config.name)
        if step is None:
            logger.warning(f"Unknown postprocessing step: {step_config.name}")
            continue

        try:
            step_output = step(
                chunk=chunk,
                file_name=file_name,
                chunk_id=chunk_id,
                metadata=metadata,
                **step_config.config,
            )
            result.update(step_output)
        except Exception as e:
            logger.error(
                f"Step {step_config.name} failed for {file_name}:{chunk_id}: {e}"
            )

    return result
