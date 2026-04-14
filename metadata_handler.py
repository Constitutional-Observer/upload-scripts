import re

from metadata_schema import LegislatureMetadata


AP_DATE_RE = re.compile(r"Assembly - Day \d+\((\d{1,2})/(\d{1,2})/(\d{4})\)")
AP_SITTING_NAME_RE = re.compile(
    r"sitting (\d+)\((\d{1,2})/(\d{1,2})/(\d{4}) to (\d{1,2})/(\d{1,2})/(\d{4})\)"
)
AP_SESSION_RE = re.compile(r"Session (\d+)")
AP_TERM_RE = re.compile(r"([A-Za-z]+) Andhra Pradesh Assembly \((\d{4})-(\d{4})\)")

KA_TERM_RE = re.compile(r"(\d+)\[(\d{4})-(\d{4})\]")
KA_SESSION_RE = re.compile(r"(\d+)\[\d{4}\]")

RJ_ASSEMBLY_RE = re.compile(r"Assembly (\d+)")
RJ_SESSION_RE = re.compile(r"Session (\d+)")

# TG (Telangana) regex patterns
TG_DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
TG_TERM_RE = re.compile(
    r"([A-Za-z]+) Telangana Legislative Assembly \((\d{4})-(\d{4})\)"
)

# TN (Tamil Nadu) regex patterns
TN_ASSEMBLY_RE = re.compile(r"TNLA-(\d+)-\((\d{4})-(\d{4})\)")
TN_SESSION_RE = re.compile(r"(\d+)\.(\d+)")

# UP (Uttar Pradesh) regex patterns - not needed as fields are already numeric

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
        "archive_link": metadata["identifier-access"],
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
        "archive_link": metadata["identifier-access"],
    }


def normalize_metadata_ka(metadata: dict) -> LegislatureMetadata:
    # Metadata handler for KA
    date_str = metadata.get("date", "0000-00-00")
    try:
        year, month, day = map(int, date_str.split("-"))
    except (ValueError, AttributeError):
        year, month, day = 0, 0, 0

    # Term
    # Example: "13[2008-2013]"
    term_match = KA_TERM_RE.search(metadata.get("kla_assemblynumber", ""))
    if term_match:
        term_number = int(term_match.group(1))
        term_start = int(term_match.group(2))
        term_end = int(term_match.group(3))
    else:
        term_number, term_start, term_end = 0, 0, 0

    # Session
    # Example: "3[2009]"
    session_match = KA_SESSION_RE.search(metadata.get("kla_sessionnumber", ""))
    session = int(session_match.group(1)) if session_match else 0

    return LegislatureMetadata(
        state_code= "KA",
        languages= metadata.get("language", []),
        year= year,
        month= month,
        day= day,
        title_en= metadata.get("kla_debate_title_subject_eng", ""),
        # Extra fields for KA
        discussions= metadata.get("kla_debate_title_subject_kan", ""),
        house= "Legislative Assembly",
        session= session,
        term_number= term_number,
        term_start= term_start,
        term_end= term_end,
        archive_link= metadata["identifier-access"],
        section_type= metadata.get("kla_sectiontype"),
        start_page= int(metadata.get("kla_startpage", 0)),
        end_page= int(metadata.get("kla_endpage", 0)),
        book_id= int(metadata.get("kla_bookid", 0)),
        place_session= metadata.get("kla_placesession"),
        minister_en= metadata.get("kla_minister_name_eng"),
        minister_kn= metadata.get("kla_minister_name_kan"),
        questioner_en= metadata.get("kla_questioner_name_eng"),
        questioner_kn= metadata.get("kla_questioner_name_kan"),
        participants_en= metadata.get("kla_debate_participants_eng"),
        participants_kn= metadata.get("kla_debate_participants_kan"),
    )


def normalize_metadata_kl(metadata: dict) -> LegislatureMetadata:
    # Metadata handler for KL (Kerala)
    # KL has a simpler metadata structure compared to other states

    # Date extraction (date field is in YYYY-MM-DD format)
    date_str = metadata.get("date", "0000-00-00")
    try:
        year, month, day = map(int, date_str.split("-"))
    except (ValueError, AttributeError):
        year, month, day = 0, 0, 0

    # Extract subjects as a comma-separated string
    subject_list = metadata.get("subject", [])
    subjects = (
        ", ".join(subject_list) if isinstance(subject_list, list) else str(subject_list)
    )

    return LegislatureMetadata(
        state_code= "KL",
        languages= metadata.get("languages", []),
        year= year,
        month= month,
        day= day,
        title_en=metadata.get("title", ""),
        # KL-specific fields
        discussions= metadata.get("description", ""),
        subject= subjects,
        archive_link= metadata["identifier-access"],
    )


def normalize_metadata_rj(metadata: dict) -> LegislatureMetadata:
    # Metadata handler for RJ (Rajasthan)

    # Date extraction (date field is in DD/MM/YYYY format)
    date_str = metadata.get("date", "00/00/0000")
    try:
        day, month, year = map(int, date_str.split("/"))
    except (ValueError, AttributeError):
        day, month, year = 0, 0, 0

    # Assembly number extraction from metadata field
    # RJ uses assembly_number which maps to term_number in the common schema
    term_number = int(metadata.get("rajasthan_legislature_assembly_number", 0))

    # Session number extraction from metadata field
    session = int(metadata.get("rajasthan_legislature_session_number", 0))

    # Fallback: try to parse from title if metadata fields are missing
    if term_number == 0 or session == 0:
        title = metadata.get("title", "")
        # Example: "Assembly 1, Session 1, 01/04/1952"
        assembly_match = RJ_ASSEMBLY_RE.search(title)
        session_match = RJ_SESSION_RE.search(title)

        if assembly_match:
            term_number = int(assembly_match.group(1))
        if session_match:
            session = int(session_match.group(1))

    return {
        "state_code": "RJ",
        "languages": metadata.get("language", []),
        "year": year,
        "month": month,
        "day": day,
        "title_en": metadata.get("title", ""),
        # Reuse existing fields for consistency with other states
        "house": "Legislative Assembly",
        "session": session,
        "term_number": term_number,
        "archive_link": metadata["identifier-access"],
    }


def normalize_metadata_tg(metadata: dict) -> LegislatureMetadata:
    # Metadata handler for TG (Telangana)

    # Date extraction from title (format: Assembly (DD-MM-YYYY))
    title = metadata.get("title", "")
    date_match = TG_DATE_RE.search(title)
    if date_match:
        day, month, year = map(int, date_match.groups())
    else:
        day, month, year = 0, 0, 0

    # House extraction
    house = metadata.get("telangana_legislature_house", "Assembly")

    # Session extraction
    session_str = metadata.get("telangana_legislature_session", "")
    # Example: "Session 3" -> extract number
    session_match = re.search(r"Session\s+(\d+)", session_str)
    session = int(session_match.group(1)) if session_match else 0

    # Sitting extraction
    sitting_str = metadata.get("telangana_legislature_sitting", "")
    # Example: "sitting 1(23-07-2024 to 02-08-2024)"
    sitting_match = re.search(
        r"sitting\s+(\d+)\((\d{2})-(\d{2})-(\d{4}) to (\d{2})-(\d{2})-(\d{4})\)",
        sitting_str,
    )
    if sitting_match:
        sitting_number = int(sitting_match.group(1))
        s_start_d, s_start_m, s_start_y = map(int, sitting_match.group(2, 3, 4))
        s_end_d, s_end_m, s_end_y = map(int, sitting_match.group(5, 6, 7))
    else:
        sitting_number = 0
        s_start_d, s_start_m, s_start_y = 0, 0, 0
        s_end_d, s_end_m, s_end_y = 0, 0, 0

    # Term extraction
    term_str = metadata.get("telangana_legislature_term", "")
    # Example: "Third Telangana Legislative Assembly (2023-2028)"
    term_match = TG_TERM_RE.search(term_str)
    if term_match:
        term_word = term_match.group(1)
        term_number = word_to_num(term_word)
        term_start = int(term_match.group(2))
        term_end = int(term_match.group(3))
    else:
        term_number, term_start, term_end = 0, 0, 0

    return {
        "state_code": "TG",
        "languages": metadata.get("language", []),
        "year": year,
        "month": month,
        "day": day,
        "title_en": metadata.get("title", ""),
        "house": house,
        "session": session,
        "sitting_number": sitting_number,
        "sitting_start_year": s_start_y,
        "sitting_start_month": s_start_m,
        "sitting_start_day": s_start_d,
        "sitting_end_year": s_end_y,
        "sitting_end_month": s_end_m,
        "sitting_end_day": s_end_d,
        "term_number": term_number,
        "term_start": term_start,
        "term_end": term_end,
        "archive_link": metadata["identifier-access"],
    }


def normalize_metadata_tn(metadata: dict) -> LegislatureMetadata:
    # Metadata handler for TN (Tamil Nadu)

    # Date extraction from tnla_date field (format: DD-MM-YYYY)
    date_str = metadata.get("tnla_date", "00-00-0000")
    try:
        day, month, year = map(int, date_str.split("-"))
    except (ValueError, AttributeError):
        day, month, year = 0, 0, 0

    # Assembly/Term extraction from tnla_assembly_no
    # Format: "TNLA-06-(1977-1980)"
    assembly_str = metadata.get("tnla_assembly_no", "")
    assembly_match = TN_ASSEMBLY_RE.search(assembly_str)
    if assembly_match:
        term_number = int(assembly_match.group(1))
        term_start = int(assembly_match.group(2))
        term_end = int(assembly_match.group(3))
    else:
        term_number, term_start, term_end = 0, 0, 0

    # Session extraction from tnla_session_no
    # Format: "2.0" (session.sub-session)
    session_str = metadata.get("tnla_session_no", "0.0")
    session_match = TN_SESSION_RE.search(session_str)
    if session_match:
        session = int(session_match.group(1))
    else:
        session = 0

    return {
        "state_code": "TN",
        "languages": metadata.get("language", []),
        "year": year,
        "month": month,
        "day": day,
        "title_en": metadata.get("tnla_subject", "") or metadata.get("title", ""),
        "house": "Legislative Assembly",
        "session": session,
        "term_number": term_number,
        "term_start": term_start,
        "term_end": term_end,
        "archive_link": metadata["identifier-access"],
        "section_type": metadata.get("tnla_business", ""),
    }


def normalize_metadata_up(metadata: dict) -> LegislatureMetadata:
    # Metadata handler for UP (Uttar Pradesh)

    # Date extraction from date field (format: DD-MM-YYYY)
    date_str = metadata.get("date", "00-00-0000")
    try:
        day, month, year = map(int, date_str.split("-"))
    except (ValueError, AttributeError):
        day, month, year = 0, 0, 0

    # Assembly/Term extraction from up_legislature_assembly_number
    term_number = int(metadata.get("up_legislature_assembly_number", 0))

    # Session extraction from up_legislature_session_number
    session = int(metadata.get("up_legislature_session_number", 0))

    # Fallback: try to parse from title if metadata fields are missing
    if term_number == 0 or session == 0:
        title = metadata.get("title", "")
        # Example: "Assembly 1, Session 1, 02-09-1952"
        # We can reuse RJ patterns since they have similar format
        assembly_match = RJ_ASSEMBLY_RE.search(title)
        session_match = RJ_SESSION_RE.search(title)

        if assembly_match:
            term_number = int(assembly_match.group(1))
        if session_match:
            session = int(session_match.group(1))

    # Get term years from session_year field if available
    session_year_str = metadata.get("up_legislature_session_year", "")
    if session_year_str:
        try:
            session_year = int(session_year_str)
            # For UP, we'll assume the term is the same year (simplification)
            # In reality, this might need more complex logic
            term_start = session_year
            term_end = session_year
        except ValueError:
            term_start, term_end = 0, 0
    else:
        term_start, term_end = 0, 0

    return {
        "state_code": "UP",
        "languages": metadata.get("language", []),
        "year": year,
        "month": month,
        "day": day,
        "title_en": metadata.get("title", ""),
        "house": "Legislative Assembly",
        "session": session,
        "term_number": term_number,
        "term_start": term_start,
        "term_end": term_end,
        "archive_link": metadata["identifier-access"],
    }


def normalize_metadata_wb(metadata: dict) -> LegislatureMetadata:
    # Metadata handler for WB (West Bengal)

    # Date extraction from westbengal_legislature_proceeding_year
    # This field contains the year of the proceedings
    year_str = metadata.get("westbengal_legislature_proceeding_year", "0000")
    try:
        year = int(year_str)
    except ValueError:
        year = 0

    # For month and day, we'll use 0 as defaults since the metadata doesn't provide specific dates
    # The westbengal_legislature_dates field contains multiple dates, but we'll use the year from above
    month, day = 0, 0

    # Extract term number from westbengal_legislature_document_id
    # This appears to be a document ID, but we'll map it to term_number for consistency
    term_number = int(metadata.get("westbengal_legislature_document_id", 0))

    # Extract session from westbengal_legislature_document_type_id
    # This appears to be a document type ID, but we'll map it to session for consistency
    session = int(metadata.get("westbengal_legislature_document_type_id", 0))

    # House extraction
    house = metadata.get("westbengal_legislature_house", "Assembly")

    # Extract title
    title_en = metadata.get("westbengal_legislature_title", "") or metadata.get(
        "title", ""
    )

    # Parse legislature period for term years
    # Format: "28.11.1940 to 04.12.1940"
    period_str = metadata.get("westbengal_legislature_period", "")
    if period_str:
        # Try to extract years from the period string
        period_parts = period_str.split(" to ")
        if len(period_parts) == 2:
            try:
                # Extract year from first date (DD.MM.YYYY)
                first_date_parts = period_parts[0].strip().split(".")
                if len(first_date_parts) == 3:
                    term_start = int(first_date_parts[2])
                else:
                    term_start = year if year != 0 else 0

                # Extract year from second date (DD.MM.YYYY)
                second_date_parts = period_parts[1].strip().split(".")
                if len(second_date_parts) == 3:
                    term_end = int(second_date_parts[2])
                else:
                    term_end = year if year != 0 else 0
            except (ValueError, IndexError):
                term_start = year if year != 0 else 0
                term_end = year if year != 0 else 0
        else:
            term_start = year if year != 0 else 0
            term_end = year if year != 0 else 0
    else:
        term_start = year if year != 0 else 0
        term_end = year if year != 0 else 0

    # Parse sitting dates from westbengal_legislature_dates
    # Format: "28.11.1940, 29.11.1940, 30.11.1940, 02.12.1940, 03.12.1940 & 04.12.1940."
    dates_str = metadata.get("westbengal_legislature_dates", "")
    if dates_str:
        # Try to extract the first and last dates
        # Clean up the string by replacing commas and & with spaces
        cleaned_dates = dates_str.replace(",", "").replace("&", "").replace(".", "")
        date_parts = cleaned_dates.split()

        # Look for the first valid date (DD MM YYYY format)
        sitting_start_day, sitting_start_month, sitting_start_year = 0, 0, 0
        sitting_end_day, sitting_end_month, sitting_end_year = 0, 0, 0

        # Find all date components in the string
        date_components = []
        i = 0
        while i < len(date_parts):
            part = date_parts[i]
            # Check if it's a 2-digit number (could be day or month)
            if part.isdigit() and len(part) == 2:
                # Look ahead for month and year
                if i + 2 < len(date_parts):
                    next_part1 = date_parts[i + 1]
                    next_part2 = date_parts[i + 2]
                    if (
                        next_part1.isdigit()
                        and len(next_part1) == 2
                        and next_part2.isdigit()
                        and len(next_part2) == 4
                    ):
                        date_components.append(
                            (int(part), int(next_part1), int(next_part2))
                        )
                        i += 3
                        continue
            i += 1

        # If we found date components, use the first and last
        if date_components:
            sitting_start_day, sitting_start_month, sitting_start_year = (
                date_components[0]
            )
            sitting_end_day, sitting_end_month, sitting_end_year = date_components[-1]
    else:
        sitting_start_day, sitting_start_month, sitting_start_year = 0, 0, 0
        sitting_end_day, sitting_end_month, sitting_end_year = 0, 0, 0

    return {
        "state_code": "WB",
        "languages": metadata.get("language", []),
        "year": year,
        "month": month,
        "day": day,
        "title_en": title_en,
        "house": house,
        "session": session,
        "sitting_start_year": sitting_start_year,
        "sitting_start_month": sitting_start_month,
        "sitting_start_day": sitting_start_day,
        "sitting_end_year": sitting_end_year,
        "sitting_end_month": sitting_end_month,
        "sitting_end_day": sitting_end_day,
        "term_number": term_number,
        "term_start": term_start,
        "term_end": term_end,
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
        case "KA":
            return normalize_metadata_ka(metadata)
        case "KL":
            return normalize_metadata_kl(metadata)
        case "RJ":
            return normalize_metadata_rj(metadata)
        case "TG":
            return normalize_metadata_tg(metadata)
        case "TN":
            return normalize_metadata_tn(metadata)
        case "UP":
            return normalize_metadata_up(metadata)
        case "WB":
            return normalize_metadata_wb(metadata)
        case _:
            raise NotImplementedError()
