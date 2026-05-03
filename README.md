# Constitutional Observer Upload Scripts

This repo hosts scripts to upload archived files from various Indian State institutions, such as the state legislature debates, state archives, high court records, gazette orders, government orders, and more.

## Structure

### `metadata_schema.py`
Defines the schemas for each archive type, i.e. the list of fields that are indexed, filterable and searchable, along with data types for each state archive, legislature debate, etc.
Field names have been made common among the different archives where possible.

### `metadata_hander.py`
Handlers for metadata of each of the index types. Converts the data from the Internet Archive metadata_all.json format into a normalized format.
For e.g. the West Bengal State Legistlature Debate date has been normalized to match the format of the other state debate dates.

### `manage_collection.py`
Script that handles creation, deletion of indexes and uploading of files to the indexes.

## Usage

0. Install the required dependencies using `uv sync`. Then activate the environment with `source .venv/bin/activate`
1. Make sure the files you are uploading have the schema and handler defined in the respective python directories.
   The manage_collection script expects to be able to find the handler by matching the directory name (See below for directory structure reference)
2. Create a `meilisearch_config.yaml` file. This includes embeddings config and the meilisearch connection details.
3. Create the index. Run `python manage_collection.py create --states <list of states, separated by spaces>`. E.g. `python manage_collection.py create --states KA AS` will create the index for the state legislature debates of Karnataka and Assam.
4. Upload documents: `python manage_collection.py upload /path/to/directory/with/metadata_and_files`. E.g. `python manage_collection.py upload /datasets/legislature_debates/AS` will upload files for Assam.


## Example folder structure

```
  /datasets/legislature_debates/
├── AS
│   ├── all_metadata.json
│   ├── downloads
  
```

## Metadata Structure

Metadata refers to additional fields that are used for making the archives more searchable. Currently the following fields are available:

```python
class LegislatureMetadata(TypedDict):
    state_code: str
    languages: list[str]

    year: int
    month: int
    day: int
    title_en: str
    archive_link: str

    house: NotRequired[str]
    session: NotRequired[int]
    sitting_number: NotRequired[int]
    sitting_start_year: NotRequired[int]
    sitting_start_month: NotRequired[int]
    sitting_start_day: NotRequired[int]
    sitting_end_year: NotRequired[int]
    sitting_end_month: NotRequired[int]
    sitting_end_day: NotRequired[int]
    term_number: NotRequired[int]
    term_start: NotRequired[int]
    term_end: NotRequired[int]

    section_type: NotRequired[str]
    start_page: NotRequired[int]
    end_page: NotRequired[int]
    book_id: NotRequired[int]
    place_session: NotRequired[str]
    minister_en: NotRequired[str]
    minister_kn: NotRequired[str]
    questioner_en: NotRequired[str]
    questioner_kn: NotRequired[str]
    participants_en: NotRequired[str]
    participants_kn: NotRequired[str]
    discussions: NotRequired[str]
```
