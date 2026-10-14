"""Contact override tools verify the connection, then store overrides privately."""
import pytest
from fastmcp import Client
from fulcra_mcp.main import mcp
from fulcra_mcp import contact_preferences as policy
from test_contact_status import backend, DESCRIPTION
from test_connection_send import OWN, PEER, OUT


@pytest.fixture
def store(backend, monkeypatch):
    document = dict(version=1, global_preferences={}, overrides={})
    monkeypatch.setattr(policy, 'load', lambda api: document)
    def save(api, change):
        change(document)
        return document
    monkeypatch.setattr(policy, '_save', save)
    return document


async def test_override_save_and_read_never_touch_connection(backend, store):
    args = {'data_type': OUT, 'peer_userid': PEER}
    async with Client(mcp) as client:
        saved = (await client.call_tool('set_contact_preferences', {**args, 'overrides': {
            'pause_autonomous_replies': True, 'notifications': 'none'}})).structured_content
        assert saved['verified'] is True
        result = (await client.call_tool('get_contact_preferences', args)).structured_content
        assert result['values']['pause_autonomous_replies'] is True
        assert result['values']['notifications'] == 'none'
        assert result['values']['acknowledge_messages'] is True
        assert store['overrides'] == {OUT + '|' + PEER: {'pause_autonomous_replies': True, 'notifications': 'none'}}
        await client.call_tool('set_contact_preferences', {**args, 'overrides': {}})
        assert store['overrides'] == {}
    assert not backend['writes']
    assert backend['row']['description'] == DESCRIPTION


async def test_multiparty_overrides_require_exact_audience(backend, store):
    other = '00000000-0000-4000-8000-000000000007'
    backend['shares'][0]['permissions'].append({'allowed_fulcra_userid': other})
    async with Client(mcp) as client:
        args = {'data_type': OUT, 'peer_userid': PEER}
        assert (await client.call_tool('get_contact_preferences', args, raise_on_error=False)).is_error
        args['expected_peer_userids'] = [PEER, other]
        saved = await client.call_tool('set_contact_preferences', {**args,
            'overrides': {'attention_peer_membership_announcements': False}})
        assert saved.structured_content['verified'] is True
        readback = await client.call_tool('get_contact_preferences', args)
        assert readback.structured_content['values']['attention_peer_membership_announcements'] is False


@pytest.mark.parametrize('option', ['peer', 'schema', 'invalid'])
async def test_override_rejects_unowned_or_invalid(backend, store, option):
    if option == 'peer': backend['row']['fulcra_userid'] = PEER
    if option == 'schema': backend['schema'] = {'properties': {}}
    overrides = {'autonomous_replies': True} if option == 'invalid' else {'notifications': 'none'}
    async with Client(mcp) as client:
        result = await client.call_tool('set_contact_preferences', {
            'data_type': OUT, 'peer_userid': PEER, 'overrides': overrides}, raise_on_error=False)
        assert result.is_error
    assert store['overrides'] == {}
