"""Display-only channel labels, never authorization, grouping, or routing."""
import unicodedata

from .description_fields import FIELDS, WHITESPACE, field_span, write_field


def validate_identifier(identifier: str) -> str:
    if (not isinstance(identifier, str) or not 1 <= len(identifier) <= 80
            or identifier != identifier.strip()
            or any(unicodedata.category(c) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for c in identifier)):
        raise ValueError("identifier must be 1..80 characters, trimmed, single-line, without control characters")
    return identifier


def _marker(description):
    marker = field_span(description, 'mesh_identifier')
    if marker:
        validate_identifier(marker[2])
        start, end, _ = marker
        if description.startswith('[mesh_identifier', start):
            tail = description[end:].strip(WHITESPACE)
            if tail and not any(tail.startswith(label + ':') for label in FIELDS.values()):
                raise ValueError('Legacy label must be a suffix or precede named fields.')
    return marker


def parse_contact_identifier(description: str | None) -> str | None:
    marker = _marker(description)
    return marker[2] if marker else None


def write_contact_identifier(description: str | None, identifier: str) -> str:
    validate_identifier(identifier)
    _marker(description)
    return write_field(description, 'mesh_identifier', identifier)
