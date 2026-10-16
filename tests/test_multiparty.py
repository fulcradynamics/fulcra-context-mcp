from copy import deepcopy

import pytest
from fulcra_mcp import connection
from test_connection_send import api, send, OWN, PEER, OUT, TARGET

OTHER = '00000000-0000-4000-8000-000000000007'


def add_member(api):
    share = deepcopy(api.shares[0])
    share['id'] = TARGET
    share['permissions'] = [{'allowed_fulcra_userid': OTHER}]
    api.shares.append(share)


def test_exact_expected_audience_and_readback(api):
    add_member(api)
    assert send(api)['status'] == 'rejected'
    result = send(api, expected_peer_userids=[PEER, OTHER], recipients=['AgentCase'])
    assert result['status'] == 'posted'
    assert result['record']['recipients'] == ['AgentCase']
    assert len(api.writes) == 1


@pytest.mark.parametrize('audience', [[], [PEER], [PEER, OTHER, OWN], [PEER, PEER], [OTHER]])
def test_audience_mismatch_never_writes(api, audience):
    add_member(api)
    assert send(api, expected_peer_userids=audience)['status'] == 'rejected'
    assert not api.writes


def test_revocation_before_write_stops_send(api):
    add_member(api)
    def validate(*args):
        api.shares.pop()
        return []
    api.validate_records = validate
    assert send(api, expected_peer_userids=[PEER, OTHER])['status'] == 'rejected'
    assert not api.writes


@pytest.mark.parametrize('kind', ['reply', 'ack'])
def test_multiparty_target_is_exact_peer_not_claimed_association(api, kind):
    add_member(api)
    result = send(api, expected_peer_userids=[PEER, OTHER], kind=kind, in_reply_to=TARGET)
    assert result['status'] == 'posted'
    assert result['record']['in_reply_to'] == TARGET
    assert result['record']['topic'] == 'test'


async def test_canonical_send_requires_exact_target_owner(api, monkeypatch):
    from fulcra_mcp import tools
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    add_member(api)
    args = dict(connection=OUT, sender='test', body='hello', record_id=TARGET,
                expected_peer_userids=[PEER, OTHER], reply_to=TARGET)
    assert (await tools.send_agent_message(**args))['status'] == 'rejected'
    assert not api.writes
    assert (await tools.send_agent_message(**args, target_peer_userid=OTHER))['status'] == 'rejected'
    assert not api.writes
    assert (await tools.send_agent_message(**args, target_peer_userid=PEER))['status'] == 'posted'


def test_duplicate_exact_grants_preserve_audience(api):
    api.shares.append(deepcopy(api.shares[0]))
    assert send(api)['status'] == 'posted'


def test_single_multi_user_grant(api):
    api.shares[0]['permissions'].append({'allowed_fulcra_userid': OTHER})
    assert send(api, expected_peer_userids=[PEER, OTHER])['status'] == 'posted'


@pytest.mark.parametrize('change', [dict(share_all_data=True), dict(group_permissions=[OTHER]),
    dict(file_paths=['/']), dict(fulcra_data_types=['Event/*'])])
def test_multiparty_unsafe_covering_grant(api, change):
    add_member(api)
    api.shares[-1].update(change)
    assert send(api, expected_peer_userids=[PEER, OTHER])['status'] == 'rejected'
    assert not api.writes
