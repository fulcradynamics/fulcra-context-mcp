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
def test_broad_access_policy_does_not_change_contact_audience(change):
    backend = EndAPI()
    broad = dict(deepcopy(backend.shares[0]), share_all_data=True, **change)
    backend.shares.append(broad)
    connection._authorize(backend, OWN, PEER, SEND_OUT)
    assert backend.deleted == [] and backend.updates == []


@pytest.mark.parametrize('change', [
    {'share_all_data': True}, {'fulcra_data_types': ['Event']},
    {'fulcra_data_types': ['Event/*']}, {'fulcra_data_types': ['*']},
])
def test_end_contact_never_deletes_overlapping_broad_share(change):
    backend = EndAPI()
    narrow_id = backend.shares[0]['id']
    broad = dict(deepcopy(backend.shares[0]), **change)
    broad['id'] = '00000000-0000-4000-8000-0000000000ff'
    backend.shares.append(broad)
    result = end(backend, archive=True)
    assert result['status'] == 'ended' and result['archived']
    assert result['broader_access_remains'] is True
    assert backend.deleted == [narrow_id] and backend.shares == [broad]


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


@pytest.mark.parametrize('open_invitation', [False, True])
def test_prepare_and_match_with_existing_share_all(api, open_invitation):
    from test_open_invitations import clone_api, respond
    clone_api(api)
    api.get_datashares.return_value = [dict(id=OTHER, share_all_data=True,
        permissions=[{'allowed_fulcra_userid': OTHER}])]
    code = invitations.prepare(api, OUT, open_invitation=open_invitation)['code']
    (respond if open_invitation else handshake)(api, code)
    result = invitations.match(api)['results'][0]
    assert result['status'] == 'matched'
    assert api.create_datashare.call_count == 1
    created = api.create_datashare.call_args.kwargs
    assert created['share_all_data'] is False
    assert created['allowed_user_ids'] == [PEER]
    assert created['fulcra_data_types'] == [result['data_type']]
    assert not open_invitation or result['data_type'] != OUT
    api.delete_datashare.assert_not_called()


def test_standing_and_named_invitation_creation_with_share_all(api):
    from test_open_invitations import clone_api
    clone_api(api)
    broad = dict(id=OTHER, share_all_data=True, permissions=[{'allowed_fulcra_userid': OTHER}])
    api.get_datashares.return_value = [broad]
    standing = invitations.standing(api, 'Alex')
    assert standing['status'] == 'prepared' and standing['inviter_name'] == 'Alex'
    api.create_datashare.assert_not_called()
    created = invitations.create(api, 'Alex', 'Sam', PEER)
    assert created['shared_with'] == PEER
    assert created['data_type'] != standing['data_type']
    assert api.create_datashare.call_count == 1
    assert api.create_datashare.call_args.kwargs['share_all_data'] is False
    assert broad in api.get_datashares.return_value
    api.delete_datashare.assert_not_called()


def test_end_contact_must_verify_narrow_removal_despite_broad_access():
    backend = EndAPI()
    backend.shares.append(dict(id=OTHER, share_all_data=True))
    backend.delete_datashare = lambda share_id: None
    result = end(backend, archive=True)
    assert not result['ended'] and result['status'] == 'rejected'
    assert backend.updates == []
