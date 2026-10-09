"""Real HTTP MCP auth boundary, synthetic backend only (no live accounts)."""
import json
from datetime import datetime, timedelta
from unittest.mock import create_autospec

from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials

from fulcra_mcp import credentials
from fulcra_mcp.main import oauth_provider
from fulcra_mcp.settings import settings
from test_stateless import INITIALIZE, mcp_client


async def test_mesh_identifier_http_auth_and_contract(tmp_path, monkeypatch):
    fake = create_autospec(FulcraAPI, instance=True)
    fake.get_fulcra_userid.return_value = 'own'
    type_id = 'MomentAnnotation/12345678-1234-4234-8234-123456789abc'
    entry = {'id': type_id, 'fulcra_userid': 'own', 'name': 'Mesh Outbox', 'description': 'Prose'}
    fake.resolve_data_type.side_effect = lambda *a, **kw: [dict(entry)]
    def transport(path, *, method, authenticated, data=None):
        assert path == '/user/v1alpha1/annotation/' + type_id.split('/')[1]
        assert authenticated is True
        if method == 'PUT':
            assert isinstance(data, dict)
            entry.update(data)
        return json.dumps({**entry, 'id': type_id.split('/')[1], 'annotation_type': 'moment',
                           'spec': None, 'measurement_spec': None, 'tags': []})
    fake.fulcra_api.side_effect = transport
    creds = FulcraCredentials(access_token='synthetic', access_token_expiration=datetime.now() + timedelta(hours=1))
    monkeypatch.setattr(settings, 'fulcra_environment', 'test')
    monkeypatch.setattr(credentials, 'FulcraAPI', lambda **kwargs: fake)
    monkeypatch.setattr(oauth_provider, 'credentials_for_token', lambda token: ('synthetic', creds) if token == 'mcp_test' else None)
    call = {'name': 'set_mesh_identifier', 'arguments': {'data_type': type_id, 'identifier': 'Travel'}}
    async with mcp_client(tmp_path) as http:
        async def rpc(method, params):
            response = await http.post('/mcp', json={'jsonrpc': '2.0', 'id': 2, 'method': method, 'params': params})
            assert response.status_code == 200
            body = response.text
            return json.loads(next(line[6:] for line in body.splitlines() if line.startswith('data: ')) if body.startswith('event:') else body)
        assert (await http.post('/mcp', json=INITIALIZE)).status_code == 200
        listed = (await rpc('tools/list', {}))['result']['tools']
        tool = next(t for t in listed if t['name'] == 'set_mesh_identifier')
        assert set(tool['inputSchema']['properties']) == {'data_type', 'identifier'}
        assert tool['inputSchema']['required'] == ['data_type', 'identifier']
        assert tool['annotations']['readOnlyHint'] is False
        assert tool['annotations']['idempotentHint'] is True
        for token in ['', 'Bearer invalid-token']:
            response = await http.post('/mcp', headers={'Authorization': token}, json={'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': call})
            assert response.status_code == 401
        assert not fake.mock_calls
        result = (await rpc('tools/call', call))['result']
        assert not result.get('isError')
        assert json.loads(result['content'][0]['text'])['verified'] is True
        assert json.loads((await rpc('tools/call', call))['result']['content'][0]['text'])['changed'] is False
        assert sum(c.kwargs['method'] == 'PUT' for c in fake.fulcra_api.call_args_list) == 1
        # A backend catalog entry owned by someone else is refused even if the
        # backend unexpectedly returns it despite the explicit owner filter.
        entry['fulcra_userid'] = 'other'
        result = (await rpc('tools/call', call))['result']['content'][0]['text']
        assert 'Only the authenticated' in result
        assert sum(c.kwargs['method'] == 'PUT' for c in fake.fulcra_api.call_args_list) == 1
    fake.update_data_type.assert_not_called()
    assert {c[0] for c in fake.mock_calls} == {'get_fulcra_userid', 'resolve_data_type', 'fulcra_api'}
