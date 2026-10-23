"""Owned metadata updates traverse the real SDK's v1 serialization."""
import copy
import json
from unittest.mock import Mock

import pytest
from fulcra_api.core import FulcraAPI

from conftest import FAKE_USER_ID

TYPE = 'Event/df10403a-2115-4254-9e49-e48ca0af6f5d'
ENTRY = dict(id=TYPE, fulcra_userid=FAKE_USER_ID, api_version='v1',
             name='Private configuration', description='old', recordable=True,
             record_spec={'type': 'event', 'schema': '{}'}, deprecated=False)


async def test_metadata_uses_real_sdk(call, fake_fulcra, monkeypatch):
    transport = Mock(return_value=Mock(read=lambda: b'{}'))
    monkeypatch.setattr('urllib.request.urlopen', transport)
    sdk = FulcraAPI()
    sdk.fulcra_credentials = Mock(access_token='synthetic-test-token')
    sdk.fulcra_credentials.is_expired.return_value = False
    fake_fulcra.update_data_type.side_effect = sdk.update_data_type
    fake_fulcra.v1_catalog.side_effect = [[copy.deepcopy(ENTRY)], [{**ENTRY, 'description': 'new'}]]
    result = json.loads(await call('update_data_type', {
        'data_type': TYPE, 'description': 'new', 'expected_description': 'old'}))
    assert result['verified'] is True
    transport.assert_called_once()
    request = transport.call_args.args[0]
    assert request.selector == '/input/v1/data_type/' + TYPE
    assert request.method == 'PUT'
    assert json.loads(request.data) == {'description': 'new'}
    assert request.get_header('Content-type') == 'application/json'
    assert fake_fulcra.v1_catalog.call_count == 2


@pytest.mark.parametrize('change', [
    {'fulcra_userid': '00000000-0000-0000-0000-000000000001'},
    {'api_version': 'v1alpha1'}, {'deprecated': True}, {'recordable': False},
])
async def test_metadata_rejects_ineligible_type(call, fake_fulcra, change):
    fake_fulcra.v1_catalog.return_value = [{**ENTRY, **change}]
    result = json.loads(await call('update_data_type', {'data_type': TYPE, 'description': 'new'}))
    assert result['status'] == 'rejected'
    fake_fulcra.update_data_type.assert_not_called()


async def test_metadata_stale_description_does_not_write(call, fake_fulcra):
    fake_fulcra.v1_catalog.return_value = [ENTRY]
    result = json.loads(await call('update_data_type', {
        'data_type': TYPE, 'description': 'new', 'expected_description': 'stale'}))
    assert result['status'] == 'rejected'
    fake_fulcra.update_data_type.assert_not_called()


@pytest.mark.parametrize('after', [ENTRY, {**ENTRY, 'description': 'new', 'name': 'changed'}])
async def test_metadata_unverified_readback_is_uncertain(call, fake_fulcra, after):
    fake_fulcra.v1_catalog.side_effect = [[ENTRY], [after]]
    result = json.loads(await call('update_data_type', {'data_type': TYPE, 'description': 'new'}))
    assert result['status'] == 'uncertain'
    assert result['verified'] is False
    assert fake_fulcra.update_data_type.call_count == 1


@pytest.mark.parametrize('base', ['Event', 'Metric'])
async def test_metadata_name_only_preserves_description(call, fake_fulcra, base):
    entry = {**ENTRY, 'id': TYPE.replace('Event/', base + '/')}
    fake_fulcra.v1_catalog.side_effect = [[entry], [{**entry, 'name': 'Renamed'}]]
    result = json.loads(await call('update_data_type', {'data_type': entry['id'], 'name': 'Renamed'}))
    assert result['verified'] is True
    fake_fulcra.update_data_type.assert_called_once_with(base, TYPE.split('/')[1], {'name': 'Renamed'})


@pytest.mark.parametrize('data_type', ['Event', 'Event/not-a-uuid', TYPE.replace('-', ''), TYPE.replace('Event/', 'MomentAnnotation/')])
async def test_metadata_invalid_or_legacy_id_never_writes(call, fake_fulcra, data_type):
    result = json.loads(await call('update_data_type', {'data_type': data_type, 'name': 'Renamed'}))
    assert result['status'] == 'rejected'
    fake_fulcra.update_data_type.assert_not_called()
    fake_fulcra.fulcra_api.assert_not_called()


async def test_metadata_write_transport_failure_is_uncertain(call, fake_fulcra):
    fake_fulcra.v1_catalog.return_value = [ENTRY]
    fake_fulcra.update_data_type.side_effect = OSError('transport failed')
    result = json.loads(await call('update_data_type', {'data_type': TYPE, 'description': 'new'}))
    assert result['status'] == 'uncertain'
    assert result['verified'] is False
    assert fake_fulcra.update_data_type.call_count == 1



SCHEMA = {'type': 'object', 'properties': {'id': {'type': 'string'}, 'title': {'type': 'string'}},
          'required': ['title']}


def _with_fields(**extra):
    schema = copy.deepcopy(SCHEMA)
    schema['properties'].update(extra)
    return schema


async def test_add_fields_sends_existing_and_new_fields(call, fake_fulcra):
    fake_fulcra.v1_catalog.return_value = [ENTRY]
    fake_fulcra.v1_catalog_schema.side_effect = [SCHEMA, _with_fields(year={'type': 'integer'})]
    result = json.loads(await call('update_data_type', {
        'data_type': TYPE, 'add_fields': {'properties': {'year': {'type': 'integer'}}}}))
    assert result['verified'] is True
    assert result['added_fields'] == ['year']
    assert '5 minutes' in result['note']
    base, type_id, body = fake_fulcra.update_data_type.call_args.args
    assert (base, type_id) == ('Event', TYPE.split('/')[1])
    assert json.loads(body['record_spec']['schema']) == {
        'properties': {'title': {'type': 'string'}, 'year': {'type': 'integer'}}, 'required': ['title']}


@pytest.mark.parametrize('fields, reason', [
    ({'properties': {'title': {'type': 'integer'}}}, 'already has title'),
    ({'properties': {'year': {'type': 'integer'}}, 'required': ['year']}, 'must be optional'),
])
async def test_add_fields_refuses_changes_to_existing_fields(call, fake_fulcra, fields, reason):
    fake_fulcra.v1_catalog.return_value = [ENTRY]
    fake_fulcra.v1_catalog_schema.return_value = SCHEMA
    result = json.loads(await call('update_data_type', {'data_type': TYPE, 'add_fields': fields}))
    assert result['status'] == 'rejected'
    assert reason in result['reason']
    fake_fulcra.update_data_type.assert_not_called()


async def test_add_fields_is_not_combined_with_metadata(call, fake_fulcra):
    result = json.loads(await call('update_data_type', {
        'data_type': TYPE, 'name': 'New', 'add_fields': {'properties': {'y': {'type': 'string'}}}}))
    assert result['status'] == 'rejected'
    fake_fulcra.update_data_type.assert_not_called()


@pytest.mark.parametrize('after', [SCHEMA, _with_fields(year={'type': 'integer'}, title={'type': 'integer'})])
async def test_add_fields_unverified_readback_is_uncertain(call, fake_fulcra, after):
    fake_fulcra.v1_catalog.return_value = [ENTRY]
    fake_fulcra.v1_catalog_schema.side_effect = [SCHEMA, after]
    result = json.loads(await call('update_data_type', {
        'data_type': TYPE, 'add_fields': {'properties': {'year': {'type': 'integer'}}}}))
    assert result['status'] == 'uncertain'
    assert fake_fulcra.update_data_type.call_count == 1
