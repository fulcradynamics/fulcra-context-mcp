"""Generic metadata operations preserve private-store policy and sanitize errors."""
import json

import pytest

from test_data_type_metadata import ENTRY, TYPE


@pytest.mark.parametrize('private_name', ['Fulcra Agent Invitations', 'Fulcra Contact Preferences'])
@pytest.mark.parametrize('selector', [TYPE, 'Event', 'Event/*', '*', None])
async def test_private_metadata_refuses_covering_grants(call, fake_fulcra, private_name, selector):
    fake_fulcra.v1_catalog.return_value = [{**ENTRY, 'name': private_name}]
    fake_fulcra.get_datashares.return_value = [
        {'share_all_data': selector is None, 'fulcra_data_types': [selector] if selector else []}]
    result = json.loads(await call('update_data_type_metadata', {'data_type': TYPE, 'description': 'secret'}))
    assert result['status'] == 'rejected'
    fake_fulcra.update_data_type.assert_not_called()


async def test_private_metadata_cannot_be_renamed_to_evade_sharing_guard(call, fake_fulcra):
    fake_fulcra.v1_catalog.side_effect = [[{**ENTRY, 'name': 'Fulcra Agent Invitations'}],
                                        [{**ENTRY, 'name': 'Public'}]]
    fake_fulcra.get_datashares.return_value = []
    result = json.loads(await call('update_data_type_metadata', {'data_type': TYPE, 'name': 'Public'}))
    assert result['status'] == 'rejected'
    fake_fulcra.update_data_type.assert_not_called()


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
    text = await call('update_data_type_metadata', {'data_type': TYPE, 'description': 'new'})
    result = json.loads(text)
    assert result['status'] == ('rejected' if stage in ('identity', 'catalog') else 'uncertain')
    assert 'private payload' not in text


@pytest.mark.parametrize('private_name', ['Fulcra Agent Invitations', 'Fulcra Contact Preferences'])
async def test_private_creation_checks_existing_wildcard_grants(call, fake_fulcra, private_name):
    fake_fulcra.create_data_type.return_value = ENTRY
    fake_fulcra.get_datashares.return_value = [{'share_all_data': False, 'fulcra_data_types': ['Event/*']}]
    result = await call('create_data_type', {'name': private_name, 'base_type': 'event', 'description': 'secret'})
    assert 'private' in result.lower()
    fake_fulcra.create_data_type.assert_not_called()


async def test_private_metadata_update_interoperates_and_rechecks_privacy(call, fake_fulcra):
    from fulcra_mcp.contact_preferences import _parse
    before = {**ENTRY, 'name': 'Fulcra Contact Preferences',
              'description': '{"version":1,"global_preferences":{},"overrides":{}}'}
    description = '{"version":1,"global_preferences":{"notifications":"none"},"overrides":{}}'
    after = {**before, 'description': description}
    fake_fulcra.v1_catalog.side_effect = [[before], [after]]
    fake_fulcra.get_datashares.return_value = []
    result = json.loads(await call('update_data_type_metadata', {
        'data_type': TYPE, 'description': description, 'expected_description': before['description']}))
    assert result['verified'] is True
    assert _parse(after)['global_preferences'] == {'notifications': 'none'}
    assert fake_fulcra.get_datashares.call_count == 2


async def test_private_metadata_new_grant_during_write_is_uncertain(call, fake_fulcra):
    before = {**ENTRY, 'name': 'Fulcra Agent Invitations'}
    fake_fulcra.v1_catalog.side_effect = [[before], [{**before, 'description': 'new'}]]
    fake_fulcra.get_datashares.side_effect = [[], [{'share_all_data': True, 'fulcra_data_types': []}]]
    result = json.loads(await call('update_data_type_metadata', {'data_type': TYPE, 'description': 'new'}))
    assert result['status'] == 'uncertain'
    assert fake_fulcra.update_data_type.call_count == 1


@pytest.mark.parametrize('grants', [None, [{}], [{'share_all_data': False}],
                                    [{'share_all_data': False, 'fulcra_data_types': None}]])
async def test_private_metadata_incomplete_grants_fail_closed(call, fake_fulcra, grants):
    before = {**ENTRY, 'name': 'Fulcra Agent Invitations'}
    fake_fulcra.v1_catalog.side_effect = [[before], [{**before, 'description': 'new'}]]
    fake_fulcra.get_datashares.return_value = grants
    result = json.loads(await call('update_data_type_metadata', {'data_type': TYPE, 'description': 'new'}))
    assert result['status'] == 'rejected'
    fake_fulcra.update_data_type.assert_not_called()


async def test_renaming_shared_type_into_private_storage_is_rejected(call, fake_fulcra):
    fake_fulcra.v1_catalog.return_value = [ENTRY]
    fake_fulcra.get_datashares.return_value = [{'share_all_data': False, 'fulcra_data_types': [TYPE]}]
    result = json.loads(await call('update_data_type_metadata', {
        'data_type': TYPE, 'name': 'Fulcra Agent Invitations', 'description': 'secret'}))
    assert result['status'] == 'rejected'
    fake_fulcra.update_data_type.assert_not_called()
