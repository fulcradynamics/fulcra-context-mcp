"""Optional, untrusted last-assessment display metadata, never routing authority."""
import json
import re
from datetime import datetime
from .contact_identifier import validate_identifier

TOKEN = '[contact_status:'


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
    """(start, end, value) of the single status marker, wherever whitespace
    folding put it, or None if absent or malformed."""
    if not isinstance(description, str) or description.count(TOKEN) != 1:
        return None
    start = description.index(TOKEN)
    try:
        if description[start + len(TOKEN)] != ' ':
            return None
        value, end = json.JSONDecoder().raw_decode(description, start + len(TOKEN) + 1)
        validate_status(value)
    except (ValueError, TypeError, IndexError):
        return None
    return (start, end + 1, value) if description[end:end + 1] == ']' else None


def parse_status(description):
    marker = _marker(description)
    return marker[2] if marker else None


def remove_status(description):
    """The description without its status marker and the whitespace before it."""
    start, end, _ = _marker(description)
    return description[:start].rstrip(' \t\r\n') + description[end:]


def write_status(description, value):
    validate_status(value)
    if not isinstance(description, str):
        raise ValueError('Missing description; refusing metadata replacement.')
    marker = '[contact_status: ' + json.dumps(value, separators=(',', ':')) + ']'
    if TOKEN in description:
        if parse_status(description) is None:
            raise ValueError('Malformed status; refusing metadata replacement.')
        start, end, _ = _marker(description)
        return description[:start] + marker + description[end:]
    # Insert before the final label suffix; every existing byte stays unchanged.
    from .contact_identifier import _marker as label_marker
    label = label_marker(description)
    index = label[0] if label else len(description)
    before = description[:index]
    return before + ('' if before.endswith('\n') else '\n') + marker + ('\n' if label else '') + description[index:]
