"""Optional, untrusted last-assessment display metadata, never routing authority."""

import re
from datetime import datetime
from .contact_identifier import validate_identifier


def validate_status(value):
    if (not isinstance(value, dict) or set(value) != {'attention', 'reason', 'assessed_at'}
            or type(value['attention']) is not bool
            or not isinstance(value['assessed_at'], str)
            or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value['assessed_at'])):
        raise ValueError('Status requires a boolean, a trimmed single-line Unicode reason (1..80 code points, without control characters), and a UTC assessment time.')
    validate_identifier(value['reason'])
    datetime.strptime(value['assessed_at'], '%Y-%m-%dT%H:%M:%SZ')
    return value


def _marker(description):
    from .description_fields import field_span
    marker = field_span(description, 'contact_status')
    if marker:
        validate_status(marker[2])
    return marker


def parse_status(description):
    try:
        marker = _marker(description)
        return marker[2] if marker else None
    except (ValueError, TypeError):
        return None


def remove_status(description):
    from .description_fields import write_field
    _marker(description)
    return write_field(description, 'contact_status', None)


def write_status(description, value):
    from .description_fields import write_field
    validate_status(value)
    if not isinstance(description, str):
        raise ValueError('Missing description; refusing metadata replacement.')
    _marker(description)
    return write_field(description, 'contact_status', value)
