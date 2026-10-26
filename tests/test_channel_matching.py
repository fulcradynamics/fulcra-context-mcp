"""Channels are identified by ownership, schema and grants, not display text."""
import json

import pytest

from test_direct_connection_send import backend, ARGS
from test_agent_invitations import api, OWN, PEER, OUT, IN, handshake
from fulcra_mcp import agent_invitations as invitations
from fulcra_mcp.mentions import _thread_labels
from fulcra_api import connections


@pytest.mark.parametrize('description', ['', 'My project messages', None,
    '[agent_connection: invalid]',
    '[agent_connection: {"version":1,"peers":[{"fulcra_userid":"00000000-0000-4000-8000-000000000099","data_type":"Event/00000000-0000-4000-8000-000000000099"}]}'])
async def test_send_selected_unmarked_channel(call, backend, description):
    fake, _ = backend
    fake.resolve_data_type.return_value[0]['description'] = description
    fake.get_datashares.return_value[0]['datashare_name'] = 'Project'
    result = json.loads(await call('send_agent_message', dict(
        connection=ARGS['outbox'], sender=ARGS['sender'], body=ARGS['body'], record_id=ARGS['mid'])))
    assert result['status'] == 'posted'


def test_discover_schema_compatible_unmarked_channel():
    entry = dict(id=IN, fulcra_userid=PEER, description='Project messages',
                 fields=connections.CHANNEL_FIELDS['properties'],
                 required_fields=connections.CHANNEL_FIELDS['required'])
    shares = dict(own_fulcra_userid=OWN, outgoing=[], incoming=[dict(
        sharing_fulcra_userid=PEER, grant_type='user', data_types=[IN], datashare_name=None)])
    assert PEER in _thread_labels({'data types usable with: get_records': [entry]}, shares)


def test_match_unmarked_channel_and_grant(api):
    code = invitations.prepare(api, OUT)['code']
    api.catalog[1]['description'] = 'Messages for this project'
    api.get_shared_datasets.return_value[1]['datashare_name'] = None
    handshake(api, code)
    assert invitations.match(api)['results'][0]['status'] == 'matched'


@pytest.mark.parametrize('failure', [None, 'schema', 'catalog', 'incomplete'])
def test_unrelated_event_is_skipped_only_after_successful_resolution(api, failure):
    from test_agent_invitations import channel, incoming
    other = 'Event/00000000-0000-4000-8000-000000000030'
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    api.catalog.append(channel(other, PEER))
    api.get_shared_datasets.return_value.append(dict(incoming(channel=other), datashare_name='Workout export'))
    def schema(data_type, *args, **kwargs):
        if data_type == other:
            if failure == 'schema':
                raise OSError('unavailable')
            if failure == 'incomplete':
                return {}
            return {'type': 'object', 'properties': {'note': {'type': 'string'}}}
        return {'type': 'object', **connections.CHANNEL_FIELDS}
    api.v1_catalog_schema.side_effect = schema
    if failure == 'catalog':
        api.catalog.pop()
    result = invitations.match(api)
    if failure:
        assert result['status'] == 'unavailable'
        assert result['diagnostic']['stage'] == 'incoming_channel'
        api.create_datashare.assert_not_called()
    else:
        assert result['results'][0]['status'] == 'matched'
        assert all(other not in call.args[0] for call in api.fulcra_v1_records.call_args_list)


def test_invitation_lives_on_outbox_and_preserves_other_metadata(api):
    original = 'Project notes\n[connection_setup_session: "codex://threads/00000000-0000-4000-8000-000000000001"]\n[mesh_identifier: "Alex"]'
    api.catalog[0]['description'] = original
    prepared = invitations.prepare(api, OUT)
    assert prepared['code'] in api.catalog[0]['description']
    api.create_data_type.assert_not_called()
    from fulcra_mcp.channel_metadata import parse_metadata, write_metadata
    metadata = parse_metadata(api.catalog[0]['description'])
    assert metadata['invitation']['state'] == 'prepared'
    assert write_metadata(api.catalog[0]['description'], None) == original
    handshake(api, prepared['code'])
    assert invitations.match(api)['results'][0]['status'] == 'matched'
    metadata = parse_metadata(api.catalog[0]['description'])
    assert metadata['peers'] == [{'fulcra_userid': PEER, 'data_type': IN}]
    assert metadata['invitation']['state'] == 'completed'
    assert api.catalog[1]['description'] == 'connect-our-agents channel'


def test_explicit_association_needs_no_invitation_or_peer_metadata(api):
    from fulcra_mcp.channel_metadata import save_peer, parse_metadata
    api.catalog[1]['description'] = '[agent_connection: invalid stale metadata]'
    api.catalog[1]['fields'] = {'custom_note': {'type': 'string'}}
    api.catalog[1]['required_fields'] = ['custom_note']
    api.v1_catalog_schema.side_effect = AssertionError('Explicit pairing needs no protocol schema')
    save_peer(api, OWN, OUT, PEER, IN)
    assert parse_metadata(api.catalog[0]['description'])['peers'] == [
        {'fulcra_userid': PEER, 'data_type': IN}]
    api.create_datashare.assert_not_called()
    api.create_data_type.assert_not_called()
    api.v1_catalog_schema.assert_not_called()


def test_metadata_save_requires_readback(api):
    api.update_data_type.side_effect = lambda *args: None
    with pytest.raises(ValueError, match='verified'):
        invitations.prepare(api, OUT)


async def test_open_template_cannot_be_selected_for_send(call, backend):
    fake, _ = backend
    fake.resolve_data_type.return_value[0]['description'] = '[agent_connection: {"version":1,"invitation":{"prefix":"open_invitation","state":"prepared","code":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","responses":{}}}]'
    result = json.loads(await call('send_agent_message', dict(
        connection=ARGS['outbox'], sender=ARGS['sender'], body=ARGS['body'], record_id=ARGS['mid'])))
    assert result['status'] == 'rejected'
    fake.record_data_type.assert_not_called()


def test_multiple_peers_and_unrelated_metadata_survive_matching(api):
    from fulcra_mcp.channel_metadata import parse_metadata, write_metadata, save_peer
    from test_agent_invitations import OTHER, channel
    existing = {'version': 1, 'peers': [{'fulcra_userid': OTHER, 'data_type': IN}], 'extension': {'keep': True}}
    api.catalog[0]['description'] = write_metadata('Notes\n[mesh_identifier: "Alex"]', existing)
    api.catalog.append(channel(IN, OTHER))
    save_peer(api, OWN, OUT, PEER, IN)
    save_peer(api, OWN, OUT, PEER, IN)
    value = parse_metadata(api.catalog[0]['description'])
    assert value['peers'] == existing['peers'] + [{'fulcra_userid': PEER, 'data_type': IN}]
    assert value['extension'] == {'keep': True}
    assert api.catalog[0]['description'].endswith('Notes\n[mesh_identifier: "Alex"]')


def test_preparing_another_outbox_does_not_rewrite_completed_decisions(api):
    from fulcra_mcp.channel_metadata import parse_metadata, write_metadata
    from test_agent_invitations import channel
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    assert invitations.match(api)['results'][0]['status'] == 'matched'
    metadata = parse_metadata(api.catalog[0]['description'])
    metadata['peers'] = []  # A subsequent explicitly edited decision.
    api.catalog[0]['description'] = write_metadata(api.catalog[0]['description'], metadata)
    before = api.catalog[0]['description']
    second = OUT[:-1] + '1'
    api.catalog.append(channel(second, OWN))
    api.update_data_type.reset_mock()
    invitations.prepare(api, second)
    assert api.catalog[0]['description'] == before
    assert api.update_data_type.call_count == 1
