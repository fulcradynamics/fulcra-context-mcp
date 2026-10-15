"""Regression coverage for invitation matching and private covering grants."""
import json
import pytest
from test_agent_invitations import api, handshake, invitations, OWN, PEER, OTHER, OUT, IN, STATE


@pytest.mark.parametrize('kind', ['ack', 'reply', 'message'])
def test_later_inherited_topics_preserve_first_candidate(api, kind):
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    api.rows[(PEER, IN)].append(dict(api.rows[(PEER, IN)][0],
        id=OWN, kind=kind, start_time='2026-10-02T00:00:00Z'))
    assert invitations.match(api)['results'][0]['status'] == 'matched'
    assert invitations.match(api)['results'] == []
    api.create_datashare.assert_called_once()


def test_consumed_uncertain_attempt_verifies_despite_later_topic(api):
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    share = api.create_datashare.side_effect
    def uncertain(**kwargs):
        share(**kwargs)
        raise TimeoutError
    api.create_datashare.side_effect = uncertain
    assert invitations.match(api)['results'][0]['status'] == 'pending'
    api.rows[(PEER, IN)].append(dict(api.rows[(PEER, IN)][0],
        id=OWN, kind='reply', start_time='2026-10-02T00:00:00Z'))
    assert invitations.match(api)['results'][0]['status'] == 'matched'
    assert invitations.match(api)['results'] == []
    api.create_datashare.assert_called_once()


def test_completed_invitation_leaves_later_lifecycle_to_discovery(api):
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    assert invitations.match(api)['results'][0]['status'] == 'matched'
    assert json.loads(api.catalog[-1]['description'])['invitations'][OUT]['state'] == 'completed'
    api.get_datashares.return_value[0]['permissions'].append({'allowed_fulcra_userid': OTHER})
    api.get_shared_datasets.side_effect = AssertionError('Completed invitations need no history scan')
    assert invitations.match(api) == {'results': []}
    api.get_datashares.return_value = []
    assert invitations.match(api) == {'results': []}
    api.create_datashare.assert_called_once()


def test_completion_save_failure_retains_consumed_no_retry_state(api):
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    update = api.update_data_type.side_effect
    def fail_completion(base, id, body):
        if json.loads(body['description'])['invitations'][OUT]['state'] == 'completed':
            raise TimeoutError
        update(base, id, body)
    api.update_data_type.side_effect = fail_completion
    assert invitations.match(api)['results'][0]['status'] == 'pending'
    assert json.loads(api.catalog[-1]['description'])['invitations'][OUT]['state'] == 'consumed'
    api.get_datashares.return_value = []
    assert invitations.match(api)['results'][0]['status'] == 'pending'
    api.create_datashare.assert_called_once()


def test_uncertain_attempt_does_not_accept_expanded_audience(api):
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    share = api.create_datashare.side_effect
    def uncertain(**kwargs):
        share(**kwargs)
        raise TimeoutError
    api.create_datashare.side_effect = uncertain
    assert invitations.match(api)['results'][0]['status'] == 'pending'
    api.get_datashares.return_value[0]['permissions'].append({'allowed_fulcra_userid': OTHER})
    assert invitations.match(api)['results'][0]['status'] == 'pending'
    assert json.loads(api.catalog[-1]['description'])['invitations'][OUT]['state'] == 'consumed'
    api.create_datashare.assert_called_once()


@pytest.mark.parametrize('private_name', [invitations.NAME, 'Fulcra Contact Preferences'])
@pytest.mark.parametrize('grant', [
    {'share_all_data': True}, {'data_types': ['Event']},
    {'data_types': ['Event/*']}, {'data_types': ['*']}, {'data_types': [STATE]},
])
async def test_public_covering_shares_cannot_disclose_private_storage(api, monkeypatch, private_name, grant):
    from fastmcp import Client
    from fulcra_mcp import tools
    from fulcra_mcp.main import mcp
    invitations.prepare(api, OUT)
    api.catalog[-1]['name'] = private_name
    api.create_datashare.side_effect = None
    api.create_datashare.return_value = {}
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    async with Client(mcp) as client:
        result = await client.call_tool('create_share', {'name': 'private test', 'with_user_ids': [PEER], **grant})
    assert 'private and cannot be shared' in result.content[0].text
    api.create_datashare.assert_not_called()


@pytest.mark.parametrize('grant', [{'data_types': [OUT]}, {'file_paths': ['/shared/']}])
async def test_public_unrelated_narrow_shares_remain_allowed(api, monkeypatch, grant):
    from fastmcp import Client
    from fulcra_mcp import tools
    from fulcra_mcp.main import mcp
    invitations.prepare(api, OUT)
    api.catalog.append(dict(api.catalog[-1], id=STATE[:-1] + '8', name='Fulcra Contact Preferences'))
    api.create_datashare.side_effect = None
    api.create_datashare.return_value = {}
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    async with Client(mcp) as client:
        result = await client.call_tool('create_share', {'name': 'narrow test', 'with_user_ids': [PEER], **grant})
    assert 'Created share' in result.content[0].text
    api.create_datashare.assert_called_once()
