from copy import deepcopy
from datetime import datetime, timezone
from urllib.error import HTTPError

import pytest
from fulcra_mcp import connection

OWN = '00000000-0000-4000-8000-000000000001'
PEER = '00000000-0000-4000-8000-000000000002'
MID = '00000000-0000-4000-8000-000000000003'
OUT = 'Event/00000000-0000-4000-8000-000000000004'
IN = 'Event/00000000-0000-4000-8000-000000000005'
TARGET = '00000000-0000-4000-8000-000000000006'

class API:
    def __init__(self):
        self.rows = []; self.writes = []; self.failure = None
        self.shares = [dict(id=MID, datashare_name='connect-agents-with-anyone: Test',
                            share_all_data=False, fulcra_data_types=[OUT],
                            permissions=[dict(allowed_fulcra_userid=PEER)])]
        self.target = dict(id=TARGET, sender='peer', kind='message', body='hello',
                           start_time=datetime.now(timezone.utc).isoformat(), topic='test')
    def get_fulcra_userid(self): return OWN
    def get_datashares(self): return self.shares
    def get_shared_datasets(self):
        return [dict(grant_type='user', sharing_fulcra_userid=PEER,
                     datashare_name='connect-agents-with-anyone: Test', fulcra_data_types=[IN])]
    def resolve_data_type(self, channel, fulcra_userid):
        return [dict(id=channel, fulcra_userid=fulcra_userid, api_version='v1', recordable=True,
                     description='connect-agents-with-anyone channel', record_spec={'type':'event'})]
    def validate_records(self, *args): return []
    def record_data_type(self, channel, rows, version):
        assert channel == OUT and version == 'v1'
        self.writes.append(deepcopy(rows[0]))
        if self.failure: raise self.failure
        self.rows = deepcopy(rows)
        return {'upload_id':'synthetic'}

@pytest.fixture(params=['connect-agents-with-anyone', 'connect-our-agents'])
def api(monkeypatch, request):
    value = API()
    if request.param == 'connect-our-agents':
        value.shares[0]['datashare_name'] = 'connect-our-agents: Test'
        resolve = value.resolve_data_type
        value.resolve_data_type = lambda *a, **kw: [dict(e, description='connect-our-agents channel') for e in resolve(*a, **kw)]
        incoming = value.get_shared_datasets()
        incoming[0]['datashare_name'] = 'connect-our-agents: Test'
        value.get_shared_datasets = lambda: incoming
    monkeypatch.setattr(connection.records, 'get_records', lambda api, entry, *args, **kw: api.rows if entry['fulcra_userid'] == OWN else [api.target])
    monkeypatch.setattr(connection, 'RETRY_DELAY', 0, raising=False)
    return value

def send(api, **kw):
    return connection.send(api, **(dict(peer_userid=PEER, outbox=OUT, sender='test', body='hello', mid=MID) | kw))

def test_event_exact_readback_and_same_id(api):
    result = send(api)
    assert result['status'] == 'posted'
    assert result['record']['id'] == MID
    assert 'note' not in api.writes[0]
    assert send(api)['status'] == 'posted'
    assert len(api.writes) == 1
    assert send(api, body='changed')['status'] == 'rejected'

@pytest.mark.parametrize('extra', [dict(body='x'*4001), dict(kind='heartbeat'), dict(recipients=[]), dict(mid=MID.upper()+' '), dict(kind='reply')])
def test_invalid_never_writes(api, extra):
    assert send(api, **extra)['status'] == 'rejected'
    assert api.writes == []

def test_reply_and_ack_inherit_topic_and_reject_acks(api):
    assert send(api, kind='reply', in_reply_to=TARGET)['record']['topic'] == 'test'
    api.rows = []; api.target['kind'] = 'ack'
    assert send(api, kind='ack', in_reply_to=TARGET)['status'] == 'rejected'

def test_retries_same_payload_and_never_auth_denial(api):
    api.failure = TimeoutError()
    assert send(api)['status'] == 'uncertain'
    assert len(api.writes) == 2 and api.writes[0] == api.writes[1]
    api.writes = []; api.failure = HTTPError('synthetic', 403, 'denied', {}, None)
    denied = send(api)
    assert denied['status'] == 'rejected' and denied['retryable'] is False
    assert len(api.writes) == 1

def test_successful_upload_is_not_repeated_while_ingestion_is_pending(api, monkeypatch):
    monkeypatch.setattr(connection.records, 'get_records', lambda *args, **kwargs: [])
    result = send(api)
    assert result['status'] == 'uncertain'
    assert result['retryable'] is False
    assert len(api.writes) == 1


def test_broad_grant_does_not_block_connection(api):
    api.shares.append(dict(id=TARGET, share_all_data=True, fulcra_data_types=[], permissions=[]))
    assert send(api)['status'] == 'posted'
    assert len(api.writes) == 1

@pytest.mark.parametrize('change', [dict(grant_type='group'), dict(sharing_fulcra_userid=OWN), dict(fulcra_data_types=[IN, OUT]), dict(time_start='2026-01-01')])
def test_reply_target_requires_exact_direct_peer_grant(api, change):
    grants = api.get_shared_datasets()
    grants[0].update(change)
    api.get_shared_datasets = lambda: grants
    assert send(api, kind='ack', in_reply_to=TARGET)['status'] == 'rejected'
    assert not api.writes

def test_old_reply_target_and_artifact_validation(api):
    api.target['start_time'] = '2000-01-01T00:00:00+00:00'
    assert send(api, kind='reply', in_reply_to=TARGET)['status'] == 'rejected'
    assert send(api, artifacts=[{'unexpected':'field'}])['status'] == 'rejected'
    assert not api.writes

async def test_event_identifier_preserves_conversion_provenance(api, monkeypatch):
    import json
    from fulcra_mcp import tools
    description = 'connect-agents-with-anyone channel\nconverted_from_mesh: []\n[mesh_identifier: "Old"]'
    entry = api.resolve_data_type(OUT, OWN)[0] | {'description':description}
    api.resolve_data_type = lambda *args, **kwargs: [entry.copy()]
    updates = []
    def update(base, identifier, values):
        updates.append((base, identifier, values))
        entry.update(values)
    api.update_data_type = update
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    result = json.loads(await tools.set_contact_identifier(OUT, 'New'))
    assert result['verified'] and result['changed']
    assert len(updates) == 1
    assert entry['description'] == description.replace('"Old"', '"New"')


def _with_status(api, attention):
    from fulcra_mcp.contact_status import write_status
    api.description = write_status('connect-agents-with-anyone channel', dict(
        attention=attention, reason='Waiting on you' if attention else 'Up to date', assessed_at='2026-10-13T12:00:00Z'))
    api.updates = []
    api.resolve_data_type = lambda channel, fulcra_userid: [dict(
        id=channel, fulcra_userid=fulcra_userid, api_version='v1', recordable=True,
        description=api.description, record_spec={'type': 'event'})]
    def update(base, type_id, change):
        api.updates.append((base, type_id, change)); api.description = change['description']
    api.update_data_type = update


@pytest.mark.parametrize('kind', ['message', 'reply'])
@pytest.mark.parametrize('attention', [True, False])
def test_posted_message_or_reply_clears_all_status(api, kind, attention):
    from fulcra_mcp.contact_status import parse_status
    _with_status(api, attention)
    result = send(api, **({'kind': 'reply', 'in_reply_to': TARGET} if kind == 'reply' else {}))
    assert result['status'] == 'posted' and result['status_cleared'] is True
    assert api.updates[0][:2] == ('Event', OUT.split('/')[1])
    status = parse_status(api.description)
    assert status is None
    assert '[contact_status:' not in api.description


def test_status_clears_from_whitespace_folded_description(api):
    import re
    _with_status(api, True)
    api.description = re.sub(r'\s+', ' ', api.description + '\n[mesh_identifier: "Alex"]')
    result = send(api)
    assert result['status_cleared'] is True
    assert api.description == 'connect-agents-with-anyone channel [mesh_identifier: "Alex"]'


def test_ack_leaves_status_alone(api):
    _with_status(api, True)
    result = send(api, kind='ack', body='ack', in_reply_to=TARGET)
    assert result['status'] == 'posted' and 'status_cleared' not in result and api.updates == []


def test_failed_clear_does_not_fail_the_post(api):
    _with_status(api, True)
    def denied(*args): raise HTTPError('u', 403, 'denied', None, None)
    api.update_data_type = denied
    result = send(api)
    assert result['status'] == 'posted' and result['status_cleared'] is False


@pytest.mark.parametrize('failure', [TimeoutError(), HTTPError('u', 403, 'denied', None, None)])
def test_unconfirmed_or_rejected_send_preserves_status(api, failure):
    _with_status(api, True)
    before = api.description
    api.failure = failure
    assert send(api)['status'] in ('uncertain', 'rejected')
    assert api.description == before and api.updates == []


@pytest.mark.parametrize('tool', ['send_agent_contact_message', 'send_agent_message'])
async def test_ui_and_agent_sends_remove_status_without_changing_other_metadata(api, monkeypatch, tool):
    from fulcra_mcp import tools
    _with_status(api, False)
    api.description += '\n[mesh_identifier: "Alex"]'
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    args = dict(sender='test', body='hello')
    if tool == 'send_agent_contact_message':
        args.update(peer_userid=PEER, outbox=OUT, mid=MID)
    else:
        args.update(connection=OUT, record_id=MID)
    result = await getattr(tools, tool)(**args)
    assert result['status'] == 'posted' and result['status_cleared'] is True
    assert api.description == 'connect-agents-with-anyone channel\n[mesh_identifier: "Alex"]'
