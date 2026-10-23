"""Broader grants may overlap, but never establish or enlarge a contact."""
from copy import deepcopy

import pytest

from fulcra_mcp import agent_invitations as invitations, connection
from test_agent_invitations import api, handshake, incoming, OWN, PEER, OTHER, OUT
from test_end_contact import EndAPI, end
from test_connection_send import OUT as SEND_OUT


def test_broad_grant_needs_narrow_authority_for_every_expected_recipient():
    backend = EndAPI()
    narrow = deepcopy(backend.shares[0])
    broad = dict(deepcopy(narrow), share_all_data=True)
    backend.shares = [broad]
    with pytest.raises(ValueError):
        connection._authorize(backend, OWN, PEER, SEND_OUT)
    backend.shares = [narrow, broad]
    narrow['permissions'].append({'allowed_fulcra_userid': OTHER})
    connection._authorize(backend, OWN, PEER, SEND_OUT, [PEER, OTHER])
    with pytest.raises(ValueError):
        connection._authorize(backend, OWN, PEER, SEND_OUT)
    narrow['permissions'].pop()
    broad['permissions'].append({'allowed_fulcra_userid': OTHER})
    with pytest.raises(ValueError):
        connection._authorize(backend, OWN, PEER, SEND_OUT, [PEER, OTHER])


@pytest.mark.parametrize('change', [
    {'permissions': [{'allowed_fulcra_userid': OTHER}]},
    {'permissions': [{'allowed_fulcra_userid': PEER}, {'allowed_fulcra_userid': OTHER}]},
    {'permissions': []}, {'permissions': [{'allowed_fulcra_userid': OWN}]},
    {'group_permissions': [{'allowed_group_id': OTHER}]}, {'group_id': OTHER},
    {'time_start': '2026-01-01T00:00:00Z'}, {'time_end': '2027-01-01T00:00:00Z'},
    {'file_paths': ['/private/']},
    {'fulcra_data_types': [SEND_OUT, 'file:/private/']},
    {'fulcra_data_types': [SEND_OUT, 'filehistory:/private/']},
])
def test_unsafe_broad_overlap_is_rejected(change):
    backend = EndAPI()
    broad = dict(deepcopy(backend.shares[0]), share_all_data=True, **change)
    backend.shares.append(broad)
    with pytest.raises(ValueError):
        connection._authorize(backend, OWN, PEER, SEND_OUT)
    assert backend.deleted == [] and backend.updates == []


@pytest.mark.parametrize('change', [
    {'share_all_data': True}, {'fulcra_data_types': ['Event']},
    {'fulcra_data_types': ['Event/*']}, {'fulcra_data_types': ['*']},
])
def test_end_contact_never_deletes_overlapping_broad_share(change):
    backend = EndAPI()
    backend.shares.append(dict(deepcopy(backend.shares[0]), **change))
    assert end(backend, archive=True)['status'] == 'rejected'
    assert backend.deleted == [] and backend.updates == []


def test_incoming_share_all_overlap_does_not_prevent_matching(api):
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    api.get_shared_datasets.return_value.append(dict(incoming(), share_all_data=True,
        fulcra_data_types=[], datashare_name='Personal sharing'))
    assert invitations.match(api)['results'][0]['status'] == 'matched'
    assert api.create_datashare.call_count == 1
    assert api.create_datashare.call_args.kwargs['share_all_data'] is False


def test_existing_mixed_selector_overlap_matches_without_creating_shares(api):
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    narrow = dict(id=OTHER, share_all_data=False, fulcra_data_types=[OUT],
        datashare_name='connect-our-agents invitation', permissions=[{'allowed_fulcra_userid': PEER}])
    api.get_datashares.return_value = [narrow, dict(narrow,
        fulcra_data_types=[OUT, 'StepCount'], datashare_name='Personal sharing')]
    assert invitations.match(api)['results'][0]['status'] == 'matched'
    api.create_datashare.assert_not_called()
    api.delete_datashare.assert_not_called()


def test_share_all_still_prevents_using_exposed_invitation_storage(api):
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    api.get_datashares.return_value = [dict(id=OTHER, share_all_data=True,
        permissions=[{'allowed_fulcra_userid': PEER}])]
    assert invitations.match(api)['status'] == 'unavailable'
    api.create_datashare.assert_not_called()
    api.delete_datashare.assert_not_called()
    api.update_data_type.assert_not_called()
