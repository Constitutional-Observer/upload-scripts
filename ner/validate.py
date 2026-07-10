"""Validate the `_ner` field across Meilisearch documents.

Walks every index (or the ones passed via --index) and reports which documents
already carry a `_ner` field, listing them and optionally dumping the field's
value.
"""

from __future__ import annotations

import argparse
import json
import sys

import meilisearch
import meilisearch.errors

DEFAULT_URL = "https://search.constitutional.observer"
DEFAULT_MASTER_KEY = "freehand-pruning-unmarked-panic-plentiful-throwaway"
NER_FIELD = "_ner"


def iter_documents(index, primary_key: str, page_size: int, use_filter: bool):
    """Yield documents from an index one page at a time.

    When `use_filter` is set, only documents that carry `_ner` are requested,
    so the server does the filtering instead of shipping every document over
    the wire.
    """
    offset = 0
    fields = [primary_key, NER_FIELD]
    while True:
        params = {"offset": offset, "limit": page_size, "fields": fields}
        if use_filter:
            params["filter"] = f"{NER_FIELD} EXISTS"
        result = index.get_documents(params)
        docs = result.results
        if not docs:
            break
        for doc in docs:
            yield doc if isinstance(doc, dict) else doc.__dict__
        if offset + len(docs) >= result.total:
            break
        offset += len(docs)


def ner_field_filterable(index) -> bool:
    """Whether `_ner EXISTS` filters can be pushed down to this index."""
    try:
        index.get_documents({"limit": 1, "filter": f"{NER_FIELD} EXISTS"})
        return True
    except meilisearch.errors.MeilisearchApiError:
        return False


def validate_index(index, page_size: int, show_values: bool) -> tuple[int, int]:
    """Report `_ner` presence for one index. Returns (present, total)."""
    primary_key = index.get_primary_key() or "id"
    total = index.get_stats().number_of_documents
    use_filter = ner_field_filterable(index)
    present = 0

    print(f"\n=== {index.uid} (documents={total}) ===")
    for doc in iter_documents(index, primary_key, page_size, use_filter):
        if NER_FIELD not in doc:
            continue
        present += 1
        doc_id = doc.get(primary_key)
        value = doc[NER_FIELD]
        count = len(value) if isinstance(value, list) else "n/a"
        print(f"  {doc_id}  (entities={count})")
        if show_values:
            print(json.dumps(value, ensure_ascii=False, indent=2))

    print(f"  -> {present}/{total} documents have `{NER_FIELD}`")
    return present, total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help="Meilisearch base URL")
    parser.add_argument("--key", default=DEFAULT_MASTER_KEY, help="Meilisearch master key")
    parser.add_argument(
        "--index",
        action="append",
        help="Limit to specific index uid(s). Repeatable. Default: all indexes.",
    )
    parser.add_argument(
        "--values",
        action="store_true",
        help=f"Print the full `{NER_FIELD}` value for each document where present.",
    )
    parser.add_argument("--page-size", type=int, default=200, help="Docs fetched per request")
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

    grand_present = 0
    grand_total = 0
    for index in indexes:
        present, total = validate_index(index, args.page_size, args.values)
        grand_present += present
        grand_total += total

    print(f"\nTotal: {grand_present}/{grand_total} documents have `{NER_FIELD}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
