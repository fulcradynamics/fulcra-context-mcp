"""Owned override tools exercise real SDK metadata transport."""
import pytest
from fastmcp import Client
from fulcra_mcp.main import mcp
from fulcra_mcp import tools
from test_contact_status import backend, DESCRIPTION
from test_connection_send import OWN, PEER, OUT


async def test_multiparty_overrides_require_exact_audience(backend, monkeypatch):
    from fulcra_mcp import contact_preferences as policy
    other = '00000000-0000-4000-8000-000000000007'
    backend['shares'][0]['permissions'].append({'allowed_fulcra_userid': other})
    monkeypatch.setattr(policy, 'read', lambda api: policy.DEFAULTS)
    async with Client(mcp) as client:
        args = {'data_type': OUT, 'peer_userid': PEER}
        assert (await client.call_tool('get_contact_preferences', args, raise_on_error=False)).is_error
        args['expected_peer_userids'] = [PEER, other]
        saved = await client.call_tool('set_contact_preferences', {**args,
            'overrides': {'attention_peer_membership_announcements': False}})
        assert saved.structured_content['verified'] is True
        readback = await client.call_tool('get_contact_preferences', args)
        assert readback.structured_content['values']['attention_peer_membership_announcements'] is False
        backend['shares'][0]['permissions'].pop()
        assert (await client.call_tool('get_contact_preferences', args, raise_on_error=False)).is_error
        assert len(backend['writes']) == 1


async def test_override_save_and_owned_read(backend, monkeypatch):
    from fulcra_mcp import contact_preferences as policy
    monkeypatch.setattr(policy, 'read', lambda api: policy.DEFAULTS)
    async with Client(mcp) as client:
        saved = (await client.call_tool('set_contact_preferences', {
            'data_type': OUT, 'peer_userid': PEER,
            'overrides': {'autonomous_replies': True, 'notifications': 'none'}})).structured_content
        assert saved['verified'] is True
        result = (await client.call_tool('get_contact_preferences', {
            'data_type': OUT, 'peer_userid': PEER})).structured_content
        assert result['values']['autonomous_replies'] is False
        assert result['values']['notifications'] == 'none'
        assert result['owner'] == OWN
        assert backend['row']['description'].endswith('[mesh_identifier: "Travel"]')
        assert '[connection_setup_session:' in backend['row']['description']


@pytest.mark.parametrize('option', ['peer', 'denied', 'unverified', 'schema'])
async def test_override_rejects_unowned_invalid_or_unverified(backend, option):
    if option == 'peer': backend['row']['fulcra_userid'] = PEER
    if option == 'denied': backend['denied'] = True
    if option == 'unverified': backend['persist'] = False
    if option == 'schema': backend['schema'] = {'properties': {}}
    async with Client(mcp) as client:
        result = await client.call_tool('set_contact_preferences', {
            'data_type': OUT, 'peer_userid': PEER, 'overrides': {'notifications': 'none'}}, raise_on_error=False)
        assert result.is_error
    assert len(backend['writes']) <= 1
    if option in ('peer', 'schema'): assert not backend['writes']
