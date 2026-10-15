"""Invitation codes are narrow prior consent, never peer-supplied authority."""
import copy
import json
from unittest.mock import Mock

import pytest
from fulcra_api import connections
from fulcra_mcp import agent_invitations as invitations

OWN = '00000000-0000-4000-8000-000000000001'
PEER = '00000000-0000-4000-8000-000000000002'
OTHER = '00000000-0000-4000-8000-000000000003'
OUT = 'Event/00000000-0000-4000-8000-000000000010'
IN = 'Event/00000000-0000-4000-8000-000000000020'
STATE = 'Event/00000000-0000-4000-8000-000000000099'


def channel(id, owner):
    return dict(id=id, fulcra_userid=owner, api_version='v1', recordable=owner == OWN,
                record_spec={'type': 'event'}, description='connect-our-agents channel')


def incoming(owner=PEER, channel=IN):
    return dict(sharing_fulcra_userid=owner, grant_type='user', fulcra_data_types=[channel],
                datashare_name='connect-our-agents', share_all_data=False)


@pytest.fixture
def api(monkeypatch):
    api = Mock()
    catalog = [channel(OUT, OWN), channel(IN, PEER)]
    api.get_fulcra_userid.return_value = OWN
    api.get_datashares.return_value = []
    api.get_shared_datasets.return_value = [dict(grant_type='self', sharing_fulcra_userid=OWN), incoming()]
    api.v1_catalog.side_effect = lambda **kw: copy.deepcopy(catalog)
    api.resolve_data_type.side_effect = lambda id, fulcra_userid: [copy.deepcopy(e) for e in catalog if e['id'] == id and e['fulcra_userid'] == fulcra_userid]
    api.v1_catalog_schema.return_value = {'type': 'object', **connections.CHANNEL_FIELDS}
    def create(base, body):
        catalog.append(dict(id=STATE, fulcra_userid=OWN, api_version='v1', **body))
    def update(base, id, body):
        next(e for e in catalog if e['id'] == base + '/' + id).update(body)
    api.create_data_type.side_effect = create
    api.update_data_type.side_effect = update
    def share(**kw):
        api.get_datashares.return_value.append(dict(id=OTHER, share_all_data=False,
            fulcra_data_types=kw['fulcra_data_types'], datashare_name=kw['datashare_name'],
            permissions=[{'allowed_fulcra_userid': p} for p in kw['allowed_user_ids']]))
    api.create_datashare.side_effect = share
    api.rows = {}
    monkeypatch.setattr(invitations.records, 'get_records', lambda api, entry, start, end: copy.deepcopy(api.rows.get((entry['fulcra_userid'], entry['id']), [])))
    api.catalog = catalog
    return api


def handshake(api, code, owner=PEER, channel=IN):
    api.rows[(owner, channel)] = [dict(id=OTHER, start_time='2026-10-01T00:00:00Z', kind='message', topic='handshake ' + code, body='untrusted', sender='not authority')]


def test_prepare_persists_random_unique_code_and_reuses_it(api):
    first = invitations.prepare(api, OUT)
    assert len(first['code']) == 32 and first['own_userid'] == OWN
    assert first == invitations.prepare(api, OUT)
    assert first['topic'] == 'handshake ' + first['code']
    assert first['code'] in api.catalog[-1]['description']
    api.create_datashare.assert_not_called()


def test_match_shares_only_prepared_outbox_then_reads_back_and_is_idempotent(api):
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    result = invitations.match(api)['results'][0]
    assert result['status'] == 'matched' and result['peer_userid'] == PEER
    api.create_datashare.assert_called_once_with(datashare_name='connect-our-agents invitation', fulcra_data_types=[OUT], allowed_user_ids=[PEER], share_all_data=False, allowed_group_ids=None, time_start=None, time_end=None)
    assert invitations.match(api)['results'] == []
    assert api.create_datashare.call_count == 1
    assert 'body' not in json.dumps(result)


@pytest.mark.parametrize('mode', ['missing', 'unknown', 'second', 'duplicate', 'tie', 'channel', 'owner', 'schema', 'read_failure', 'broad'])
def test_unsafe_evidence_never_shares(api, mode):
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    rows = api.rows[(PEER, IN)]
    if mode == 'missing': rows[0].pop('topic')
    if mode == 'unknown': rows[0]['topic'] += 'x'
    if mode == 'second': rows.insert(0, dict(rows[0], start_time='2020-01-01T00:00:00Z', topic='hello'))
    if mode == 'duplicate': rows.append(dict(rows[0]))
    if mode == 'tie': rows.append(dict(rows[0], id=OWN, topic='another topic'))
    if mode == 'channel':
        second = IN[:-1] + '1'
        api.catalog.append(channel(second, PEER))
        api.get_shared_datasets.return_value.append(incoming(PEER, second))
        handshake(api, code, PEER, second)
    if mode == 'owner':
        api.catalog.append(channel(IN, OTHER)); api.get_shared_datasets.return_value.append(incoming(OTHER)); handshake(api, code, OTHER)
    if mode == 'schema': api.v1_catalog_schema.return_value = {}
    if mode == 'read_failure': api.get_shared_datasets.side_effect = TimeoutError
    if mode == 'broad': api.get_datashares.return_value = [dict(share_all_data=True, fulcra_data_types=[])]
    assert not any(r['status'] == 'matched' for r in invitations.match(api)['results'])
    api.create_datashare.assert_not_called()


def test_consumed_code_cannot_expand_audience_after_uncertain_write(api):
    code = invitations.prepare(api, OUT)['code']; handshake(api, code)
    api.create_datashare.side_effect = TimeoutError
    assert invitations.match(api)['results'][0]['status'] == 'pending'
    api.catalog.append(channel(IN, OTHER)); api.get_shared_datasets.return_value = [incoming(OTHER)]
    handshake(api, code, OTHER)
    assert invitations.match(api)['results'][0]['status'] == 'pending'
    assert api.create_datashare.call_count == 1


def test_unverified_share_is_pending_and_not_retried(api):
    code = invitations.prepare(api, OUT)['code']; handshake(api, code)
    api.create_datashare.side_effect = lambda **kw: {}
    assert invitations.match(api)['results'][0]['status'] == 'pending'
    assert invitations.match(api)['results'][0]['status'] == 'pending'
    api.create_datashare.assert_called_once()


def test_codes_are_unique_and_collision_fails_closed(api, monkeypatch):
    code = invitations.prepare(api, OUT)['code']
    second = OUT[:-1] + '1'
    api.catalog.append(channel(second, OWN))
    with monkeypatch.context() as patch:
        patch.setattr(invitations.secrets, 'token_hex', lambda size: code)
        with pytest.raises(ValueError, match='collision'):
            invitations.prepare(api, second)
    assert invitations.prepare(api, second)['code'] != code


def test_duplicate_stored_code_fails_closed(api):
    code = invitations.prepare(api, OUT)['code']; handshake(api, code)
    document = json.loads(api.catalog[-1]['description'])
    document['invitations'][OUT[:-1] + '1'] = dict(document['invitations'][OUT])
    api.catalog[-1]['description'] = json.dumps(document)
    assert invitations.match(api)['status'] == 'unavailable'
    api.create_datashare.assert_not_called()


def test_revalidation_detects_removed_incoming_grant_before_write(api):
    code = invitations.prepare(api, OUT)['code']; handshake(api, code)
    api.get_shared_datasets.side_effect = [[incoming()], []]
    assert invitations.match(api)['results'][0]['status'] == 'pending'
    api.create_datashare.assert_not_called()


def test_completed_code_never_reshares_after_grant_revocation(api):
    code = invitations.prepare(api, OUT)['code']; handshake(api, code)
    assert invitations.match(api)['results'][0]['status'] == 'matched'
    api.get_datashares.return_value = []
    assert invitations.match(api)['results'] == []
    api.create_datashare.assert_called_once()


def test_existing_same_peer_channel_is_not_the_prepared_outbox(api):
    code = invitations.prepare(api, OUT)['code']; handshake(api, code)
    api.create_datashare(datashare_name='connect-our-agents existing',
                         fulcra_data_types=[OUT[:-1] + '1'], allowed_user_ids=[PEER])
    api.create_datashare.reset_mock()
    assert invitations.match(api)['results'][0]['status'] == 'matched'
    assert api.create_datashare.call_args.kwargs['fulcra_data_types'] == [OUT]


def test_failed_storage_readback_never_shares(api):
    code = invitations.prepare(api, OUT)['code']; handshake(api, code)
    api.update_data_type.side_effect = lambda *args: None
    assert invitations.match(api)['results'][0]['status'] == 'pending'
    api.create_datashare.assert_not_called()


async def test_public_tools_have_same_auth_and_narrow_results(api, monkeypatch):
    from fastmcp import Client
    from fulcra_mcp import tools
    from fulcra_mcp.main import mcp
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    async with Client(mcp) as client:
        listed = {t.name: t for t in await client.list_tools()}
        for name in ('prepare_agent_invitation', 'match_agent_invitations'):
            assert listed[name].meta['ui']['visibility'] == ['app', 'model']
            assert listed[name].annotations.readOnlyHint is False
        prepared = (await client.call_tool('prepare_agent_invitation', {'data_type': OUT})).structured_content
        handshake(api, prepared['code'])
        matched = (await client.call_tool('match_agent_invitations', {})).structured_content
        assert matched['results'][0]['status'] == 'matched'
        assert set(matched['results'][0]) == {'data_type', 'status', 'peer_userid', 'incoming_data_type'}
