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

# Optional global paths (can be overridden per state)
state_path: /path/to/datasets/legislature_debates
metadata_path: /path/to/metadata

index_config:
  global:
    # Default batch size for document uploads (default: 1000)
    batch_size: 1000
    # Default typo tolerance settings
    minWordSizeForTypos:
      oneTypo: 1
      twoTypos: 1
    # Default embeddings for all indexes (optional)
    # If set here, applies to all indexes unless overridden at state/variant level
    embeddings: null

  # State-specific configuration
  KA:
    # Path to data directory containing downloads/ and all_metadata.json
    files_path: /datasets/legislature_debates/KA
    metadata_path: /datasets/legislature_debates/KA/all_metadata.json
    
    # Chunking configuration
    chunking:
      max_chunk_len: 200  # words per chunk
    
    # Multiple index variants per state (optional)
    indexes:
      default:
        index_name: state_legislature_debates_ka  # optional, auto-generated if omitted
        # Override embeddings for this variant
        embeddings: null
      with_embeddings:
        index_name: state_legislature_debates_ka_embeddings
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
    
    # Settings that apply to all indexes for this state
    processor: filesystem  # or "lok_sabha"
    batch_size: 500  # overrides global default for this state

  AS:
    files_path: /datasets/legislature_debates/AS
    index_name: state_legislature_debates_as  # single index (old format still supported)
    minWordSizeForTypos:
      oneTypo: 1
      twoTypos: 1
```

**Configuration Hierarchy:**

Settings are resolved in this order (highest priority first):
1. Index variant-specific config (under `indexes.<variant>`)
2. State-level config (under `<STATE_CODE>`)
3. Global config (under `index_config.global`)
4. Built-in defaults

If the `embeddings` field is `null` or omitted, no embeddings will be configured for that index.

---

## Usage

### CLI Reference

```bash
python manage_collection.py <action> [options] [path]
```

| Action | Description | Required Args |
|--------|-------------|---------------|
| `create` | Create indexes for states | `--states <STATE_CODES>` |
| `delete` | Delete an index | `--index <NAME>` or `--states <STATE_CODES>` |
| `upload` | Upload documents | `--states <STATE_CODES>` |
| `print_schema` | Show index info | `--states <STATE_CODES>` |

**Options:**
- `--states <CODES>`: State codes (e.g., `KA AS TN`). Required for `upload`, `create`, and `print_schema` actions.
- `--config <FILE>`: Config file path (default: `meilisearch_config.yaml`)
- `--prefix <PREFIX>`: Index name prefix (default: `state_legislature_debates`)
- `--limit <N>`: Limit documents to process (for upload action)
- `--index <NAME>`: Index name for delete action
- `--files-path <PATH>`: Override files path from config
- `--metadata-path <PATH>`: Override metadata path from config
- `--state-code <CODE>`: Explicit state code (auto-derived from files_path if omitted)

### Examples

```bash
# Create indexes for Karnataka and Assam (creates all variants defined in config)
python manage_collection.py create --states KA AS

# Upload documents for Assam (uses paths from config)
python manage_collection.py upload --states AS

# Upload with limit (test with 100 docs)
python manage_collection.py upload --states AS --limit 100

# Upload with explicit files path override
python manage_collection.py upload --states AS --files-path /custom/path/to/AS

# Delete an index (prompts for confirmation)
python manage_collection.py delete --index state_legislature_debates_as

# Delete all indexes for a state
python manage_collection.py delete --states AS

# View index schema for Karnataka
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
3. **Configure**: Create `meilisearch_config.yaml` with `files_path` and `metadata_path` for each state
4. **Create**: `python manage_collection.py create --states <CODES>`
5. **Upload**: `python manage_collection.py upload --states <CODES>`


## Benchmarking

`run_queries.py` will store the results for a list of predefined queries, provided in CSV format. Sample usage:

```sh
# With state-level index names in config
python run_queries.py configs/prod.yaml sample_queries_kannada.csv ka_results.parquet --state-code KA

# Or with explicit --limit
python run_queries.py configs/prod.yaml sample_queries_kannada.csv ka_results.parquet --state-code KA --limit 10
```

This will generate a Parquet file (e.g., `ka_results.parquet`) with query results, and a sidecar metadata file (e.g., `ka_results.parquet.metadata.json`). Each result entry contains a list of hits. The results can be compared with previous versions to see if search performance has improved.

### Script args:

```
  usage: run_queries.py [-h] [--limit LIMIT] [--state-code STATE_CODE] [--hybrid] meilisearch_config queries_file output_file

positional arguments:
  meilisearch_config    Path to config YAML file
  queries_file          CSV file with 'primary_search' and 'related' columns
  output_file           File to store query results in JSON format

options:
  -h, --help            show this help message and exit
  --limit LIMIT         Maximum number of results per query (default: 20)
  --state-code CODE     State code to look up index_name in config (required if config uses state-level index names)
  --hybrid             Enable hybrid search with embeddings (default: False)
```

**Note:** The `index_name` is now read from the config file using `index_config.<state_code>.index_name`. The `--state-code` argument is required when your config defines index names at the state level.

Queries can be found in the [wiki](https://github.com/Constitutional-Observer/wiki/tree/main/benchmarking)
