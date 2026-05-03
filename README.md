# Constitutional Observer Search

Index and search Indian state legislative debates, archives, high court records, gazettes, and government orders.

This repository provides tools to upload, index, and search digitized archival documents from Indian state institutions using [Meilisearch](https://www.meilisearch.com/).

## Goals

- **Normalized metadata**: Common schema across different state archives
- **Chunking**: Documents split into searchable chunks (200 words by default)
- **Embedding support**: Configure embeddings for semantic search

---

## Setup

```bash
# Install dependencies
uv sync

# Activate virtual environment
source .venv/bin/activate
```

## Configuration

Create `meilisearch_config.yaml`:

```yaml
connection:
  URL: http://localhost:7700
  API_KEY: api_key

index_config:
  embeddings:
    LLAMA_JINA_PROVIDER:
      source: "rest"
      dimensions: 768
      url: "http://your-embedding-service:8080/embeddings"
      request:
        model: "jinaai/jina-embeddings-v5-text-nano-retrieval"
        input: ["{{text}}"]
      response: [{"embedding": ["{{embedding}}"]}]
      documentTemplate: "Document: {{doc.__discussions}}"
```
If the embeddings field is removed, no embeddings will be configured for the index.

---

## Usage

### CLI Reference

```bash
python manage_collection.py <action> [options] [path]
```

| Action | Description | Required Args |
|--------|-------------|---------------|
| `create` | Create indexes for states | `--states <STATE_CODES>` |
| `delete` | Delete an index | `--index <NAME>` |
| `upload` | Upload documents | `<files_path>` |
| `print_schema` | Show index info | `--states <STATE_CODES>` |

**Options:**
- `--states <CODES>`: State codes (e.g., `KA AS TN`)
- `--config <FILE>`: Config file path (default: `meilisearch_config.yaml`)
- `--prefix <PREFIX>`: Index name prefix (default: `state_legislature_debates`)
- `--limit <N>`: Limit documents to process
- `--index <NAME>`: Index name for delete action

### Examples

```bash
# Create indexes for Karnataka and Assam
python manage_collection.py create --states KA AS

# Upload documents for Assam
python manage_collection.py upload /datasets/legislature_debates/AS

# Upload with limit (test with 100 docs)
python manage_collection.py upload /datasets/legislature_debates/AS --limit 100

# Delete an index (prompts for confirmation)
python manage_collection.py delete --index state_legislature_debates_as

# View index schema
python manage_collection.py print_schema --states KA
```

---

### Archive Directory Structure

```
/
└── /datasets/
    └── legislature_debates/
        └── <STATE_CODE>/   # e.g., AS, KA, TN
            ├── all_metadata.json   # Internet Archive metadata (JSONL)
            └── downloads/          # Extracted text files (_djvu.txt)
```

---

### Input Format

Each state directory must contain:
- `all_metadata.json` - JSONL file with Internet Archive item metadata
- `downloads/` - Directory with extracted text files (`._djvu.txt`)

### Metadata Schema

See [`metadata_schema.py`](metadata_schema.py) for complete field definitions.

**Core fields (all archives):**

| Field | Type | Facet | Searchable | Description |
|-------|------|-------|------------|-------------|
| `state_code` | str | Yes | Yes | State abbreviation (AP, AS, KA, etc.) |
| `year` | int | Yes | Yes | Document year |
| `month` | int | Yes | Yes | Document month |
| `day` | int | Yes | Yes | Document day |
| `title_en` | str | No | Yes | English title |
| `archive_link` | str | No | No | Internet Archive URL |
| `file_name` | str | Yes | No | Source filename |

**Legislature-specific fields:**

| Field | Type | Description |
|-------|------|-------------|
| `house` | str | Legislative house (Lok Sabha, Rajya Sabha, etc.) |
| `session` | int | Session number |
| `sitting_number` | int | Sitting number within session |
| `sitting_start_*` | int | Sitting start date (year/month/day) |
| `sitting_end_*` | int | Sitting end date (year/month/day) |
| `term_number` | int | Legislative term |
| `section_type` | str | Section classification |
| `minister_en` | str | Minister name (English) |
| `minister_kn` | str | Minister name (Kannada) |
| `participants_en` | str | Participants list |
| `discussions` | str | Full debate text |

See [`LegislatureMetadata`](metadata_schema.py) for complete field list.

**Supported state codes:** `AP`, `AS`, `RJ`, `KA`, `KL`, `TN`, `TS`, `UP`, `WB`, `TG`

---

## Workflow

1. **Extract**: Download files from Internet Archive, extract text (DjVu -> text)
2. **Organize**: Place in `/datasets/<type>/<STATE>/` with `all_metadata.json` and `downloads/`
3. **Create**: `python manage_collection.py create --states <CODES>`
4. **Upload**: `python manage_collection.py upload /datasets/<type>/<STATE>`
