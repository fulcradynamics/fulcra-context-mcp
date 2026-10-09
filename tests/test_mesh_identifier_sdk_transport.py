"""Real authenticated SDK transport, synthetic HTTP only; no live account."""
from copy import deepcopy
from datetime import datetime, timedelta
from email.message import Message
from io import BytesIO
import json
from urllib.error import HTTPError
from urllib.parse import urlparse, parse_qs

from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials
import pytest

from fulcra_mcp import tools
from fulcra_mcp.mesh_identifier import write_mesh_identifier

TYPE_ID = 'MomentAnnotation/12345678-1234-4234-8234-123456789abc'
PATH = '/user/v1alpha1/annotation/' + TYPE_ID.split('/')[1]
FIELDS = ('name', 'description', 'annotation_type', 'spec', 'measurement_spec', 'tags')


@pytest.fixture
def backend(monkeypatch):
    api = FulcraAPI(oidc_audience='https://synthetic.invalid')
    api.fulcra_credentials = FulcraCredentials(access_token='synthetic', access_token_expiration=datetime.now() + timedelta(hours=1))
    monkeypatch.setattr(api, 'get_token_claims', lambda: {'fulcradynamics.com/userid': 'own'})
    original = {'id': TYPE_ID.split('/')[1], 'fulcra_userid': 'own',
                'name': 'Mesh Outbox — peer', 'description': 'Keep prose\n  exactly.',
                'annotation_type': 'moment', 'spec': {'default_note': 'Keep note'},
                'measurement_spec': None, 'tags': ['aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'],
                'created_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:00:00Z',
                'deleted_at': None, 'fulcra_source_id': 'synthetic'}
    state = {'row': deepcopy(original), 'original': original, 'calls': [], 'persist': True, 'mutation': {}}

    def transport(req):
        path = urlparse(req.full_url).path
        method = req.get_method()
        body = json.loads(req.data) if req.data is not None else None
        assert req.get_header('Authorization') == 'Bearer synthetic'
        state['calls'].append((method, path, body))
        if path == '/data/v1/catalog':
            assert method == 'GET'
            assert parse_qs(urlparse(req.full_url).query) == {'data_type': [TYPE_ID], 'fulcra_userid': ['own']}
            return BytesIO(json.dumps([{**original, 'description': state['row'].get('description'), 'id': TYPE_ID}]).encode())
        assert path == PATH
        if method == 'PUT':
            expected = {key: original[key] for key in FIELDS}
            expected['description'] = write_mesh_identifier(original['description'], 'Travel')
            assert body == expected
            if state['persist']:
                state['row'].update(deepcopy(body))
            state['row'].update(state['mutation'])
            headers = Message()
            headers['Location'] = PATH
            raise HTTPError(req.full_url, 303, 'See Other', headers, None)
        assert method == 'GET' and body is None
        reads = sum(m == 'GET' and p == PATH for m, p, _ in state['calls'])
        if reads == 3:
            state['row'].update(state.get('independent_mutation', {}))
        if reads > 1 and state.get('missing_readback'):
            state['row'].pop(state['missing_readback'], None)
        if 'raw_response' in state:
            return BytesIO(state['raw_response'])
        return BytesIO(json.dumps(state['row']).encode())

    monkeypatch.setattr('urllib.request.urlopen', transport)
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    return state


async def test_real_sdk_preservation_redirect_independent_readback_and_noop(backend):
    result = json.loads(await tools.set_mesh_identifier(TYPE_ID, 'Travel'))
    assert result == {'data_type': TYPE_ID, 'fulcra_userid': 'own', 'identifier': 'Travel', 'changed': True, 'verified': True}
    assert [(m, p) for m, p, _ in backend['calls']] == [
        ('GET', '/data/v1/catalog'), ('GET', PATH), ('PUT', PATH),
        ('GET', PATH), ('GET', PATH), ('GET', '/data/v1/catalog')]
    assert backend['row'] == {**backend['original'], 'description': write_mesh_identifier(backend['original']['description'], 'Travel')}
    backend['calls'].clear()
    assert json.loads(await tools.set_mesh_identifier(TYPE_ID, 'Travel'))['changed'] is False
    assert [(m, p) for m, p, _ in backend['calls']] == [
        ('GET', '/data/v1/catalog'), ('GET', PATH), ('GET', PATH), ('GET', '/data/v1/catalog')]


@pytest.mark.parametrize('field', ['id', 'fulcra_userid', *FIELDS])
async def test_missing_metadata_no_write(backend, field):
    del backend['row'][field]
    result = await tools.set_mesh_identifier(TYPE_ID, 'Travel')
    assert 'verified' not in result
    assert all(m == 'GET' for m, _, _ in backend['calls'])


@pytest.mark.parametrize('change', [
    {'id': 'other'}, {'fulcra_userid': 'other'}, {'annotation_type': 'duration'},
    {'description': None}, {'tags': None}, {'tags': ['not-a-uuid']},
    {'spec': []}, {'measurement_spec': {}}, {'deleted_at': '2026-01-01'},
    {'description': '[mesh_identifier: bad]'},
])
async def test_invalid_raw_metadata_no_write(backend, change):
    backend['row'].update(change)
    result = await tools.set_mesh_identifier(TYPE_ID, 'Travel')
    assert 'verified' not in result
    assert all(m == 'GET' for m, _, _ in backend['calls'])


@pytest.mark.parametrize('change', [
    {'id': 'other'}, {'fulcra_userid': 'other'}, {'annotation_type': 'duration'},
    {'name': 'Mesh Outbox renamed'}, {'tags': []}, {'spec': None},
    {'measurement_spec': {}}, {'description': '[mesh_identifier: "Wrong"]'},
])
async def test_readback_mismatch_never_success(backend, change):
    backend['mutation'] = change
    assert 'Could not verify' in await tools.set_mesh_identifier(TYPE_ID, 'Travel')


async def test_stale_readback(backend):
    backend['persist'] = False
    assert 'Could not verify' in await tools.set_mesh_identifier(TYPE_ID, 'Travel')


@pytest.mark.parametrize('value', [TYPE_ID.upper(), 'MomentAnnotation/' + TYPE_ID.split('/')[1].upper(), TYPE_ID + '/..', TYPE_ID + '?x=1', TYPE_ID + '%2f', TYPE_ID + '\n'])
async def test_noncanonical_id_no_requests(backend, value):
    assert 'exact MomentAnnotation' in await tools.set_mesh_identifier(value, 'Travel')
    assert backend['calls'] == []


async def test_redirect_success_cannot_replace_independent_verification(backend):
    backend['independent_mutation'] = {'spec': None}
    assert 'Could not verify' in await tools.set_mesh_identifier(TYPE_ID, 'Travel')


@pytest.mark.parametrize('field', ['id', 'fulcra_userid', *FIELDS])
async def test_missing_readback_metadata(backend, field):
    backend['missing_readback'] = field
    assert 'Could not verify' in await tools.set_mesh_identifier(TYPE_ID, 'Travel')


@pytest.mark.parametrize('response', [b'null', b'[]', b'not json', b'{}'])
async def test_malformed_resource_no_write(backend, response):
    backend['raw_response'] = response
    assert 'verified' not in await tools.set_mesh_identifier(TYPE_ID, 'Travel')
    assert all(m == 'GET' for m, _, _ in backend['calls'])
