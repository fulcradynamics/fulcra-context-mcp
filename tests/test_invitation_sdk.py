"""Exercise real SDK serialization and full JSONL parsing with transport mocked."""
import json
from datetime import datetime, timedelta
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import urlparse, parse_qs

import pytest
from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials
from fulcra_api import connections
from fulcra_mcp import agent_invitations as invitations

OWN = '00000000-0000-4000-8000-000000000001'
PEER = '00000000-0000-4000-8000-000000000002'
OUT = 'Event/00000000-0000-4000-8000-000000000010'
IN = 'Event/00000000-0000-4000-8000-000000000020'
STATE = 'Event/00000000-0000-4000-8000-000000000099'


@pytest.mark.parametrize('partial', [False, True])
def test_sdk_invitation_transport_owner_scope_and_partial_reads(monkeypatch, partial):
    api = FulcraAPI(oidc_audience='https://synthetic.invalid')
    api.fulcra_credentials = FulcraCredentials(access_token='synthetic',
        access_token_expiration=datetime.now() + timedelta(hours=1))
    monkeypatch.setattr(api, 'get_token_claims', lambda: {'fulcradynamics.com/userid': OWN})
    catalog = [dict(id=id, fulcra_userid=owner, api_version='v1', recordable=owner == OWN,
        record_spec={'type': 'event'}, description='connect-our-agents channel') for id, owner in [(OUT, OWN), (IN, PEER)]]
    outgoing, rows, calls = [], [], []
    def transport(req):
        url = urlparse(req.full_url); query = parse_qs(url.query)
        path, method = url.path, req.get_method()
        calls.append((method, path, query))
        value = None
        if path == '/data/v1/catalog':
            value = [e for e in catalog if e['fulcra_userid'] == query['fulcra_userid'][0]
                     and ('data_type' not in query or e['id'] == query['data_type'][0])]
        elif path.endswith('/schema'):
            assert query['fulcra_userid'] == ([PEER] if IN in path else [OWN])
            value = {'type': 'object', **connections.CHANNEL_FIELDS}
        elif path == '/user/v1/dataset':
            value = [dict(grant_type='self', sharing_fulcra_userid=OWN),
                dict(grant_type='user', sharing_fulcra_userid=PEER,
                     datashare_name='connect-our-agents invitation', fulcra_data_types=[IN], share_all_data=False)]
        elif path == '/user/v1/datashare':
            if method == 'POST':
                body = json.loads(req.data)
                assert body == dict(datashare_name='connect-our-agents invitation', fulcra_user_name=OWN,
                    time_start=None, time_end=None, fulcra_data_types=[OUT], share_all_data=False,
                    permissions=[{'allowed_fulcra_userid': PEER}])
                outgoing.append(dict(id=PEER, **body)); value = outgoing[-1]
            else:
                value = outgoing
        elif path == '/data/v1/records':
            assert query['fulcra_userid'] == [PEER]
            assert query['q'][0].startswith('{__name__="' + IN + '"}[')
            payload = '\n'.join(json.dumps(r) for r in rows).encode()
            return BytesIO(payload + (b'\n{"id":' if partial else b'\n'))
        elif path.startswith('/input/v1/data_type/Event'):
            if method == 'GET':
                value = catalog[-1]
            else:
                body = json.loads(req.data)
                if method == 'POST':
                    catalog.append(dict(id=STATE, fulcra_userid=OWN, api_version='v1', **body))
                else:
                    assert method == 'PUT' and path.endswith(STATE)
                    catalog[-1].update(body)
                headers = Message(); headers['Location'] = '/input/v1/data_type/' + STATE
                raise HTTPError(req.full_url, 303, 'See Other', headers, None)
        else:
            raise AssertionError((method, path, query))
        return BytesIO(json.dumps(value).encode())
    monkeypatch.setattr('urllib.request.urlopen', transport)
    prepared = invitations.prepare(api, OUT)
    rows.append(dict(id=PEER, kind='message', sender='Agent', body='hello',
                     topic=prepared['topic'], start_time='2026-10-01T00:00:00Z'))
    result = invitations.match(api)
    if partial:
        assert result['status'] == 'unavailable' and outgoing == []
    else:
        assert result['results'][0]['status'] == 'matched'
        assert invitations.match(api)['results'] == []
        assert len(outgoing) == 1
        post = next(i for i, c in enumerate(calls) if c[:2] == ('POST', '/user/v1/datashare'))
        assert any(c[:2] == ('GET', '/user/v1/datashare') for c in calls[post + 1:])
