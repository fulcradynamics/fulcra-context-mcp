"""Real SDK schema/JSONL/query transport with a synthetic authenticated server."""
import json
from datetime import datetime, timedelta
from io import BytesIO
from urllib.parse import parse_qs, urlparse

import pytest
from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials

from fulcra_mcp import tools
from conftest import FAKE_USER_ID
from test_direct_connection_send import ARGS, ENV, GRANT, OUTBOX, PEER


@pytest.mark.parametrize('null_readback', [False, True])
async def test_sdk_post_is_event_jsonl_and_independent_scoped_readback(monkeypatch, null_readback):
    api = FulcraAPI(oidc_audience='https://synthetic.invalid')
    api.fulcra_credentials = FulcraCredentials(access_token='synthetic', access_token_expiration=datetime.now() + timedelta(hours=1))
    monkeypatch.setattr(api, 'get_token_claims', lambda: {'fulcradynamics.com/userid': FAKE_USER_ID})
    rows, calls = [], []
    def transport(req):
        url = urlparse(req.full_url)
        query = parse_qs(url.query)
        method = req.get_method()
        assert req.get_header('Authorization') == 'Bearer synthetic'
        calls.append((method, url.path))
        if url.path == '/data/v1/catalog':
            assert query == {'data_type': [OUTBOX], 'fulcra_userid': [FAKE_USER_ID]}
            result = [dict(id=OUTBOX, name='Connection', description='connect-agents-with-anyone channel', fulcra_userid=FAKE_USER_ID, recordable=True, api_version='v1', record_spec={'type': 'event'})]
        elif url.path == '/user/v1/datashare':
            result = [dict(datashare_id=GRANT, datashare_name='connect-agents-with-anyone: test', share_all_data=False, fulcra_data_types=[OUTBOX], permissions=[dict(allowed_fulcra_userid=PEER)], group_permissions=[])]
        elif url.path.endswith('/schema'):
            from fulcra_api.connections import CHANNEL_FIELDS
            result = {'type': 'object', **CHANNEL_FIELDS, 'properties': {'id': {'type':'string'}, **CHANNEL_FIELDS['properties']}}
        elif url.path == '/ingest/v1/record/' + OUTBOX:
            assert method == 'POST' and query == {'api_version': ['v1']}
            assert req.get_header('Content-type') == 'application/x-jsonl'
            batch = [json.loads(line) for line in req.data.decode().splitlines()]
            assert batch == [ENV]
            rows.extend(batch)
            result = {'upload_id': 'synthetic'}
        else:
            assert url.path == '/data/v1/records'
            assert method == 'GET'
            assert OUTBOX in query['q'][0]
            assert query.get('fulcra_userid', [FAKE_USER_ID]) == [FAKE_USER_ID]
            observed = [dict(artifacts=None, in_reply_to=None, recipients=None, **r)
                        for r in rows] if null_readback else rows
            return BytesIO(('\n'.join(json.dumps(r) for r in observed)).encode())
        return BytesIO(json.dumps(result).encode())
    monkeypatch.setattr('urllib.request.urlopen', transport)
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    result = await tools.send_agent_contact_message(**ARGS)
    assert result['status'] == 'posted', result
    assert result['peer_acknowledged'] is False
    assert calls.count(('POST', '/ingest/v1/record/' + OUTBOX)) == 1
    # Confirm the record first, then fetch current metadata for best-effort clearing.
    assert calls[-2:] == [('GET', '/data/v1/records'), ('GET', '/data/v1/catalog')]
    assert sum(path == '/user/v1/datashare' for _, path in calls) == 2
