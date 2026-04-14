"""
The metadata of the Internet Archive collections is not normalized, and each
state has a different subset of fields available. The fields are
also differently named for each state. This module provides The normalized list
of fields, statewise. For e.g. if one state has an debate_date, and another
a date_of_debate, this module will provide "debate_date" as a common field.
"""
from typing import TypedDict, NotRequired, Any, Annotated, Literal
from pydantic import BaseModel
from dataclasses import dataclass

# Type for field metadata
FieldMetadata = dict[Literal["facet", "locale", "searchable"], bool | str]

class LegislatureMetadata(TypedDict):
    """
    List of all fields provided by all states. Here mostly for
    documentation and understanding the possible list of fields
    Additional fields may be needed as more states get added
    """
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

STATE_CODES = ["AP", "AS", "RJ", "KA", "KL", "TN", "TS", "UP", "WB", "TG"]

@dataclass
class FieldParams:
    """Metadata parameters for each field"""
    facet: bool = False
    locale: str | None = None
    searchable: bool = True

class LegislatureMetadataBase(BaseModel):
    """
    Base class with fields that are common to all the collections.
    Each collection is expected to inherit this class to declare
    the additional fields it will provide (can also be no additional fields)
    """
    state_code: Annotated[str, {"facet": False, "description": "State code"}]
    file_name: Annotated[str, {"facet": False, "description": "File name"}]
    year: Annotated[int, {"facet": True, "description": "Year"}]
    month: Annotated[int, {"facet": True, "description": "Month"}]
    day: Annotated[int, {"facet": True, "description": "Day"}]
    title_en: Annotated[str, {"facet": False, "description": "Title in English"}]
    archive_link: Annotated[str, {"facet": False, "description": "Archive link"}]

    @classmethod
    def get_field_schema(cls) -> list[dict[str, Any]]:
        """Generate schema definition from Pydantic model fields with Annotated metadata"""
        schema = []
        
        # Get the original annotations to access metadata
        annotations = cls.__annotations__
        
        for name, field_info in cls.model_fields.items():
            # Get metadata from Annotated type
            facet = False
            locale = None
            description = ""
            
            # Check if this field has Annotated metadata
            if name in annotations:
                annotation = annotations[name]
                if hasattr(annotation, '__metadata__'):
                    for metadata in annotation.__metadata__:
                        if isinstance(metadata, dict):
                            facet = metadata.get('facet', False)
                            locale = metadata.get('locale', None)
                            description = metadata.get('description', "")
                            break
            
            # Convert Python type to schema type
            type_map = {
                str: "string",
                int: "int32",
                list: "string[]"
            }
            
            # Get the base type
            base_type = field_info.annotation
            if hasattr(field_info.annotation, "__origin__"):
                base_type = field_info.annotation.__args__[0] if field_info.annotation.__args__ else str
            
            schema_type = type_map.get(base_type, "string")
            
            field_def = {
                "name": name,
                "type": schema_type,
                "facet": facet,
            }
            
            if locale:
                field_def["locale"] = locale
            if description:
                field_def["description"] = description
                
            schema.append(field_def)
        return schema

# Generate base fields from the base class
BASE_FIELDS = LegislatureMetadataBase.get_field_schema()

class LegislatureMetadataAP(LegislatureMetadataBase):
    """Andhra Pradesh specific metadata fields"""
    house: Annotated[str, {"facet": True, "description": "House"}]
    session: Annotated[int, {"facet": True, "description": "Session"}]
    sitting_number: Annotated[int, {"facet": False, "description": "Sitting number"}]
    sitting_start_year: Annotated[int, {"facet": False, "description": "Sitting start year"}]
    sitting_start_month: Annotated[int, {"facet": False, "description": "Sitting start month"}]
    sitting_start_day: Annotated[int, {"facet": False, "description": "Sitting start day"}]
    sitting_end_year: Annotated[int, {"facet": False, "description": "Sitting end year"}]
    sitting_end_month: Annotated[int, {"facet": False, "description": "Sitting end month"}]
    sitting_end_day: Annotated[int, {"facet": False, "description": "Sitting end day"}]
    term_number: Annotated[int, {"facet": True, "description": "Term number"}]
    term_start: Annotated[int, {"facet": False, "description": "Term start"}]
    term_end: Annotated[int, {"facet": False, "description": "Term end"}]

class LegislatureMetadataKA(LegislatureMetadataBase):
    """Karnataka specific metadata fields"""
    session: Annotated[int, {"facet": True, "description": "Session"}]
    term_number: Annotated[int, {"facet": True, "description": "Term number"}]
    term_start: Annotated[int, {"facet": False, "description": "Term start"}]
    term_end: Annotated[int, {"facet": False, "description": "Term end"}]
    section_type: Annotated[str, {"facet": True, "description": "Section type"}]
    start_page: Annotated[int, {"facet": False, "description": "Start page"}]
    end_page: Annotated[int, {"facet": False, "description": "End page"}]
    book_id: Annotated[int, {"facet": False, "description": "Book ID"}]
    place_session: Annotated[str, {"facet": True, "description": "Place session"}]
    minister_en: Annotated[str, {"facet": False, "description": "Minister name (English)"}]
    minister_kn: Annotated[str, {"facet": False, "description": "Minister name (Kannada)", "locale": "kn"}]
    questioner_en: Annotated[str, {"facet": False, "description": "Questioner name (English)"}]
    questioner_kn: Annotated[str, {"facet": False, "description": "Questioner name (Kannada)", "locale": "kn"}]
    participants_en: Annotated[str, {"facet": False, "description": "Participants (English)"}]
    participants_kn: Annotated[str, {"facet": False, "description": "Participants (Kannada)", "locale": "kn"}]

class LegislatureMetadataKL(LegislatureMetadataBase):
    """Kerala specific metadata fields"""
    discussions: Annotated[str, {"facet": False, "description": "Discussions", "locale": "ml"}]
    subject: Annotated[str, {"facet": False, "description": "Subject"}]

class LegislatureMetadataTG(LegislatureMetadataBase):
    """Telangana specific metadata fields"""
    house: Annotated[str, {"facet": True, "description": "House"}]
    session: Annotated[int, {"facet": True, "description": "Session"}]
    sitting_number: Annotated[int, {"facet": False, "description": "Sitting number"}]
    sitting_start_year: Annotated[int, {"facet": False, "description": "Sitting start year"}]
    sitting_start_month: Annotated[int, {"facet": False, "description": "Sitting start month"}]
    sitting_start_day: Annotated[int, {"facet": False, "description": "Sitting start day"}]
    sitting_end_year: Annotated[int, {"facet": False, "description": "Sitting end year"}]
    sitting_end_month: Annotated[int, {"facet": False, "description": "Sitting end month"}]
    sitting_end_day: Annotated[int, {"facet": False, "description": "Sitting end day"}]
    term_number: Annotated[int, {"facet": True, "description": "Term number"}]
    term_start: Annotated[int, {"facet": False, "description": "Term start"}]
    term_end: Annotated[int, {"facet": False, "description": "Term end"}]

# Map state codes to their metadata classes
STATE_METADATA_CLASSES = {
    "AP": LegislatureMetadataAP,
    "KA": LegislatureMetadataKA,
    "KL": LegislatureMetadataKL,
    "TG": LegislatureMetadataTG,
    # States that only use base fields
    "AS": LegislatureMetadataBase,
    "RJ": LegislatureMetadataBase,
    "TN": LegislatureMetadataBase,
    "UP": LegislatureMetadataBase,
    "WB": LegislatureMetadataBase,
    "TS": LegislatureMetadataBase,
}


def get_metadata_schema(state_code: str | None = None) -> dict[str, list[dict[str, Any]]] | list[dict[str, Any]]:
    """
    Generate metadata schema for a specific state or all states.
    This is only needed when creating/updating search indexes.
    
    Args:
        state_code: If provided, returns schema for just this state. Otherwise returns all states.
    
    Returns:
        Dictionary of state_code -> schema for all states, or just the schema list for one state.
    """
    if state_code:
        # Generate schema for a single state
        if state_code not in STATE_METADATA_CLASSES:
            raise ValueError(f"Unknown state code: {state_code}")
        
        metadata_class = STATE_METADATA_CLASSES[state_code]
        # Get state-specific fields (excluding base class fields)
        state_fields = []
        for field_def in metadata_class.get_field_schema():
            if field_def["name"] not in [f["name"] for f in BASE_FIELDS]:
                state_fields.append(field_def)
        
        # Start with discussions field (common to all states)
        schema = [{"name": "discussions", "type": "string"}]
        schema.extend(state_fields)
        return schema
    else:
        # Generate schema for all states
        schema = {}
        for state_code in STATE_CODES:
            schema[state_code] = get_metadata_schema(state_code)
        return schema


# For backward compatibility, keep METADATA_SCHEMA as a module-level variable
# but make it lazy-loaded
_METADATA_SCHEMA = None

def __getattr__(name: str) -> Any:
    """Lazy load METADATA_SCHEMA on first access"""
    if name == "METADATA_SCHEMA":
        global _METADATA_SCHEMA
        if _METADATA_SCHEMA is None:
            _METADATA_SCHEMA = get_metadata_schema()
        return _METADATA_SCHEMA
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
