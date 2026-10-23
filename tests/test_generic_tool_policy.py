"""Generic data-type and share tools apply no messaging-specific name policy."""
import json

import pytest

from test_data_type_metadata import ENTRY, TYPE

STORE_NAMES = ['Fulcra Agent Invitations', 'Fulcra Contact Preferences']
PEER = '00000000-0000-0000-0000-000000000002'


@pytest.mark.parametrize('name', STORE_NAMES)
@pytest.mark.parametrize('args', [
    {'data_types': [TYPE], 'with_user_ids': [PEER]},
    {'data_types': ['Event'], 'with_group_ids': ['g1']},
    {'share_all_data': True, 'with_user_ids': [PEER]},
])
async def test_create_share_accepts_any_authorized_type(call, fake_fulcra, name, args):
    fake_fulcra.v1_catalog.return_value = [{**ENTRY, 'name': name}]
    fake_fulcra.create_datashare.return_value = {'datashare': {'datashare_id': 'd1'}}
    text = await call('create_share', {'name': 'Mine', **args})
    assert text.startswith('Created share')
    fake_fulcra.create_datashare.assert_called_once()
    fake_fulcra.v1_catalog.assert_not_called()


@pytest.mark.parametrize('name', STORE_NAMES)
async def test_create_data_type_accepts_any_name(call, fake_fulcra, name):
    await call('create_data_type', {'name': name, 'base_type': 'event', 'description': 'notes'})
    fake_fulcra.get_datashares.assert_not_called()


@pytest.mark.parametrize('name', STORE_NAMES)
async def test_update_data_type_has_no_name_policy(call, fake_fulcra, name):
    fake_fulcra.v1_catalog.side_effect = [[{**ENTRY, 'name': name}], [{**ENTRY, 'name': 'Public'}]]
    result = json.loads(await call('update_data_type', {'data_type': TYPE, 'name': 'Public'}))
    assert result['verified'] is True
    fake_fulcra.get_datashares.assert_not_called()


async def test_expected_description_accepts_catalog_display(call, fake_fulcra):
    raw = 'line one\n[contact_status: {}]\n[mesh_identifier: "Trip"]'
    before = {**ENTRY, 'description': raw}
    fake_fulcra.v1_catalog.return_value = [before]
    fake_fulcra.v1_catalog_schema.return_value = {}
    text = await call('get_data_catalog', {'data_type': TYPE})
    shown = next(iter(json.loads(text.split(': ', 1)[1]).values()))[0]['description']
    assert shown != raw
    fake_fulcra.v1_catalog.side_effect = [[before], [{**before, 'description': 'new'}]]
    result = json.loads(await call('update_data_type', {
        'data_type': TYPE, 'description': 'new', 'expected_description': shown}))
    assert result['verified'] is True
    fake_fulcra.v1_catalog.side_effect = [[before]]
    result = json.loads(await call('update_data_type', {
        'data_type': TYPE, 'description': 'new', 'expected_description': 'line one'}))
    assert result['status'] == 'rejected'


@pytest.mark.parametrize('stage', ['identity', 'catalog', 'write', 'readback'])
async def test_metadata_unexpected_errors_do_not_leak_private_content(call, fake_fulcra, stage):
    secret = RuntimeError('private payload and credential URL')
    fake_fulcra.v1_catalog.return_value = [ENTRY]
    if stage == 'identity':
        fake_fulcra.get_fulcra_userid.side_effect = secret
    elif stage == 'catalog':
        fake_fulcra.v1_catalog.side_effect = secret
    elif stage == 'write':
        fake_fulcra.update_data_type.side_effect = secret
    else:
        fake_fulcra.v1_catalog.side_effect = [[ENTRY], secret]
    text = await call('update_data_type', {'data_type': TYPE, 'description': 'new'})
    result = json.loads(text)
    assert result['status'] == ('rejected' if stage in ('identity', 'catalog') else 'uncertain')
    assert 'private payload' not in text
