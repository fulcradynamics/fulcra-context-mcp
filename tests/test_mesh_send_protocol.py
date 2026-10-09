"""Exercise the same HTTP/OAuth server as production, with synthetic clients."""
import json
from datetime import datetime, timedelta
from unittest.mock import create_autospec

from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials

from fulcra_mcp import credentials, tools
from fulcra_mcp.main import oauth_provider
from fulcra_mcp.settings import settings
from test_stateless import INITIALIZE, mcp_client
from test_mesh_send import ARGS, ENV, GRANT, OUTBOX, PEER


async def test_send_http_auth_and_per_user_isolation(tmp_path, monkeypatch):
    owners = ['00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000011']
    clients = {}
    saved = {}
    for owner in owners:
        fake = create_autospec(FulcraAPI, instance=True)
        fake.get_fulcra_userid.return_value = owner
        fake.resolve_data_type.return_value = [dict(id=OUTBOX, fulcra_userid=owners[0], name='Mesh Outbox', recordable=True, api_version='v1alpha1')]
        fake.get_datashares.return_value = [dict(id=GRANT, share_all_data=False, fulcra_data_types=[OUTBOX], permissions=[dict(allowed_fulcra_userid=PEER)])]
        fake.validate_records.return_value = []
        saved[owner] = []
        def record(target, rows, version, owner=owner):
            saved[owner].extend(rows)
            return {'upload_id': 'synthetic'}
        fake.record_data_type.side_effect = record
        clients[owner] = fake
    monkeypatch.setattr(tools.records, 'get_records', lambda api, *args: list(saved[api.get_fulcra_userid()]))
    creds = {owner: FulcraCredentials(access_token=owner, access_token_expiration=datetime.now() + timedelta(hours=1)) for owner in owners}
    monkeypatch.setattr(settings, 'fulcra_environment', 'test')
    monkeypatch.setattr(credentials, 'FulcraAPI', lambda **kwargs: clients[kwargs['credentials'].access_token])
    monkeypatch.setattr(oauth_provider, 'credentials_for_token', lambda token: (token, creds[token]) if token in creds else None)
    import time
    from mcp.server.auth.provider import AccessToken
    from fulcra_mcp.provider import OIDC_SCOPES
    for owner in owners:
        monkeypatch.setitem(oauth_provider.tokens, owner, AccessToken(token=owner, client_id='synthetic', scopes=OIDC_SCOPES, expires_at=int(time.time()) + 3600))
    async with mcp_client(tmp_path) as http:
        async def rpc(token):
            response = await http.post('/mcp', headers={'Authorization': 'Bearer ' + token}, json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'mesh_send', 'arguments': ARGS}})
            if response.status_code != 200: return response.status_code
            text = response.text
            data = json.loads(next(line[6:] for line in text.splitlines() if line.startswith('data: ')) if text.startswith('event:') else text)
            return data['result']
        for token in ['', 'invalid']:
            assert await rpc(token) == 401
        assert all(not fake.mock_calls for fake in clients.values())
        result = await rpc(owners[0])
        assert result['structuredContent']['status'] == 'posted'
        assert json.loads(saved[owners[0]][0]['note']) == ENV
        result = await rpc(owners[1])
        assert result['structuredContent']['status'] == 'rejected'
        clients[owners[1]].record_data_type.assert_not_called()
        assert len(saved[owners[0]]) == 1 and saved[owners[1]] == []
