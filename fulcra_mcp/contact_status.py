"""Optional, untrusted last-assessment display metadata, never routing authority."""
import json
import re
from datetime import datetime
from .mesh_identifier import validate_identifier

TOKEN = '[contact_status:'
PATTERN = re.compile(r'^\[contact_status: (\{[^\r\n]*\})\]$', re.MULTILINE)


def validate_status(value):
    if (not isinstance(value, dict) or set(value) != {'attention', 'reason', 'assessed_at'}
            or type(value['attention']) is not bool
            or not isinstance(value['assessed_at'], str)
            or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value['assessed_at'])):
        raise ValueError('Status requires a boolean, a trimmed single-line Unicode reason (1..80 code points, without control characters), and a UTC assessment time.')
    validate_identifier(value['reason'])
    datetime.strptime(value['assessed_at'], '%Y-%m-%dT%H:%M:%SZ')
    return value


def parse_status(description):
    if not isinstance(description, str) or description.count(TOKEN) != 1:
        return None
    match = PATTERN.search(description)
    try:
        return validate_status(json.loads(match[1])) if match else None
    except (ValueError, TypeError):
        return None


def write_status(description, value):
    validate_status(value)
    if not isinstance(description, str):
        raise ValueError('Missing description; refusing metadata replacement.')
    marker = '[contact_status: ' + json.dumps(value, separators=(',', ':')) + ']'
    if TOKEN in description:
        if parse_status(description) is None:
            raise ValueError('Malformed status; refusing metadata replacement.')
        match = PATTERN.search(description)
        return description[:match.start()] + marker + description[match.end():]
    # Insert before the final label suffix; every existing byte stays unchanged.
    from .mesh_identifier import _marker
    label = _marker(description)
    index = label[0] if label else len(description)
    before = description[:index]
    return before + ('' if before.endswith('\n') else '\n') + marker + ('\n' if label else '') + description[index:]
