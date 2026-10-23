"""Canonical MCP sender and send_agent_contact_message share authorization and readback."""
import json
import pytest
from fulcra_mcp import tools
from test_connection_send import API, OUT, OWN, PEER, MID, TARGET

@pytest.fixture
def connected(monkeypatch):
    api = API()
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    monkeypatch.setattr(tools.records, 'get_records', lambda api, entry, *a, **kw: api.rows if entry['fulcra_userid'] == OWN else [api.target])
    return api

async def test_sends_on_your_channel_and_reports_verified_id(call, connected):
    result = json.loads(await call('send_agent_message', dict(connection=PEER, sender='a', body='hello', record_id=MID)))
    assert result['status'] == 'posted' and result['mid'] == MID
    assert connected.writes[0]['id'] == MID
    assert connected.writes[0]['body'] == 'hello'

async def test_reply_reuses_topic(call, connected):
    result = json.loads(await call('send_agent_message', dict(connection=OUT, sender='a', body='yes', reply_to=TARGET)))
    assert result['status'] == 'posted'
    assert result['record']['topic'] == 'test'

async def test_refusal_explained_without_write(call, connected):
    connected.target['kind'] = 'ack'
    result = json.loads(await call('send_agent_message', dict(connection=PEER, sender='a', body='x', ack=TARGET)))
    assert result['status'] == 'rejected' and 'never an ack' in result['reason']
    assert not connected.writes

async def test_bad_priority_refused_by_schema(client, connected):
    result = await client.call_tool('send_agent_message', dict(connection=PEER, sender='a', body='x', priority='urgent'), raise_on_error=False)
    assert result.is_error and not connected.writes

async def test_http_denial_is_nonretryable_tool_response(call, connected):
    from urllib.error import HTTPError
    connected.failure = HTTPError('synthetic', 403, 'denied', {}, None)
    result = json.loads(await call('send_agent_message', dict(connection=OUT, sender='a', body='x', record_id=MID)))
    assert result['status'] == 'rejected' and result['retryable'] is False
    assert len(connected.writes) == 1

async def test_rejects_group_and_malformed_connection(call, connected):
    connected.shares[0]['permissions'].append({'allowed_fulcra_userid':MID})
    for connection in (PEER, ' '+PEER):
        result = json.loads(await call('send_agent_message', dict(connection=connection, sender='a', body='x', record_id=MID)))
        assert result['status'] == 'rejected' and not connected.writes

async def test_latest_has_no_required_range_and_uses_sdk(call, fake_fulcra, monkeypatch):
    fake_fulcra.resolve_data_type.return_value = [{'id':OUT,'fulcra_userid':OWN,'api_version':'v1','record_spec':{'type':'event'}}]
    fake_fulcra.get_fulcra_userid.return_value = OWN
    fake_fulcra.fulcra_v1_records.return_value = json.dumps({'id':MID,'body':'hello'})
    text = await call('get_records', {'data_type':OUT,'latest':True})
    assert MID in text
    assert fake_fulcra.fulcra_v1_records.call_args.args == ('{__name__="'+OUT+'"}',)
