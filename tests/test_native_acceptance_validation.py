"""Public native acceptance validates before sharing or reserving reuse."""
import copy

import pytest
from fastmcp import Client
from fulcra_api import connections
from fulcra_mcp.channel_metadata import parse_metadata
from fulcra_mcp.main import mcp, openai_mcp
from test_native_lifecycle import accounts, call, OWN, PEER


async def test_target_schema_before_reservation(accounts, monkeypatch):
    a, b, active = accounts
    schema = copy.deepcopy(connections.CHANNEL_FIELDS)
    schema['allOf'] = [{'properties': {'body': {'maxLength': 5}, 'priority': {'const': 'P2'}},
                        'required': ['priority']}]
    channel = a.create_data_type('Event', dict(name='Response', description='Agent contact channel',
        record_spec={'schema': schema}))['id']
    a.writes.clear()
    validated = []
    validate = a.validate_records
    def capture(channel, rows, version):
        validated.extend(copy.deepcopy(rows))
        return validate(channel, rows, version)
    monkeypatch.setattr(a, 'validate_records', capture)
    args = dict(inviter_userid=PEER, topic='handshake ' + 'a'*32, sender='Agent', response_channel=channel)
    async with Client(mcp) as client:
        rejected = await call(client, 'accept_agent_invitation', introduction='Approved hello', **args)
        assert rejected['status'] == 'rejected'
        assert not a.writes and not a.shares and not a.rows
        assert not parse_metadata(a.catalog[0]['description']).get('acceptance')
        assert not b.get_shared_datasets()
        accepted = await call(client, 'accept_agent_invitation', introduction='Hello', **args)
    assert accepted['status'] == 'introduction_posted'
    assert len(validated) == 3  # rejected preflight, valid preflight, final send validation
    assert validated[-2] == validated[-1]
    assert validated[-1]['priority'] == 'P2'
    assert {k: v for k, v in a.rows[channel][0].items() if k != 'start_time'} == validated[-1]


@pytest.mark.parametrize('failure', ['errors', 'exception'])
async def test_created_validation_failure_does_not_share(accounts, monkeypatch, failure):
    a, b, active = accounts
    def reject(*args):
        if failure == 'exception':
            raise TimeoutError('schema unavailable')
        return ['backend schema rejected record']
    monkeypatch.setattr(a, 'validate_records', reject)
    args = dict(inviter_userid=PEER, topic='handshake ' + 'a'*32, sender='Agent', introduction='Hello')
    async with Client(mcp) as client:
        result = await call(client, 'accept_agent_invitation', **args)
        assert result['status'] == 'uncertain'
        assert result['data_type'] == a.catalog[0]['id']
        assert result['retryable'] is False
        assert [w[0] for w in a.writes] == ['create']
        assert not a.shares and not a.rows and not b.get_shared_datasets()
        before = copy.deepcopy(a.writes)
        assert (await call(client, 'accept_agent_invitation', **args))['status'] == 'recovery_required'
        assert a.writes == before


async def test_openai_standing_native_acceptance_openai_match(accounts):
    a, b, active = accounts
    async with Client(openai_mcp) as client:
        invite = await call(client, 'prepare_standing_agent_invitation', inviter_name='Alex')
    active.set(b)
    async with Client(mcp) as client:
        accepted = await call(client, 'accept_agent_invitation', inviter_userid=OWN,
            topic=invite['topic'], sender='Sura agent', introduction='Approved introduction')
        assert accepted['status'] == 'introduction_posted'
    active.set(a)
    async with Client(openai_mcp) as client:
        matched = await call(client, 'match_agent_invitations')
        assert matched['results'][0]['status'] == 'matched'
        assert matched['results'][0]['peer_userid'] == PEER
        assert all(invite['data_type'] not in s['fulcra_data_types'] for s in a.shares)
        assert (await call(client, 'match_agent_invitations'))['results'] == []
    active.set(b)
    b.shares.clear()
    before = copy.deepcopy(b.writes)
    async with Client(mcp) as client:
        recovery = await call(client, 'accept_agent_invitation', inviter_userid=OWN,
            topic=invite['topic'], sender='Sura agent', introduction='Approved introduction')
    assert recovery['status'] != 'introduction_posted' and b.writes == before
    with pytest.raises(PermissionError):
        a.read_records(PEER, accepted['data_type'])
