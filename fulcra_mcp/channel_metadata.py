"""Optional durable channel decisions on the owner's Event description.

These records are not grants or prerequisites for using a selected channel.
"""
import json
import re

from .connection import UUID_PATTERN, _uuid, channel_entry

from .description_fields import field_span, write_field


def _marker(description):
    span = field_span(description, 'agent_connection')
    if not span:
        return None
    start, end, value = span
    if not isinstance(value, dict) or value.get('version') != 1:
        raise ValueError('Invalid channel metadata.')
    peers = value.get('peers', [])
    if not isinstance(peers, list) or any(
        not isinstance(p, dict) or not _uuid(p.get('fulcra_userid'))
        or not isinstance(p.get('data_type'), str)
        or not re.fullmatch('Event/' + UUID_PATTERN, p['data_type']) for p in peers
    ):
        raise ValueError('Invalid channel associations.')
    return start, end, value


def parse_metadata(description):
    marker = _marker(description)
    return marker[2] if marker else {}


def is_template(description):
    try:
        return parse_metadata(description).get('invitation', {}).get('prefix') == 'open_invitation'
    except (ValueError, TypeError, AttributeError):
        return False


def write_metadata(description, metadata):
    _marker(description)
    updated = write_field(description, 'agent_connection', metadata or None)
    if metadata:
        _marker(updated)
    return updated


def save_metadata(api, own, data_type, metadata, expected=None):
    entry = channel_entry(api, own, data_type)
    if api.get_fulcra_userid() != own or not entry.get('recordable'):
        raise ValueError('Owned recordable channel required.')
    description = entry.get('description') or ''
    if expected is not None and parse_metadata(description) != expected:
        raise ValueError('Channel metadata changed; reload before writing.')
    updated = write_metadata(description, metadata)
    if updated != description:
        api.update_data_type('Event', data_type.split('/')[1], {'description': updated})
    if channel_entry(api, own, data_type).get('description') != updated:
        raise ValueError('Channel metadata save not verified.')


def add_peer(metadata, peer, incoming):
    pair = dict(fulcra_userid=peer, data_type=incoming)
    peers = metadata.setdefault('peers', [])
    if pair not in peers:
        peers.append(pair)
    metadata['version'] = 1


def save_peer(api, own, outbox, peer, incoming):
    # Explicit decisions need exact ownership, not invitation protocol evidence.
    if own == peer or not _uuid(peer):
        raise ValueError('Distinct exact peer required.')
    if any(not re.fullmatch('Event/' + UUID_PATTERN, channel) for channel in (outbox, incoming)):
        raise ValueError('Exact Event channel references required.')
    channel_entry(api, peer, incoming)
    metadata = parse_metadata(channel_entry(api, own, outbox).get('description'))
    expected = json.loads(json.dumps(metadata))
    add_peer(metadata, peer, incoming)
    save_metadata(api, own, outbox, metadata, expected)
