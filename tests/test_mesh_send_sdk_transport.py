"""Real SDK schema/JSONL/query transport with a synthetic authenticated server."""
import json
from datetime import datetime, timedelta
from io import BytesIO
from urllib.parse import parse_qs, urlparse

from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials

from fulcra_mcp import tools
from conftest import FAKE_USER_ID
from test_mesh_send import ARGS, ENV, GRANT, OUTBOX, PEER


async def test_sdk_post_is_note_jsonl_and_independent_scoped_readback(monkeypatch):
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
            result = [dict(id=OUTBOX, name='Mesh Outbox', fulcra_userid=FAKE_USER_ID, recordable=True, api_version='v1alpha1', record_spec={'type': 'event'})]
        elif url.path == '/user/v1/datashare':
            result = [dict(datashare_id=GRANT, share_all_data=False, fulcra_data_types=[OUTBOX], permissions=[dict(allowed_fulcra_userid=PEER)], group_permissions=[])]
        elif url.path.endswith('/schema'):
            result = {'type': 'object', 'required': ['note', 'recorded_at', 'sources'], 'properties': {
                'note': {'type': 'string'}, 'recorded_at': {'type': 'string', 'format': 'date-time'},
                'sources': {'type': 'array', 'items': {'type': 'string'}}}}
        elif url.path == '/ingest/v1/record/MomentAnnotation':
            assert method == 'POST' and query == {'api_version': ['v1alpha1']}
            assert req.get_header('Content-type') == 'application/x-jsonl'
            batch = [json.loads(line) for line in req.data.decode().splitlines()]
            assert len(batch) == 1 and json.loads(batch[0]['note']) == ENV
            assert batch[0]['sources'] == ['com.fulcradynamics.mcp', 'com.fulcradynamics.annotation.' + OUTBOX.split('/')[1]]
            rows.extend(batch)
            result = {'upload_id': 'synthetic'}
        else:
            assert url.path == '/data/v1alpha1/event/' + OUTBOX
            assert method == 'GET'
            assert 'start_time' in query and 'end_time' in query
            assert query.get('fulcra_userid', [FAKE_USER_ID]) == [FAKE_USER_ID]
            result = rows
        return BytesIO(json.dumps(result).encode())
    monkeypatch.setattr('urllib.request.urlopen', transport)
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    result = await tools.mesh_send(**ARGS)
    assert result['status'] == 'posted', result
    assert result['peer_acknowledged'] is False
    assert calls.count(('POST', '/ingest/v1/record/MomentAnnotation')) == 1
    assert calls[-1] == ('GET', '/data/v1alpha1/event/' + OUTBOX)
    assert sum(path == '/user/v1/datashare' for _, path in calls) == 2
