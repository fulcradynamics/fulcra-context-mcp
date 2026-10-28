import pytest
import json
import re

from fulcra_mcp.contact_identifier import parse_contact_identifier, write_contact_identifier
from fulcra_mcp.channel_metadata import parse_metadata, write_metadata
from fulcra_mcp.description_fields import FIELDS, field_span, render_field, write_field


def test_named_label_and_deliberate_legacy_edit():
    assert parse_contact_identifier('Agent contact channel\nContact label: "Sura Novi\'s agent"') == "Sura Novi's agent"
    assert write_contact_identifier('Intro\n[mesh_identifier: "Old"]\n', 'New') == 'Intro\nContact label: "New"\n'


def test_adjacent_legacy_spans_get_named_field_boundaries():
    text = 'Notes[agent_connection: {"version":1}]More'
    updated = write_metadata(text, {'version': 1})
    assert updated == 'Notes\nConnection details: {"version":1}\nMore'
    assert parse_metadata(updated) == {'version': 1}
    assert parse_contact_identifier(write_contact_identifier('Notes[mesh_identifier: "Old"]', 'New')) == 'New'


@pytest.mark.parametrize('prefix,suffix', [
    ('Notes  unchanged', ''),
    ('', 'More  notes'),
    ('Notes  unchanged', 'More  notes'),
    ('[mesh_identifier: "Old"]', '[connection_setup_session: "kept"]'),
    ('Notes\t', '\r\nMore  notes'),
])
def test_legacy_replacement_preserves_both_edges(prefix, suffix):
    old = {'version': 1, 'invitation': {'state': 'prepared', 'code': '0123456789abcdef0123456789abcdef'}}
    new = old | {'invitation': old['invitation'] | {'state': 'completed'}}
    text = prefix + '[agent_connection: ' + json.dumps(old) + ']' + suffix
    assert parse_metadata(text) == old
    updated = write_metadata(text, new)
    left = '\n' if prefix and prefix[-1] not in ' \t\r\n' else ''
    right = '\n' if suffix and suffix[0] not in ' \t\r\n' else ''
    assert updated == prefix + left + render_field('agent_connection', new) + right + suffix
    assert parse_metadata(updated) == new
    assert parse_metadata(re.sub(r'\s+', ' ', updated)) == new
    assert write_metadata(updated, new) == updated
    assert write_metadata(text, {}) == prefix + suffix
    if prefix.startswith('[mesh_identifier:'):
        assert parse_contact_identifier(updated) == 'Old'
        assert field_span(updated, 'connection_setup_session')[2] == 'kept'
        renamed = write_contact_identifier(updated, 'New')
        assert parse_contact_identifier(renamed) == 'New'
        assert parse_metadata(renamed) == new


@pytest.mark.parametrize('prefix,suffix', [('Notes', ''), ('', 'More'), ('Notes', 'More'),
                                          ('[agent_connection: {"version":1}]', '[contact_status: {}]')])
def test_legacy_label_replacement_preserves_both_edges(prefix, suffix):
    text = prefix + '[mesh_identifier: "Old"]' + suffix
    assert field_span(text, 'mesh_identifier')[2] == 'Old'
    updated = write_field(text, 'mesh_identifier', 'New')
    assert updated == prefix + ('\n' if prefix else '') + 'Contact label: "New"' + ('\n' if suffix else '') + suffix
    assert parse_contact_identifier(updated) == 'New'
    if prefix.startswith('[agent_connection:'):
        assert parse_metadata(updated) == {'version': 1}
        assert field_span(updated, 'contact_status')[2] == {}


def test_save_adjacent_legacy_metadata_roundtrips(monkeypatch):
    from unittest.mock import Mock
    from fulcra_mcp import channel_metadata

    old = {'version': 1, 'invitation': {'state': 'prepared', 'code': '0123456789abcdef0123456789abcdef'}}
    new = old | {'invitation': old['invitation'] | {'state': 'completed'}}
    entry = {'recordable': True, 'description': 'Notes[agent_connection: ' + json.dumps(old) + ']More'}
    api = Mock()
    api.get_fulcra_userid.return_value = 'owner'
    api.update_data_type.side_effect = lambda kind, identifier, fields: entry.update(fields)
    monkeypatch.setattr(channel_metadata, 'channel_entry', lambda *args: entry)
    channel_metadata.save_metadata(api, 'owner', 'Event/channel', new, expected=old)
    api.update_data_type.assert_called_once_with('Event', 'channel', {'description': entry['description']})
    assert entry['description'] == 'Notes\n' + render_field('agent_connection', new) + '\nMore'
    assert parse_metadata(entry['description']) == new


def test_nested_tokens_and_preservation():
    text = 'Intro\nConnection details: {"version":1,"extra":{"text":"[mesh_identifier: \\\"fake\\\"] Contact label: fake","array":[{}]}}\nContact label: "Real"\nUnknown: keep'
    assert parse_contact_identifier(text) == 'Real'
    metadata = parse_metadata(text)
    assert metadata['extra']['array'] == [{}]
    assert write_contact_identifier(text, 'New').endswith('Contact label: "New"\nUnknown: keep')
    assert parse_metadata(write_metadata(text, metadata)) == metadata
    assert parse_contact_identifier(' '.join(text.splitlines())) == 'Real'


@pytest.mark.parametrize('text', [
    'Contact label: "one" [mesh_identifier: "two"]',
    'Contact label: "one" Contact label: "two"',
    'Contact label: invalid',
    'Contact label: "one"junk',
])
def test_refuse_malformed_or_duplicate_target(text):
    with pytest.raises(ValueError):
        write_contact_identifier(text, 'New')


@pytest.mark.parametrize('key', FIELDS)
def test_every_field_legacy_new_mixed_and_exact_spans(key):
    value = {'nested': [1, {'text': 'café "[]" Contact label: fake'}]}
    bare = key in {'converted_from_mesh', 'standing_invitation_inviter'}
    legacy = ('' if bare else '[') + key + ': ' + json.dumps(value) + ('' if bare else ']')
    named = render_field(key, value)
    for field in [legacy, named]:
        text = 'Notes  unchanged\n' + field + '\nUnknown: keep'
        assert field_span(text, key)[2] == value
        assert write_field(text, key, value) == 'Notes  unchanged\n' + named + '\nUnknown: keep'
        assert write_field(text, key, None) == 'Notes  unchanged\n\nUnknown: keep'
        assert field_span(re.sub(r'\s+', ' ', text), key)[2] == value
    for duplicate in [legacy + '\n' + named, named + ' ' + named, legacy + legacy if not bare else legacy + ' ' + legacy]:
        with pytest.raises(ValueError):
            write_field(duplicate, key, value)
    for invalid in [FIELDS[key] + ': bad', FIELDS[key] + ': {"x":', FIELDS[key] + ': "x"junk']:
        with pytest.raises(ValueError):
            write_field(invalid, key, value)


def test_folding_safe_unicode_and_nested_marker_labels():
    label = 'café  "[mesh_identifier: fake]"\u00a0test'
    text = write_contact_identifier('Notes', label)
    assert parse_contact_identifier(re.sub(r'\s+', ' ', text)) == label
    assert write_contact_identifier(text, label) == text


def test_named_status_validation_and_legacy_edit():
    from fulcra_mcp.contact_status import parse_status, write_status
    value = {'attention': True, 'reason': 'Waiting [contact_status: fake]', 'assessed_at': '2026-10-13T12:00:00Z'}
    legacy = '[contact_status: ' + json.dumps(value) + ']'
    text = write_status('Intro\n' + legacy + '\nUnknown: keep', value)
    assert parse_status(text) == value
    assert text.startswith('Intro\nContact status: ')
    assert parse_status(text + '\n' + legacy) is None
    with pytest.raises(ValueError):
        write_status(text + '\n' + legacy, value)
    with pytest.raises(ValueError):
        write_status(text, value | {'assessed_at': '2026-02-30T00:00:00Z'})
