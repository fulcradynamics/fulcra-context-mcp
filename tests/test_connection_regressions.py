"""Authorization outcomes and semantic discovery against real catalog projection."""
import json
from copy import deepcopy
from urllib.error import HTTPError

import pytest
from fulcra_api.connections import CHANNEL_FIELDS
from fulcra_mcp import connection, mentions, tools
from test_connection_send import API, OWN, PEER, OUT, MID


@pytest.mark.parametrize('stop', ['revoked', 'account', 'denied'])
async def test_timeout_then_authorization_stop_is_emitted_nonretryable(monkeypatch, stop):
    api = API()
    writes = []
    def write(*args):
        writes.append(args)
        if stop == 'revoked':
            api.shares = []
        elif stop == 'account':
            api.get_fulcra_userid = lambda: PEER
        else:
            def denied():
                raise HTTPError('synthetic', 403, 'denied', {}, None)
            api.get_datashares = denied
        raise TimeoutError()
    api.record_data_type = write
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    monkeypatch.setattr(connection, 'RETRY_DELAY', 0)
    monkeypatch.setattr(connection.records, 'get_records', lambda *a, **kw: [])
    result = await tools.agent_connection_send(peer_userid=PEER, outbox=OUT, sender='test', body='hello', mid=MID)
    assert result['status'] == 'uncertain'
    assert len(writes) == 1
    assert result.get('retryable') is False
    assert 'authorization' in result['reason'].lower() or 'denied' in result['reason'].lower()


def projected(schema):
    fields, required = tools._user_defined_fields(schema)
    return {'fields': fields, 'required_fields': required}


def catalog(entry):
    return {'data types usable with: get_records': [entry]}


def shares():
    return dict(own_fulcra_userid=OWN, outgoing=[], incoming=[dict(
        sharing_fulcra_userid=PEER, grant_type='user',
        datashare_name='connect-agents-with-anyone: test', data_types=[OUT])])


@pytest.mark.parametrize('change', ['types', 'required', 'kind', 'body_limit', 'sender_limit', 'recipients', 'valid'])
def test_mentions_semantic_schema(change):
    schema = deepcopy(CHANNEL_FIELDS)
    if change == 'types':
        schema = {'properties': {k: {'type': t} for k, t in zip(('sender','kind','body'), ('number','boolean','object'))}}
    elif change == 'required': schema.pop('required')
    elif change == 'kind': schema['properties']['kind']['enum'] = ['message', 'heartbeat']
    elif change == 'body_limit': schema['properties']['body']['maxLength'] = 9999
    elif change == 'sender_limit': schema['properties']['sender']['minLength'] = 0
    elif change == 'recipients': schema['properties']['recipients']['maxItems'] = 99
    entry = dict(id=OUT, name='Connection', fulcra_userid=PEER,
                 description='connect-agents-with-anyone channel', **projected(schema))
    assert list(mentions._thread_labels(catalog(entry), shares())) == ([PEER] if change == 'valid' else [])


@pytest.mark.parametrize('required', [True, False])
async def test_mentions_exact_schema_keeps_requiredness(monkeypatch, required):
    entry = dict(id=OUT, name='Connection', fulcra_userid=PEER, description='connect-agents-with-anyone channel')
    exact = projected(CHANNEL_FIELDS)
    if not required:
        exact.pop('required_fields')
    async def get_catalog(**kw):
        return 'Available data types, grouped by compatible tool: ' + json.dumps(catalog(
            entry | exact if kw else entry))
    async def get_shares(**kw): return 'Shares: ' + json.dumps(shares())
    monkeypatch.setattr(mentions, 'get_data_catalog', get_catalog)
    monkeypatch.setattr(mentions, 'list_shares', get_shares)
    assert list(await mentions._discover_threads()) == ([PEER] if required else [])


def test_shared_schema_and_fixture_match_real_sdk_catalog_projection():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    fixture = json.loads((root / 'tests/fixtures/connection-schema.json').read_text())
    assert fixture == mentions.CHANNEL_SCHEMA
    assert mentions._semantic(fixture) == mentions._semantic(projected(CHANNEL_FIELDS))


def test_catalog_omitted_names_do_not_break_connection_mentions():
    unrelated = tools._slim_entry({'id': 'StepCount', 'name': 'StepCount', 'api_version': 'v1'})
    entry = dict(id=OUT, fulcra_userid=PEER,
                 description='connect-agents-with-anyone channel', **projected(CHANNEL_FIELDS))
    assert 'name' not in unrelated
    assert list(mentions._thread_labels(
        {'data types usable with: get_records': [unrelated, entry]}, shares())) == [PEER]

