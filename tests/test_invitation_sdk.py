"""Exercise real SDK serialization and full JSONL parsing with transport mocked."""
import json
from datetime import datetime, timedelta, timezone
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import urlparse, parse_qs

import promql_parser
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


@pytest.mark.parametrize('open_invitation', [False, True])
@pytest.mark.parametrize('partial', [False, True])
@pytest.mark.parametrize('earlier', [False, True])
@pytest.mark.parametrize('hour', [0, 12])
def test_sdk_invitation_transport_owner_scope_and_partial_reads(monkeypatch, partial, earlier, hour, open_invitation):
    query_end = datetime(2026, 10, 16, hour, tzinfo=timezone.utc)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return query_end

    monkeypatch.setattr(invitations, 'datetime', Clock)
    api = FulcraAPI(oidc_audience='https://synthetic.invalid')
    api.fulcra_credentials = FulcraCredentials(access_token='synthetic',
        access_token_expiration=datetime.now() + timedelta(hours=1))
    monkeypatch.setattr(api, 'get_token_claims', lambda: {'fulcradynamics.com/userid': OWN})
    catalog = [dict(id=id, fulcra_userid=owner, api_version='v1', recordable=owner == OWN,
        record_spec={'type': 'event'}, description='connect-our-agents channel') for id, owner in [(OUT, OWN), (IN, PEER)]]
    outgoing, rows, calls = [], [], []
    individual = 'Event/00000000-0000-4000-8000-000000000030'
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
                    time_start=None, time_end=None, fulcra_data_types=[individual if open_invitation else OUT], share_all_data=False,
                    permissions=[{'allowed_fulcra_userid': PEER}])
                outgoing.append(dict(id=PEER, **body)); value = outgoing[-1]
            else:
                value = outgoing
        elif path == '/data/v1/records':
            assert query['fulcra_userid'] == [PEER]
            assert query['q'][0].startswith('{__name__="' + IN + '"}[')
            # Exercise the data service's real parser, not just URL encoding.
            try:
                parsed = promql_parser.parse(query['q'][0])
            except ValueError:
                raise HTTPError(req.full_url, 422, 'Invalid query', Message(), None)
            end = parsed.vector_selector.at.at
            assert end - parsed.range == datetime(1, 1, 1, tzinfo=timezone.utc)
            assert end == query_end
            payload = '\n'.join(json.dumps(r) for r in rows).encode()
            return BytesIO(payload + (b'\n{"id":' if partial else b'\n'))
        elif path.startswith('/input/v1/data_type/Event'):
            if method == 'GET':
                value = next(e for e in catalog if path.endswith(e['id']))
            else:
                body = json.loads(req.data)
                if method == 'POST':
                    id = STATE if body['name'] == invitations.NAME else individual
                    if id == individual:
                        assert open_invitation
                        schema = json.loads(body['record_spec']['schema'])
                        assert schema['properties'] == connections.CHANNEL_FIELDS['properties']
                        assert set(schema['required']) == set(connections.CHANNEL_FIELDS['required'])
                        body['record_spec']['type'] = 'event'
                    catalog.append(dict(id=id, fulcra_userid=OWN, api_version='v1', recordable=True, **body))
                else:
                    assert method == 'PUT' and path.endswith(STATE)
                    id = STATE
                    next(e for e in catalog if e['id'] == STATE).update(body)
                headers = Message(); headers['Location'] = '/input/v1/data_type/' + id
                raise HTTPError(req.full_url, 303, 'See Other', headers, None)
        else:
            raise AssertionError((method, path, query))
        return BytesIO(json.dumps(value).encode())
    monkeypatch.setattr('urllib.request.urlopen', transport)
    prepared = invitations.prepare(api, OUT, open_invitation=open_invitation)
    rows.append(dict(id=PEER, kind='message', sender='Agent', body='hello',
                     topic=prepared['topic'], start_time='2026-10-01T02:00:00.123456+02:00',
                     end_time='2026-10-01T02:00:00.123456+02:00'))
    if earlier:
        # Appended out of order, before Unix epoch/pandas' nanosecond range.
        rows.append(dict(rows[0], id=OWN, start_time='0001-01-02T00:00:00Z', topic='hello'))
    result = invitations.match(api)
    if partial:
        assert result['status'] == 'unavailable' and outgoing == []
        assert result['diagnostic'] == {'stage': 'handshake_history', 'category': 'validation'}
    elif earlier:
        if open_invitation:
            assert result['results'] == []
        else:
            assert result['results'][0]['reason'] == 'No unique first-message handshake.'
        assert outgoing == []
    else:
        assert result['results'][0]['status'] == 'matched'
        assert invitations.match(api)['results'] == []
        assert len(outgoing) == 1
        post = next(i for i, c in enumerate(calls) if c[:2] == ('POST', '/user/v1/datashare'))
        assert any(c[:2] == ('GET', '/user/v1/datashare') for c in calls[post + 1:])
