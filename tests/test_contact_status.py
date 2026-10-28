import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from email.message import Message
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from urllib.error import HTTPError

import pytest
from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials
from fulcra_api.connections import CHANNEL_FIELDS
from fulcra_mcp import tools
from fulcra_mcp.contact_status import parse_status, write_status
from test_connection_send import OWN, PEER, OUT, MID

STATUS = dict(attention=True, reason='Decision needed', assessed_at='2026-10-13T12:00:00Z')
DESCRIPTION = ('connect-agents-with-anyone channel\nconverted_from_mesh: []\n'
               '[connection_setup_session: "codex://threads/00000000-0000-0000-0000-000000000001"]\n'
               '[mesh_identifier: "Travel"]')


@pytest.mark.parametrize('fixture', json.loads((Path(__file__).parent / 'fixtures/contact-status.json').read_text()), ids=lambda f: f['name'])
def test_shared_parser_fixtures(fixture):
    assert parse_status(fixture['description']) == fixture['expected']


def test_marker_preserves_every_other_byte():
    result = write_status(DESCRIPTION, STATUS)
    assert result.startswith(DESCRIPTION + '\nContact status: ')
    assert parse_status(result) == STATUS
    updated = write_status(result, STATUS | {'attention': False})
    assert parse_status(updated)['attention'] is False
    from fulcra_mcp.contact_status import remove_status
    assert remove_status(updated) == DESCRIPTION + '\n'


@pytest.mark.parametrize('description', [None, '', '[contact_status: bad]', '[contact_status: {}]',
    '[contact_status: {"attention":false}]', '[contact_status: null]'])
def test_unknown_is_not_clear(description):
    assert parse_status(description) is None
    if description and '[contact_status' in description:
        with pytest.raises(ValueError): write_status(description, STATUS)


@pytest.fixture
def backend(monkeypatch):
    api = FulcraAPI(oidc_audience='https://synthetic.invalid')
    api.fulcra_credentials = FulcraCredentials(access_token='synthetic', access_token_expiration=datetime.now() + timedelta(hours=1))
    monkeypatch.setattr(api, 'get_token_claims', lambda: {'fulcradynamics.com/userid': OWN})
    original = dict(id=OUT, fulcra_userid=OWN, api_version='v1', recordable=True,
                    name='Connection', description=DESCRIPTION, record_spec={'type': 'event'})
    state = dict(row=deepcopy(original), original=original, writes=[], calls=[], persist=True, shares=[dict(
        id=MID, datashare_name='connect-agents-with-anyone: Test', share_all_data=False,
        fulcra_data_types=[OUT], permissions=[dict(allowed_fulcra_userid=PEER)])])
    monkeypatch.setattr(api, 'get_datashares', lambda: state['shares'])
    monkeypatch.setattr(api, 'v1_catalog_schema', lambda *a: state.get('schema', CHANNEL_FIELDS))
    def transport(req):
        assert req.get_header('Authorization') == 'Bearer synthetic'
        path = urlparse(req.full_url).path
        state['calls'].append((req.get_method(), path))
        if path == '/data/v1/catalog':
            assert req.get_method() == 'GET'
            assert parse_qs(urlparse(req.full_url).query) == {'data_type':[OUT], 'fulcra_userid':[OWN]}
            return BytesIO(json.dumps([state['row']]).encode())
        assert path == '/input/v1/data_type/' + OUT
        if req.get_method() == 'GET':
            return BytesIO(json.dumps(state['row']).encode())
        assert req.get_method() == 'PUT'
        body = json.loads(req.data)
        assert list(body) == ['description']
        state['writes'].append(body)
        if state.get('denied'): raise HTTPError(req.full_url, 403, 'denied', {}, None)
        if state['persist']: state['row'].update(body)
        state['row'].update(state.get('mutation', {}))
        headers = Message(); headers['Location'] = path
        raise HTTPError(req.full_url, 303, 'See Other', headers, None)
    monkeypatch.setattr('urllib.request.urlopen', transport)
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    return state


async def assess():
    return await tools.set_contact_status(OUT, PEER, True, 'Decision needed')


async def test_real_sdk_unicode_roundtrip(backend):
    reason = 'Awaiting user’s decision — José / 需要确认'
    result = await tools.set_contact_status(OUT, PEER, True, reason)
    assert result['verified'] is True
    assert len(backend['writes']) == 1
    assert result['assessment']['reason'] == reason
    assert parse_status(backend['row']['description']) == result['assessment']
    assert backend['calls'][-1] == ('GET', '/data/v1/catalog')
    from fulcra_mcp.contact_status import remove_status
    assert remove_status(backend['row']['description']) == DESCRIPTION + '\n'


async def test_real_sdk_transport_preservation_and_independent_readback(backend):
    before = datetime.now(timezone.utc).replace(microsecond=0)
    result = await assess()
    assert result['verified'] is True
    assert len(backend['writes']) == 1
    assert backend['calls'] == [('GET','/data/v1/catalog'), ('PUT','/input/v1/data_type/'+OUT),
                                ('GET','/input/v1/data_type/'+OUT), ('GET','/data/v1/catalog')]
    assert {k:v for k,v in backend['row'].items() if k != 'description'} == {k:v for k,v in backend['original'].items() if k != 'description'}
    status = parse_status(backend['row']['description'])
    assert status['attention'] is True
    assert before <= datetime.fromisoformat(status['assessed_at'].replace('Z', '+00:00')) <= datetime.now(timezone.utc)
    assert result['assessment'] == status


@pytest.mark.parametrize('change', [dict(fulcra_userid=PEER), dict(description=None), dict(recordable=False), dict(record_spec={'type':'metric'}), dict(api_version='v1alpha1'), dict(description=DESCRIPTION+'\n[contact_status: bad]')])
async def test_invalid_or_peer_metadata_never_writes(backend, change):
    backend['row'].update(change)
    assert (await assess())['verified'] is False
    assert not backend['writes']


async def test_schema_required_but_broad_access_does_not_block_status(backend):
    backend['schema'] = {'properties': {}}
    assert (await assess())['verified'] is False
    backend.pop('schema')
    backend['shares'].append(dict(share_all_data=True, fulcra_data_types=[], permissions=[]))
    assert (await assess())['verified'] is True
    assert len(backend['writes']) == 1


@pytest.mark.parametrize('option', [dict(persist=False), dict(mutation={'description': None}), dict(denied=True)])
async def test_unverified_or_denied_is_best_effort_no_retry(backend, option):
    backend.update(option)
    assert (await assess())['verified'] is False
    assert len(backend['writes']) == 1


async def test_backend_updated_timestamp_does_not_prevent_verified_status(backend):
    backend['mutation'] = {'updated_at': '2026-10-13T12:00:00Z'}
    assert (await assess())['verified'] is True
