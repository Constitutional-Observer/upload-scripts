from typing import TypedDict
import re


AP_DATE_RE = re.compile(r"Assembly - Day \d+\((\d{1,2})/(\d{1,2})/(\d{4})\)")
AP_SITTING_NAME_RE = re.compile(
    r"sitting (\d+)\((\d{1,2})/(\d{1,2})/(\d{4}) to (\d{1,2})/(\d{1,2})/(\d{4})\)"
)
AP_SESSION_RE = re.compile(r"Session (\d+)")
AP_TERM_RE = re.compile(r"([A-Za-z]+) Andhra Pradesh Assembly \((\d{4})-(\d{4})\)")


class LegislatureMetadata(TypedDict):
    state_code: str
    languages: list[str]

    year: int
    month: int
    day: int
    title_en: str

    # AP Specific
    house: str | None
    session: int | None
    sitting_number: int | None
    sitting_start_year: int | None
    sitting_start_month: int | None
    sitting_start_day: int | None
    sitting_end_year: int | None
    sitting_end_month: int | None
    sitting_end_day: int | None
    term_number: int | None
    term_start: int | None
    term_end: int | None

    archive_link: str


STATE_CODES = ["AP", "AS", "RJ", "KA", "KL", "TN", "TS", "UP", "WB"]

BASE_FIELDS = [
    {"name": "state_code", "type": "string", "facet": True},
    {"name": "file_name", "type": "string"},
    {"name": "year", "type": "int32", "facet": True},
    {"name": "month", "type": "int32", "facet": True},
    {"name": "day", "type": "int32", "facet": True},
    {"name": "title_en", "type": "string"},
    {"name": "archive_link", "type": "string"},
]

STATE_LOCALES = {
    "AP": "te",
    "AS": "as",
    "RJ": "hi",
    "KA": "kn",
    "KL": "ml",
    "TN": "ta",
    "TS": "te",
    "UP": "hi",
    "WB": "bn",
}

METADATA_SCHEMA = {
    state: [
        {"name": "discussions", "type": "string", "locale": locale},
    ]
    for state, locale in STATE_LOCALES.items()
}

# Add state-specific fields for AP
METADATA_SCHEMA["AP"].extend(
    [
        {"name": "house", "type": "string", "facet": True},
        {"name": "session", "type": "int32", "facet": True},
        {"name": "sitting_number", "type": "int32"},
        {"name": "sitting_start_year", "type": "int32"},
        {"name": "sitting_start_month", "type": "int32"},
        {"name": "sitting_start_day", "type": "int32"},
        {"name": "sitting_end_year", "type": "int32"},
        {"name": "sitting_end_month", "type": "int32"},
        {"name": "sitting_end_day", "type": "int32"},
        {"name": "term_number", "type": "int32", "facet": True},
        {"name": "term_start", "type": "int32"},
        {"name": "term_end", "type": "int32"},
    ]
)


def word_to_num(word: str) -> int:
    w2n = {
        "First": 1,
        "Second": 2,
        "Third": 3,
        "Fourth": 4,
        "Fifth": 5,
        "Sixth": 6,
        "Seventh": 7,
        "Eighth": 8,
        "Ninth": 9,
        "Tenth": 10,
        "Eleventh": 11,
        "Twelfth": 12,
        "Thirteenth": 13,
        "Fourteenth": 14,
        "Fifteenth": 15,
        "Sixteenth": 16,
        "Seventeenth": 17,
        "Eighteenth": 18,
        "Nineteenth": 19,
        "Twentieth": 20,
    }
    return w2n.get(word, 0)


def normalize_metadata_ap(metadata: dict) -> LegislatureMetadata:
    # Metadata handler for AP

    # Date extraction (Title)
    # Example: "Assembly - Day 1(01/12/2011)"
    match = AP_DATE_RE.search(metadata.get("title", ""))
    if match:
        day, month, year = map(int, match.groups())
    else:
        day, month, year = 0, 0, 0

    # Session
    # Example: "Session 8"
    session_match = AP_SESSION_RE.search(metadata.get("ap_legislature_session", ""))
    session = int(session_match.group(1)) if session_match else 0

    # Sitting
    # Example: "sitting 1(01/12/2011 to 05/12/2011)"
    sitting_match = AP_SITTING_NAME_RE.search(
        metadata.get("ap_legislature_sitting", "")
    )
    if sitting_match:
        sitting_num = int(sitting_match.group(1))
        s_start_d, s_start_m, s_start_y = map(int, sitting_match.group(2, 3, 4))
        s_end_d, s_end_m, s_end_y = map(int, sitting_match.group(5, 6, 7))
    else:
        sitting_num = 0
        s_start_d, s_start_m, s_start_y = 0, 0, 0
        s_end_d, s_end_m, s_end_y = 0, 0, 0

    # Term
    # Example: "Thirteenth Andhra Pradesh Assembly (2009-2014)"
    term_match = AP_TERM_RE.search(metadata.get("ap_legislature_term", ""))
    if term_match:
        term_word = term_match.group(1)
        term_number = word_to_num(term_word)
        term_start = int(term_match.group(2))
        term_end = int(term_match.group(3))
    else:
        term_number, term_start, term_end = 0, 0, 0

    return {
        "state_code": "AP",
        "languages": metadata.get("language", []),
        "year": year,
        "month": month,
        "day": day,
        "title_en": metadata.get("title", ""),
        "house": metadata.get("ap_legislature_house", ""),
        "session": session,
        "sitting_number": sitting_num,
        "sitting_start_year": s_start_y,
        "sitting_start_month": s_start_m,
        "sitting_start_day": s_start_d,
        "sitting_end_year": s_end_y,
        "sitting_end_month": s_end_m,
        "sitting_end_day": s_end_d,
        "term_number": term_number,
        "term_start": term_start,
        "term_end": term_end,
        "archive_link": metadata.get("identifier-access", "")
        or metadata.get("source", ""),
    }


def normalize_metadata_as(metadata: dict) -> LegislatureMetadata:
    year, month, day = map(int, metadata["date"].split("-"))
    return {
        "state_code": "AS",
        "languages": metadata.get("language", []),
        "year": year,
        "month": month,
        "day": day,
        "title_en": "",
        "house": None,
        "session": None,
        "sitting_number": None,
        "sitting_start_year": None,
        "sitting_start_month": None,
        "sitting_start_day": None,
        "sitting_end_year": None,
        "sitting_end_month": None,
        "sitting_end_day": None,
        "term_number": None,
        "term_start": None,
        "term_end": None,
        "archive_link": metadata["identifier-access"],
    }


def normalize_metadata(state_code: str, metadata: dict) -> LegislatureMetadata:
    """
    Normalise the metadata, since each state has its own format
    """
    match state_code:
        case "AP":
            return normalize_metadata_ap(metadata)
        case "AS":
            return normalize_metadata_as(metadata)
        case _:
            raise NotImplementedError()
