"""Lossless spans for human-readable channel fields and their legacy spelling."""
import json
import re

FIELDS = {
    'mesh_identifier': 'Contact label',
    'agent_connection': 'Connection details',
    'contact_status': 'Contact status',
    'connection_setup_session': 'Setup conversation',
    'standing_invitation_inviter': 'Invitation sender',
    'converted_from_mesh': 'Converted from mesh',
}
WHITESPACE = ' \t\r\n'
DECODER = json.JSONDecoder(parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def field_span(description, key):
    """Return one (start, end, value); reject malformed/duplicate target fields.

    Skip decoded JSON values so field-looking text inside strings is inert.
    Named fields start at a whitespace boundary; legacy bracket markers retain
    their historical anywhere-in-description placement.
    """
    text = '' if description is None else description
    if not isinstance(text, str):
        raise ValueError('Description must be text.')
    found = []
    i = 0
    while i < len(text):
        matched = None
        for candidate, label in FIELDS.items():
            legacy = candidate in {'standing_invitation_inviter', 'converted_from_mesh'}
            token = (candidate if legacy else '[' + candidate)
            if text.startswith(token, i) and (not legacy or i == 0 or text[i - 1] in WHITESPACE):
                matched = candidate, token, not legacy
                break
            token = label + ':'
            if text.startswith(token, i) and (i == 0 or text[i - 1] in WHITESPACE):
                matched = candidate, label, False
                break
        if matched:
            candidate, token, bracket = matched
            start = i
            pos = i + len(token)
            try:
                if text[pos:pos + 1] != ':':
                    raise ValueError('Missing colon.')
                pos += 1
                if text[pos:pos + 1] not in WHITESPACE or pos == len(text):
                    raise ValueError('Missing field whitespace.')
                while pos < len(text) and text[pos] in WHITESPACE:
                    pos += 1
                value, end = DECODER.raw_decode(text, pos)
                if bracket:
                    if text[end:end + 1] != ']':
                        raise ValueError('Missing closing bracket.')
                    end += 1
                if not bracket and end < len(text) and text[end] not in WHITESPACE:
                    raise ValueError('Missing field boundary.')
            except (ValueError, IndexError) as exc:
                if candidate == key:
                    raise ValueError('Malformed ' + FIELDS[key] + '.') from exc
                i += len(token)
                continue
            if candidate == key:
                found.append((start, end, value))
            i = end
            continue
        # Also protect tokens in unrelated, well-formed JSON values.
        if text[i] in '\"{[':
            try:
                _, i = DECODER.raw_decode(text, i)
                continue
            except ValueError:
                pass
        i += 1
    if len(found) > 1:
        raise ValueError('Duplicate ' + FIELDS[key] + '.')
    return found[0] if found else None


def render_field(key, value):
    # Escaped string whitespace survives catalog folding without changing JSON.
    encoded = json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False)
    return FIELDS[key] + ': ' + re.sub(r' {2,}', lambda m: '\\u0020' * len(m[0]), encoded)


def write_field(description, key, value):
    text = '' if description is None else description
    span = field_span(text, key)
    replacement = render_field(key, value) if value is not None else ''
    if span:
        start, end, _ = span
        if replacement:
            if start and text[start - 1] not in WHITESPACE:
                replacement = '\n' + replacement
            if end < len(text) and text[end] not in WHITESPACE:
                replacement += '\n'
        return text[:start] + replacement + text[end:]
    return text + ('\n' if text and replacement else '') + replacement
