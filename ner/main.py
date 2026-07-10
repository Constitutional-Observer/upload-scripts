"""Populate a `_ner` field on every document in every Meilisearch index.

For each document the text field (default `__discussions`) is run through the
AI4Bharat IndicNER model and the resulting entities are written back to the
`_ner` field. Documents that already have a `_ner` field are skipped unless
`--reparse` is passed.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import meilisearch
import meilisearch.errors
from tqdm import tqdm

DEFAULT_URL = "https://search.constitutional.observer"
DEFAULT_MASTER_KEY = ""
DEFAULT_MODEL = "ai4bharat/IndicNER"
DEFAULT_TEXT_FIELD = "__discussions"
NER_FIELD = "_ner"

# IndicNER is a BERT model with a 512 token limit. Chunk the input into
# overlapping word windows so long documents are covered end to end.
WINDOW_WORDS = 180
WINDOW_OVERLAP_WORDS = 20


@dataclass
class NerRunner:
    """Wraps the IndicNER token-classification pipeline."""

    model_name: str
    device: str | None = None

    def __post_init__(self) -> None:
        # Imported lazily so `--help` and connection errors don't pay the
        # (heavy) transformers/torch import cost.
        import torch
        from transformers import (
            AutoModelForTokenClassification,
            AutoTokenizer,
            pipeline,
        )

        if self.device is None:
            if torch.cuda.is_available():
                self.device = "cuda"
            elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"

        tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        model = AutoModelForTokenClassification.from_pretrained(self.model_name)
        self._pipeline = pipeline(
            task="token-classification",
            model=model,
            tokenizer=tokenizer,
            aggregation_strategy="simple",
            device=self.device,
        )

    def _windows(self, text: str) -> list[tuple[int, str]]:
        """Split text into overlapping word windows, tracking char offsets."""
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
            windows.append((char_offset, " ".join(word for _, word in chunk)))
            if start + WINDOW_WORDS >= len(words):
                break
        return windows

    def extract(self, text: str) -> list[dict]:
        """Return a deduplicated list of entities for the given text."""
        if not text or not text.strip():
            return []

        seen: dict[tuple[int, int, str], dict] = {}
        for char_offset, window in self._windows(text):
            for ent in self._pipeline(window):
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
                # Keep the highest-scoring detection across overlapping windows.
                if key not in seen or entity["score"] > seen[key]["score"]:
                    seen[key] = entity

        return sorted(seen.values(), key=lambda e: (e["start"], e["end"]))


def iter_documents(index, primary_key: str, text_field: str, page_size: int):
    """Yield documents from an index one page at a time."""
    offset = 0
    fields = [primary_key, text_field, NER_FIELD]
    while True:
        result = index.get_documents({"offset": offset, "limit": page_size, "fields": fields})
        docs = result.results
        if not docs:
            break
        for doc in docs:
            yield doc if isinstance(doc, dict) else doc.__dict__
        if offset + len(docs) >= result.total:
            break
        offset += len(docs)


def process_index(
    index,
    runner: NerRunner,
    text_field: str,
    reparse: bool,
    page_size: int,
    batch_size: int,
) -> tuple[int, int]:
    """Run NER over one index. Returns (processed, skipped)."""
    primary_key = index.get_primary_key() or "id"
    total = index.get_stats().number_of_documents

    processed = 0
    skipped = 0
    pending: list[dict] = []

    def flush() -> None:
        if pending:
            index.update_documents(pending, primary_key=primary_key)
            pending.clear()

    for doc in tqdm(
        iter_documents(index, primary_key, text_field, page_size),
        total=total,
        desc=index.uid,
        unit="doc",
    ):
        if NER_FIELD in doc and not reparse:
            skipped += 1
            continue

        entities = runner.extract(doc.get(text_field) or "")
        pending.append({primary_key: doc[primary_key], NER_FIELD: entities})
        processed += 1

        if len(pending) >= batch_size:
            flush()

    flush()
    return processed, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help="Meilisearch base URL")
    parser.add_argument("--key", default=DEFAULT_MASTER_KEY, help="Meilisearch master key")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="HuggingFace NER model id")
    parser.add_argument("--text-field", default=DEFAULT_TEXT_FIELD, help="Document field to analyze")
    parser.add_argument(
        "--index",
        action="append",
        help="Limit to specific index uid(s). Repeatable. Default: all indexes.",
    )
    parser.add_argument(
        "--reparse",
        action="store_true",
        help=f"Re-run the model and overwrite `{NER_FIELD}` even when already present.",
    )
    parser.add_argument("--device", default=None, help="Torch device (cuda/mps/cpu). Auto if unset.")
    parser.add_argument("--page-size", type=int, default=200, help="Docs fetched per request")
    parser.add_argument("--batch-size", type=int, default=200, help="Docs per update request")
    args = parser.parse_args()

    client = meilisearch.Client(args.url, args.key)
    try:
        client.health()
    except meilisearch.errors.MeilisearchError as exc:
        print(f"Cannot reach Meilisearch at {args.url}: {exc}", file=sys.stderr)
        return 1

    indexes = client.get_indexes()["results"]
    if args.index:
        wanted = set(args.index)
        indexes = [ix for ix in indexes if ix.uid in wanted]
        missing = wanted - {ix.uid for ix in indexes}
        if missing:
            print(f"Index(es) not found: {', '.join(sorted(missing))}", file=sys.stderr)
            return 1

    if not indexes:
        print("No indexes to process.", file=sys.stderr)
        return 1

    print(f"Loading model '{args.model}' ...")
    runner = NerRunner(model_name=args.model, device=args.device)
    print(f"Using device: {runner.device}")

    grand_processed = 0
    grand_skipped = 0
    for index in indexes:
        processed, skipped = process_index(
            index,
            runner,
            text_field=args.text_field,
            reparse=args.reparse,
            page_size=args.page_size,
            batch_size=args.batch_size,
        )
        print(f"[{index.uid}] processed={processed} skipped={skipped}")
        grand_processed += processed
        grand_skipped += skipped

    print(f"Done. processed={grand_processed} skipped={grand_skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
