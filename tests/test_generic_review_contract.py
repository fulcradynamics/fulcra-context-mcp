"""Public generic projections used by skill safety decisions (offline)."""
import copy
import json
from datetime import datetime, timedelta
from io import BytesIO
from urllib.parse import urlparse

import pytest
from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials
from fulcra_api.connections import CHANNEL_FIELDS
from fulcra_mcp import tools
from conftest import FAKE_USER_ID

TYPE = 'Event/00000000-0000-4000-8000-000000000010'
PEER = '00000000-0000-4000-8000-000000000002'
MISSING = object()


@pytest.mark.parametrize('selectors,complete', [
    (['file:/a'], True), (['filehistory:/a'], True), ([TYPE], True),
    (['Event'], True), (['*'], True), ([TYPE, 'file:/a'], True),
    ([TYPE, 'filehistory:/a'], True), ([], True),
    (MISSING, False), (None, False), (TYPE, False), ([None], False),
    ([''], False), (['file:'], False), ([' Event '], False),
])
async def test_public_share_selector_completeness(call, fake_fulcra, selectors, complete):
    grant = dict(grant_type='user', sharing_fulcra_userid=PEER,
                 datashare_name='connect-our-agents invitation', share_all_data=False)
    if selectors is not MISSING:
        grant['fulcra_data_types'] = selectors
    fake_fulcra.get_datashares.return_value = [grant]
    fake_fulcra.get_shared_datasets.return_value = [grant]
    value = json.loads((await call('list_shares', {'direction': 'both'})).removeprefix('Shares: '))
    for row in value['incoming'] + value['outgoing']:
        assert row['selectors_complete'] is complete
        assert all(isinstance(row[k], list) for k in ('data_types', 'file_paths', 'file_history_paths'))
    if complete:
        row = value['incoming'][0]
        reconstructed = row['data_types'] + ['file:' + p for p in row['file_paths']] + ['filehistory:' + p for p in row['file_history_paths']]
        assert sorted(reconstructed) == sorted(selectors)


def custom_schema():
    schema = copy.deepcopy(CHANNEL_FIELDS)
    schema['properties'].update({
        'optional_extra': {'type': 'string', 'default': 'retain me', 'maxLength': 30},
        'nullable_extra': {'anyOf': [{'$ref': '#/$defs/extra'}, {'type': 'null'}], 'default': None},
    })
    schema['$defs'] = {'extra': {'type': 'integer', 'minimum': 2}}
    return schema


@pytest.mark.parametrize('raw', [True, False])
async def test_exact_schema_real_sdk_transport_roundtrip(call, monkeypatch, raw):
    schema = custom_schema()
    full = {**schema, 'properties': {**schema['properties'], 'id': {'type': 'string'}, 'start_time': {'type': 'string'}},
            'required': schema['required'] + ['id', 'start_time']}
    entry = dict(id=TYPE, api_version='v1', fulcra_userid=FAKE_USER_ID, recordable=True,
                 name='Template', description='connect-our-agents channel', record_spec={'type': 'event'})
    if raw:
        entry['record_spec']['schema'] = json.dumps(schema)
    api = FulcraAPI(oidc_audience='https://synthetic.invalid')
    api.fulcra_credentials = FulcraCredentials(access_token='synthetic', access_token_expiration=datetime.now() + timedelta(hours=1))
    monkeypatch.setattr(api, 'get_token_claims', lambda: {'fulcradynamics.com/userid': FAKE_USER_ID})
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    posted = []
    def transport(req):
        path = urlparse(req.full_url).path
        if path == '/data/v1/catalog':
            result = [entry]
        elif path.endswith('/schema'):
            result = full
        elif path == '/input/v1/data_type/Event':
            assert req.get_method() == 'POST'
            body = json.loads(req.data)
            posted.append(json.loads(body['record_spec']['schema']))
            result = {**entry, **body}
        else:
            raise AssertionError(path)
        return BytesIO(json.dumps(result).encode())
    monkeypatch.setattr('urllib.request.urlopen', transport)
    text = await call('get_data_catalog', {'data_type': TYPE})
    row = next(iter(json.loads(text.split(': ', 1)[1]).values()))[0]
    assert row['creation_fields_schema'] == schema
    from fulcra_mcp.mentions import _compatible_schema
    from jsonschema import Draft202012Validator
    assert _compatible_schema(row)
    Draft202012Validator.check_schema(row['creation_fields_schema'])
    await call('create_data_type', {'base_type': 'event', 'name': 'Copy', 'description': 'connect-our-agents channel', 'fields': row['creation_fields_schema']})
    assert posted == [schema]


@pytest.mark.parametrize('raw_schema', ['{broken', None, {'properties': {}, 'additionalProperties': False}])
async def test_present_unusable_raw_schema_never_falls_back(call, fake_fulcra, raw_schema):
    fake_fulcra.v1_catalog.return_value = [dict(id=TYPE, api_version='v1', recordable=True,
        fulcra_userid=FAKE_USER_ID, record_spec={'type': 'event', 'schema': raw_schema})]
    fake_fulcra.v1_catalog_schema.return_value = custom_schema()
    text = await call('get_data_catalog', {'data_type': TYPE})
    row = next(iter(json.loads(text.split(': ', 1)[1]).values()))[0]
    assert row['creation_fields_schema'] is None


async def test_raw_custom_schema_survives_full_schema_unavailable(call, fake_fulcra):
    from conftest import http_error
    schema = custom_schema()
    fake_fulcra.v1_catalog.return_value = [dict(id=TYPE, api_version='v1', recordable=True,
        fulcra_userid=FAKE_USER_ID, record_spec={'type': 'event', 'schema': schema})]
    fake_fulcra.v1_catalog_schema.side_effect = http_error(404)
    text = await call('get_data_catalog', {'data_type': TYPE})
    row = next(iter(json.loads(text.split(': ', 1)[1]).values()))[0]
    assert row['creation_fields_schema'] == schema


@pytest.mark.parametrize('schema', [None, {}, {'properties': {}, 'allOf': [{'required': ['id']}]}])
async def test_unavailable_creation_schema_is_explicit(call, fake_fulcra, schema):
    fake_fulcra.v1_catalog.return_value = [dict(id=TYPE, api_version='v1', recordable=True, fulcra_userid=FAKE_USER_ID)]
    fake_fulcra.v1_catalog_schema.return_value = schema
    text = await call('get_data_catalog', {'data_type': TYPE})
    row = next(iter(json.loads(text.split(': ', 1)[1]).values()))[0]
    assert row['creation_fields_schema'] is None
