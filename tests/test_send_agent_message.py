"""Canonical MCP sender and send_agent_contact_message share authorization and readback."""
import json
import pytest
from fulcra_mcp import tools
from test_connection_send import API, OUT, OWN, PEER, MID, TARGET

@pytest.fixture
def connected(monkeypatch):
    api = API()
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    def own_records(api, entry, *args, **kwargs):
        assert entry['fulcra_userid'] == OWN, 'Sending must not retrieve peer records'
        assert entry['id'] == OUT
        return api.rows
    monkeypatch.setattr(tools.records, 'get_records', own_records)
    return api

async def test_sends_on_your_channel_and_reports_verified_id(call, connected):
    result = json.loads(await call('send_agent_message', dict(connection=PEER, sender='a', body='hello', record_id=MID)))
    assert result['status'] == 'posted' and result['mid'] == MID
    assert connected.writes[0]['id'] == MID
    assert connected.writes[0]['body'] == 'hello'

@pytest.mark.parametrize('preexisting', [False, True])
async def test_same_id_with_different_fields_is_posted_once(call, connected, preexisting):
    record = dict(id=MID, sender='a', kind='message', body='hello', topic='chat', priority='P2')
    observed = dict(id=MID, body='different', sender=None, artifacts=[],
                    recipients=['another agent'], in_reply_to=TARGET, topic=None, priority='P1')
    if preexisting:
        connected.rows = [observed]
    else:
        upload = connected.record_data_type
        def upload_with_different_readback(*args):
            result = upload(*args)
            assert connected.writes == [record]
            connected.rows = [observed]
            return result
        connected.record_data_type = upload_with_different_readback
    result = json.loads(await call('send_agent_message', dict(
        connection=OUT, sender='a', body='hello', record_id=MID)))
    assert result['status'] == 'posted', result
    assert result['record'] == observed
    assert len(connected.writes) == (0 if preexisting else 1)


@pytest.mark.parametrize('topic', [None, 'explicit topic'])
async def test_reply_uses_supplied_or_default_topic(call, connected, topic):
    result = json.loads(await call('send_agent_message', dict(connection=OUT, sender='a', body='yes', reply_to=TARGET, topic=topic)))
    assert result['status'] == 'posted'
    assert result['record']['topic'] == (topic or 'chat')

async def test_ack_reference_does_not_depend_on_target_kind(call, connected):
    connected.target['kind'] = 'ack'
    result = json.loads(await call('send_agent_message', dict(connection=PEER, sender='a', body='x', ack=TARGET)))
    assert result['status'] == 'posted'
    assert connected.writes[0]['in_reply_to'] == TARGET
    assert connected.writes[0]['kind'] == 'ack'

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
