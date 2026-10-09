"""Display-only mesh labels in an optional JSON-string description suffix.

Never use these untrusted labels for authorization, grouping, or routing.
"""
import json
import re
import unicodedata

TOKEN = "[mesh_identifier"
PREFIX = TOKEN + ": "
# Suffix whitespace is exactly JSON whitespace, shared with the JS parser.
# Do not use default strip()/trim(): their Unicode whitespace sets differ.
SUFFIX_WHITESPACE = " \t\r\n"


def validate_identifier(identifier: str) -> str:
    if (not isinstance(identifier, str) or not 1 <= len(identifier) <= 80
            or identifier != identifier.strip()
            or any(unicodedata.category(c) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for c in identifier)):
        raise ValueError("identifier must be 1..80 characters, trimmed, single-line, without control characters")
    return identifier


def _marker(description: str | None) -> tuple[int, int, str] | None:
    if description is None:
        return None
    if not isinstance(description, str):
        raise ValueError("description must be text")
    start = description.find(TOKEN)
    if start < 0:
        return None
    # Decode the JSON string, not a bracket/quote regex: both can be in labels.
    if not description.startswith(PREFIX, start):
        raise ValueError("Malformed mesh_identifier marker")
    try:
        value, end = json.JSONDecoder().raw_decode(description, start + len(PREFIX))
        validate_identifier(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("Malformed mesh_identifier marker") from exc
    if description[end:end + 1] != "]" or description[end + 1:].strip(SUFFIX_WHITESPACE):
        raise ValueError("Multiple or malformed mesh_identifier markers; expected one suffix")
    return start, end + 1, value


def parse_mesh_identifier(description: str | None) -> str | None:
    marker = _marker(description)
    return marker[2] if marker else None


def normalize_catalog_description(description: str) -> str:
    """Fold prose whitespace without changing (or repairing) marker data."""
    try:
        marker = _marker(description)
    except ValueError:
        return description
    if not marker:
        return re.sub(r"\s+", " ", description).strip()
    start, end, _ = marker
    prose = re.sub(r"\s+", " ", description[:start]).strip()
    return (prose + " " if prose else "") + description[start:end]


def write_mesh_identifier(description: str | None, identifier: str) -> str:
    validate_identifier(identifier)
    marker = _marker(description)
    description = description or ""
    if marker and marker[2] == identifier:
        return description
    # Escape whitespace within the JSON string so catalog whitespace folding
    # cannot change the value (including repeated spaces and Unicode spaces).
    quoted = json.dumps(identifier, ensure_ascii=True).replace(" ", "\\u0020")
    suffix = PREFIX + quoted + "]"
    if marker:
        start, end, _ = marker
        return description[:start] + suffix + description[end:]
    return description + ("\n" if description else "") + suffix
