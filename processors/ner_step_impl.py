"""Independent NER implementation for postprocessing step.

This module provides NER extraction functionality that is independent of
ner/main.py. It uses the HuggingFace transformers library with the IndicNER model.
"""

import logging

logger = logging.getLogger(__name__)

# Window configuration for handling long documents
# IndicNER is a BERT model with a 512 token limit
WINDOW_WORDS = 180
WINDOW_OVERLAP_WORDS = 20

# Cache for model instances
_model_cache: dict[str, tuple] = {}


def _get_model_pipeline(model_name: str, device: str | None = None):
    """Get or create a token classification pipeline for the given model.

    Args:
        model_name: HuggingFace model identifier
        device: Torch device (cuda, mps, cpu, or None for auto)

    Returns:
        Tuple of (tokenizer, model, pipeline)
    """
    cache_key = f"{model_name}:{device}"

    if cache_key in _model_cache:
        return _model_cache[cache_key]

    # Lazy imports to avoid loading heavy dependencies at module load
    import torch
    from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline

    # Determine device if not specified
    if device is None:
        if torch.cuda.is_available():
            device = "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"

    logger.info(f"Loading NER model {model_name} on device {device}")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForTokenClassification.from_pretrained(model_name)

    nlp_pipeline = pipeline(
        task="token-classification",
        model=model,
        tokenizer=tokenizer,
        aggregation_strategy="simple",
        device=0 if device == "cuda" else -1,  # -1 for CPU, 0 for CUDA
    )

    _model_cache[cache_key] = (tokenizer, model, nlp_pipeline, device)
    return _model_cache[cache_key]


def _split_into_word_windows(text: str) -> list[tuple[int, str]]:
    """Split text into overlapping word windows, tracking character offsets.

    Args:
        text: The text to split

    Returns:
        List of (character_offset, window_text) tuples
    """
    words: list[tuple[int, str]] = []
    offset = 0

    for token in text.split(" "):
        words.append((offset, token))
        offset += len(token) + 1  # +1 for the split space

    if not words:
        return []

    windows: list[tuple[int, str]] = []
    step = max(1, WINDOW_WORDS - WINDOW_OVERLAP_WORDS)

    for start in range(0, len(words), step):
        chunk = words[start : start + WINDOW_WORDS]
        if not chunk:
            break
        char_offset = chunk[0][0]
        window_text = " ".join(word for _, word in chunk)
        windows.append((char_offset, window_text))
        if start + WINDOW_WORDS >= len(words):
            break

    return windows


def extract_ner_entities(
    text: str, model: str = "ai4bharat/IndicNER", device: str | None = None
) -> list[dict]:
    """Extract named entities from text using the IndicNER model.

    This function handles long documents by splitting them into overlapping
    windows and processing each window separately. Results are deduplicated
    across windows, keeping the highest-scoring detection for each entity span.

    Args:
        text: The text to analyze
        model: HuggingFace model identifier
        device: Torch device (cuda, mps, cpu, or None for auto)

    Returns:
        List of entity dictionaries, each containing:
        - text: The entity text
        - type: The entity type (entity_group)
        - score: The confidence score (0-1)
        - start: Character start position
        - end: Character end position
    """
    if not text or not text.strip():
        return []

    # Get the pipeline for this model
    try:
        _, _, nlp_pipeline, _ = _get_model_pipeline(model, device)
    except Exception as e:
        logger.error(f"Failed to load NER model {model}: {e}")
        return []

    # Process text in windows
    seen: dict[tuple[int, int, str], dict] = {}

    for char_offset, window in _split_into_word_windows(text):
        try:
            for ent in nlp_pipeline(window):
                start = int(ent["start"]) + char_offset
                end = int(ent["end"]) + char_offset
                entity = {
                    "text": text[start:end],
                    "type": ent["entity_group"],
                    "score": round(float(ent["score"]), 4),
                    "start": start,
                    "end": end,
                }
                key = (start, end, entity["type"])
                # Keep the highest-scoring detection across overlapping windows
                if key not in seen or entity["score"] > seen[key]["score"]:
                    seen[key] = entity
        except Exception as e:
            logger.error(f"NER pipeline failed on window: {e}")
            continue

    # Return sorted by position
    return sorted(seen.values(), key=lambda e: (e["start"], e["end"]))


def clear_model_cache() -> None:
    """Clear the model cache. Useful for testing or freeing memory."""
    global _model_cache
    _model_cache.clear()
