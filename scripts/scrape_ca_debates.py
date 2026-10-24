"""Scrape the Constituent Assembly (CA) debates from the constitutionofindia.net
WordPress REST API into an all_metadata.json (JSONL) for the "functional"
processor pipeline with prechunked: true (see processors/functional_pipeline.py).

The API models debates as:
  - /wp/v2/debates            taxonomy, one term per sitting day ("09 Dec 1946")
  - /wp/v2/debate_paragraphs  posts tagged with a day term; one per paragraph,
                              ordered by menu_order, with speaker / articles ids
  - /wp/v2/debate_volume      posts listing the day terms in each volume
  - /wp/v2/speaker            taxonomy resolving speaker / speaker_referred ids

The articles taxonomy is shadowed by the "articles" post type at /wp/v2/articles
and its term slugs are just the ids, so article ids are kept as-is (strings).

The site already splits each day into paragraphs, so those are used as chunks
as-is. For each day:
  1. Fetch all paragraphs into <out_dir>/raw/<iso-date>.json (skipped on reruns
     if already cached; pass --refresh to refetch).
  2. Clean the HTML and resolve speaker ids to names.
  3. Append a JSONL line {"metadata": {...}, "chunks": [{"text": ..., ...}]}
     to <out_dir>/all_metadata.json.

The ISO date is the document identifier (and so file_name): it is unique per
sitting, sorts correctly, and avoids the inconsistent WP slugs
("29-july-1947" vs "10-dec-1949"). Chunk ids become CA_<date>_<n>.

Usage:
    python scripts/scrape_ca_debates.py <out_dir> [--limit-days N] [--refresh]
"""

import argparse
import html
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(it, **kwargs):
        return it


API = "https://www.constitutionofindia.net/wp-json/wp/v2"
PER_PAGE = 100
RETRIES = 4
REQUEST_DELAY = 0.2

TAG_RE = re.compile(r"<[^>]+>")
BLOCK_TAG_RE = re.compile(r"<\s*(br|/p|/div|/li)\b[^>]*>", re.IGNORECASE)
HEADING_RE = re.compile(
    r"^\s*(<p[^>]*>)?\s*<strong>.*</strong>\s*(</p>)?\s*$", re.DOTALL | re.IGNORECASE
)
VOLUME_RE = re.compile(r"Volume\s+(\d+)", re.IGNORECASE)


def get(client: httpx.Client, path: str, params: dict) -> httpx.Response:
    for attempt in range(RETRIES):
        try:
            response = client.get(f"{API}/{path}", params=params)
            if response.status_code < 500:
                response.raise_for_status()
                time.sleep(REQUEST_DELAY)
                return response
        except httpx.TransportError:
            if attempt == RETRIES - 1:
                raise
        time.sleep(2**attempt)
    response.raise_for_status()
    return response


def get_all(client: httpx.Client, path: str, params: dict) -> list[dict]:
    """Fetch every page of a WP collection endpoint."""
    items = []
    page = 1
    while True:
        response = get(client, path, {**params, "per_page": PER_PAGE, "page": page})
        items.extend(response.json())
        total_pages = int(response.headers.get("X-WP-TotalPages", 1))
        if page >= total_pages:
            return items
        page += 1


def term_names(terms: list[dict]) -> dict[int, str]:
    """id -> name for taxonomy terms; ids without a name fall back to the id."""
    return {t["id"]: html.unescape(t["name"]) for t in terms if t.get("name")}


def parse_day(name: str) -> str:
    """'09 Dec 1946' / '29 July 1947' -> '1946-12-09'."""
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(name.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unparseable debate date: {name!r}")


def clean_html(rendered: str) -> str:
    text = BLOCK_TAG_RE.sub("\n", rendered)
    text = html.unescape(TAG_RE.sub("", text)).replace("\xa0", " ")
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def build_chunks(paragraphs: list[dict], speakers: dict[int, str]) -> list[dict]:
    chunks = []
    for para in sorted(paragraphs, key=lambda p: (p["menu_order"], p["id"])):
        rendered = para["content"]["rendered"]
        text = clean_html(rendered)
        if not text:
            continue
        speaker = [speakers.get(i, str(i)) for i in para.get("speaker", [])]
        chunks.append(
            {
                "text": text,
                "paragraph_id": para["slug"],
                "speaker": speaker,
                "speaker_referred": [
                    speakers.get(i, str(i)) for i in para.get("speaker_referred", [])
                ],
                "articles": [str(i) for i in para.get("articles", [])],
                "is_heading": not speaker and bool(HEADING_RE.match(rendered)),
            }
        )
    return chunks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--limit-days", type=int, help="Only scrape the first N days")
    parser.add_argument(
        "--refresh", action="store_true", help="Refetch days already cached in raw/"
    )
    args = parser.parse_args()

    raw_dir = args.out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output = args.out_dir / "all_metadata.json"

    errors: list[tuple[str, str]] = []

    with httpx.Client(timeout=60, follow_redirects=True) as client:
        terms = get_all(
            client,
            "debates",
            {"_fields": "id,name,slug,link,count,yoast_head_json.description"},
        )
        speakers = term_names(get_all(client, "speaker", {"_fields": "id,name"}))
        volume_of: dict[int, int] = {}
        for volume in get_all(client, "debate_volume", {"_fields": "title,debates"}):
            match = VOLUME_RE.search(volume["title"]["rendered"])
            if match:
                for term_id in volume.get("debates", []):
                    volume_of[term_id] = int(match.group(1))

        days = sorted(((parse_day(t["name"]), t) for t in terms), key=lambda d: d[0])
        if args.limit_days:
            days = days[: args.limit_days]
        print(
            f"Found {len(terms)} day(s), {len(speakers)} speaker(s), "
            f"{len(volume_of)} day(s) mapped to volumes"
        )

        written = 0
        total_chunks = 0
        short_days = 0
        with open(output, "w", encoding="utf-8") as out:
            for date, term in tqdm(days, desc="Scraping CA debates"):
                raw_path = raw_dir / f"{date}.json"
                if raw_path.exists() and not args.refresh:
                    paragraphs = json.loads(raw_path.read_text(encoding="utf-8"))
                else:
                    try:
                        paragraphs = get_all(
                            client,
                            "debate_paragraphs",
                            {
                                "debates": term["id"],
                                "orderby": "menu_order",
                                "order": "asc",
                                "_fields": "id,slug,menu_order,content,speaker,"
                                "speaker_referred,articles",
                            },
                        )
                    except httpx.HTTPError as e:
                        errors.append((date, f"fetch failed: {e}"))
                        continue
                    raw_path.write_text(json.dumps(paragraphs), encoding="utf-8")

                # Term counts include unpublished posts, so fewer is expected
                if len(paragraphs) > term["count"]:
                    errors.append(
                        (date, f"fetched {len(paragraphs)} of {term['count']} paragraphs")
                    )
                elif len(paragraphs) < term["count"]:
                    short_days += 1

                chunks = build_chunks(paragraphs, speakers)
                if not chunks:
                    errors.append((date, "no non-empty paragraphs"))
                    continue

                metadata = {
                    "identifier": date,
                    "date": date,
                    "title": term["name"],
                    "wp_term_id": term["id"],
                    "volume": volume_of.get(term["id"], 0),
                    "link": term["link"],
                    "description": (term.get("yoast_head_json") or {}).get(
                        "description", ""
                    ),
                }
                out.write(json.dumps({"metadata": metadata, "chunks": chunks}) + "\n")
                written += 1
                total_chunks += len(chunks)

    print(f"\nWrote {written} day(s), {total_chunks} chunk(s) to {output}")
    print(f"Days with fewer published paragraphs than the term count: {short_days}")
    print(f"Warnings/errors: {len(errors)}")
    for name, reason in errors[:30]:
        print(f"  {name}: {reason}", file=sys.stderr)
    if len(errors) > 30:
        print(f"  ... and {len(errors) - 30} more", file=sys.stderr)


if __name__ == "__main__":
    main()
