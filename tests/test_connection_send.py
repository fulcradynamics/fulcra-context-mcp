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

@pytest.fixture
def api(monkeypatch):
    value = API()
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


def test_broad_grant_blocks_even_if_not_named_connection(api):
    api.shares.append(dict(id=TARGET, share_all_data=True, fulcra_data_types=[], permissions=[]))
    assert send(api)['status'] == 'rejected'
    assert not api.writes

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
