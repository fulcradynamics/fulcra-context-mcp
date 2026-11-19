"""Invitation codes are narrow prior consent, never peer-supplied authority."""
import copy
import json
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from fulcra_api import connections
from fulcra_mcp import agent_invitations as invitations
from fulcra_mcp.channel_metadata import parse_metadata

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
    def record_response(query, fulcra_userid):
        data_type = query.split('"')[1]
        return '\n'.join(json.dumps(row) for row in api.rows.get((fulcra_userid, data_type), [])).encode()
    api.fulcra_v1_records.side_effect = record_response
    api.catalog = catalog
    return api


def handshake(api, code, owner=PEER, channel=IN):
    api.rows[(owner, channel)] = [dict(id=OTHER, start_time='2026-10-01T00:00:00Z', kind='message', topic='handshake ' + code, body='untrusted', sender='not authority')]


def test_prepare_persists_random_unique_code_and_reuses_it(api):
    first = invitations.prepare(api, OUT)
    assert len(first['code']) == 32 and first['own_userid'] == OWN
    assert first == invitations.prepare(api, OUT)
    assert first['topic'] == 'handshake ' + first['code']
    assert first['code'] in api.catalog[0]['description']
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


@pytest.mark.parametrize('created,expected', [('2026-09-01T00:00:00Z', 'matched'),
                                             ('2026-10-02T00:00:00Z', 'pending')])
def test_match_uses_own_outbox_creation_not_incoming_creation(api, created, expected):
    api.catalog[0]['metadata'] = {'created_at': created}
    api.catalog[1]['metadata'] = {'created_at': '2026-11-01T00:00:00Z'}
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    assert invitations.match(api)['results'][0]['status'] == expected
    for call in api.fulcra_v1_records.call_args_list:
        days, seconds, end = re.search(r'\[(\d+)d(?:(\d+)s)?\] @ ([\d.]+)', call.args[0]).groups()
        start = datetime.fromtimestamp(float(end), timezone.utc) - timedelta(days=int(days), seconds=int(seconds or 0))
        assert timedelta(0) < datetime.fromisoformat(created) - start <= timedelta(seconds=1)


@pytest.mark.parametrize('mode', ['second', 'duplicate', 'tie'])
def test_any_handshake_in_window_matches_once(api, mode):
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    rows = api.rows[(PEER, IN)]
    if mode == 'second':
        rows.insert(0, dict(rows[0], start_time='2026-09-01T00:00:00Z', topic='hello'))
    elif mode == 'duplicate':
        rows.append(dict(rows[0]))
    else:
        rows.append(dict(rows[0], id=OWN, topic='another topic'))
    assert invitations.match(api)['results'][0]['status'] == 'matched'
    api.create_datashare.assert_called_once()


def test_old_handshake_without_creation_timestamp_does_not_match(api):
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    api.rows[(PEER, IN)][0]['start_time'] = '2020-01-01T00:00:00Z'
    assert invitations.match(api)['results'][0]['status'] == 'pending'
    api.create_datashare.assert_not_called()


@pytest.mark.parametrize('open_invitation', [False, True])
@pytest.mark.parametrize('created', [None, '2026-09-30T00:00:00.123456Z'])
def test_creation_window_on_openai_matcher(api, monkeypatch, open_invitation, created):
    import asyncio
    from fulcra_mcp import openai_endpoint, tools
    if open_invitation:
        from test_open_invitations import clone_api
        clone_api(api)
    if created:
        api.catalog[0]['metadata'] = {'created_at': created}
    prepared = invitations.prepare(api, OUT, open_invitation=open_invitation)
    handshake(api, prepared['code'])
    api.rows[(PEER, IN)][0]['topic'] = prepared['topic']
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    result = asyncio.run(openai_endpoint.match_agent_invitations())
    assert result['results'][0]['status'] == 'matched'
    for call in api.fulcra_v1_records.call_args_list:
        days, seconds, end = re.search(r'\[(\d+)d(?:(\d+)s)?\] @ ([\d.]+)', call.args[0]).groups()
        duration = timedelta(days=int(days), seconds=int(seconds or 0))
        if created:
            start = datetime.fromtimestamp(float(end), timezone.utc) - duration
            assert timedelta(0) < datetime.fromisoformat(created) - start <= timedelta(seconds=1)
        else:
            assert duration == timedelta(days=365, seconds=1)


@pytest.mark.parametrize('created', [None, '2026-09-01T00:00:00Z'])
def test_history_default_uses_channel_creation_or_one_year(api, created):
    api.catalog[0]['metadata'] = {'created_at': created}
    end = datetime(2026, 11, 12, tzinfo=timezone.utc)
    invitations._history(api, OWN, OUT, end=end)
    query = api.fulcra_v1_records.call_args.args[0]
    days, seconds, stamp = re.search(r'\[(\d+)d(?:(\d+)s)?\] @ ([\d.]+)', query).groups()
    start = datetime.fromtimestamp(float(stamp), timezone.utc) - timedelta(days=int(days), seconds=int(seconds or 0))
    expected = datetime.fromisoformat(created) if created else end - timedelta(days=365)
    assert start == expected - timedelta(seconds=1)


@pytest.mark.parametrize('created', ['invalid', '2026-01-01T00:00:00', '2099-01-01T00:00:00Z'])
def test_invalid_creation_timestamp_does_not_expand_history(api, created):
    api.catalog[0]['metadata'] = {'created_at': created}
    invitations.prepare(api, OUT)
    result = invitations.match(api)
    assert result['diagnostic']['stage'] == 'invitation_window'
    api.fulcra_v1_records.assert_not_called()
    api.create_datashare.assert_not_called()


def test_each_invitation_filters_its_own_window(api):
    second = OUT[:-1] + '1'
    api.catalog[0]['metadata'] = {'created_at': '2026-09-01T00:00:00Z'}
    api.catalog.append(dict(channel(second, OWN), metadata={'created_at': '2026-11-01T00:00:00Z'}))
    first_code = invitations.prepare(api, OUT)['code']
    second_code = invitations.prepare(api, second)['code']
    handshake(api, first_code)
    api.rows[(PEER, IN)].append(dict(api.rows[(PEER, IN)][0], topic='handshake ' + second_code))
    results = {row['data_type']: row['status'] for row in invitations.match(api)['results']}
    assert results == {OUT: 'matched', second: 'pending'}
    api.create_datashare.assert_called_once()


def test_unrelated_unnamed_direct_grant_does_not_block_matching(api):
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    api.get_shared_datasets.return_value.append(dict(incoming(),
        datashare_name=None, fulcra_data_types=['file:/shared/']))
    assert invitations.match(api)['results'][0]['status'] == 'matched'


def test_sibling_mentions_ignore_unnamed_grant():
    from fulcra_mcp.mentions import _thread_labels
    entry = dict(channel(IN, PEER), fields=connections.CHANNEL_FIELDS['properties'],
                 required_fields=connections.CHANNEL_FIELDS['required'])
    from fulcra_mcp.tools import _slim_share
    named = _slim_share(incoming())
    unnamed = _slim_share(dict(incoming(), datashare_name=None, fulcra_data_types=['file:/shared/']))
    labels = _thread_labels({'data types usable with: get_records': [entry]},
        dict(own_fulcra_userid=OWN, outgoing=[], incoming=[unnamed, named]))
    assert PEER in labels


@pytest.mark.parametrize('failure, category', [
    (TimeoutError('private code and message body'), 'transport'),
    (ValueError('private code and message body'), 'validation'),
])
def test_failure_diagnostics_do_not_expose_exception_data(api, caplog, failure, category):
    invitations.prepare(api, OUT)
    api.get_shared_datasets.side_effect = failure
    result = invitations.match(api)
    assert result['diagnostic'] == {'stage': 'incoming_grants', 'category': category}
    assert 'private code' not in json.dumps(result) + caplog.text
    api.create_datashare.assert_not_called()


@pytest.mark.parametrize('mode', ['missing', 'unknown', 'channel', 'owner', 'schema', 'read_failure', 'targeted'])
def test_unsafe_evidence_never_shares(api, mode):
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    rows = api.rows[(PEER, IN)]
    if mode == 'missing': rows[0].pop('topic')
    if mode == 'unknown': rows[0]['topic'] += 'x'

    if mode == 'channel':
        second = IN[:-1] + '1'
        api.catalog.append(channel(second, PEER))
        api.get_shared_datasets.return_value.append(incoming(PEER, second))
        handshake(api, code, PEER, second)
    if mode == 'owner':
        api.catalog.append(channel(IN, OTHER)); api.get_shared_datasets.return_value.append(incoming(OTHER)); handshake(api, code, OTHER)
    if mode == 'schema': api.v1_catalog_schema.return_value = {}
    if mode == 'read_failure': api.get_shared_datasets.side_effect = TimeoutError
    if mode == 'targeted': api.get_datashares.return_value = [dict(share_all_data=False, fulcra_data_types=[OUT])]
    assert not any(r['status'] == 'matched' for r in invitations.match(api)['results'])
    api.create_datashare.assert_not_called()


@pytest.mark.parametrize('change', [
    {'grant_type': 'group', 'group_id': OTHER},
    {'sharing_fulcra_userid': OWN},
    {'fulcra_data_types': [IN, OUT]},
    {'time_start': '2020-01-01T00:00:00Z'},
    {'time_end': '2099-01-01T00:00:00Z'},
    {'share_all_data': True},

])
def test_incoming_grant_must_remain_narrow_and_direct(api, change):
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    api.get_shared_datasets.return_value = [dict(incoming(), **change)]
    assert invitations.match(api)['results'][0]['status'] == 'pending'
    api.create_datashare.assert_not_called()


@pytest.mark.parametrize('stamp', [None, 'private body', '2026-10-01T00:00:00'])
def test_invalid_record_timestamp_fails_closed(api, stamp):
    code = invitations.prepare(api, OUT)['code']
    handshake(api, code)
    api.rows[(PEER, IN)][0]['start_time'] = stamp
    result = invitations.match(api)
    assert result['status'] == 'unavailable'
    assert result['diagnostic']['stage'] == 'handshake_timestamps'
    assert 'private body' not in json.dumps(result)
    api.create_datashare.assert_not_called()


def test_http_history_failure_is_sanitized_and_preserves_prepared_consent(api, caplog):
    from urllib.error import HTTPError
    code = invitations.prepare(api, OUT)['code']
    api.fulcra_v1_records.side_effect = HTTPError('https://invalid/' + code, 422,
        'private body ' + code, {}, None)
    result = invitations.match(api)
    assert result['diagnostic'] == dict(stage='handshake_history', category='http', http_status=422)
    assert code not in json.dumps(result) + caplog.text
    assert 'private body' not in json.dumps(result) + caplog.text
    assert parse_metadata(api.catalog[0]['description'])['invitation']['state'] == 'prepared'
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
    api.catalog.append(dict(api.catalog[0], id=OUT[:-1] + '1'))
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
    from fulcra_mcp.main import openai_mcp as mcp
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    async with Client(mcp) as client:
        listed = {t.name: t for t in await client.list_tools()}
        for name in ('prepare_agent_invitation', 'match_agent_invitations'):
            assert listed[name].meta['ui']['visibility'] == ['app']
            assert listed[name].annotations.read_only_hint is False
        prepared = (await client.call_tool('prepare_agent_invitation', {'data_type': OUT})).structured_content
        handshake(api, prepared['code'])
        matched = (await client.call_tool('match_agent_invitations', {})).structured_content
        assert matched['results'][0]['status'] == 'matched'
        assert set(matched['results'][0]) == {'data_type', 'status', 'peer_userid', 'incoming_data_type'}


NEW = 'Event/00000000-0000-4000-8000-000000000030'


@pytest.fixture
def creating(api):
    def create(base, body):
        api.catalog.append(dict(channel(NEW, OWN), name=body['name'], description=body['description']))
        return dict(id=NEW)
    api.create_data_type.side_effect = create
    return api


def test_create_labels_new_outbox_and_prepares_unshared_code(creating):
    result = invitations.create(creating, 'Leif', 'Lucian')
    assert result['data_type'] == NEW and result['identifier'] == "Lucian's agent"
    assert result['topic'] == 'handshake ' + result['code'] and result['shared_with'] is None
    entry = next(e for e in creating.catalog if e['id'] == NEW)
    assert entry['name'] == 'Leif with Lucian'
    assert 'Agent contact channel\nContact label: ' in entry['description']
    creating.create_datashare.assert_not_called()


def test_known_recipient_is_shared_up_front_and_handshake_completes(creating):
    result = invitations.create(creating, 'Leif', 'Lucian', PEER)
    creating.create_datashare.assert_called_once()
    assert creating.create_datashare.call_args.kwargs['allowed_user_ids'] == [PEER]
    handshake(creating, result['code'])
    matched = [r for r in invitations.match(creating)['results'] if r['data_type'] == NEW][0]
    assert matched['status'] == 'matched' and creating.create_datashare.call_count == 1


@pytest.mark.parametrize('recipient', [None, PEER])
async def test_create_public_result_and_readback(creating, monkeypatch, recipient):
    from fastmcp import Client
    from fulcra_mcp import tools
    from fulcra_mcp.main import openai_mcp as mcp
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: creating)
    args = {'inviter_name': 'Alex', 'recipient_name': 'Sura Novi'}
    if recipient:
        args['recipient_userid'] = recipient
    async with Client(mcp) as client:
        result = (await client.call_tool('create_agent_invitation', args)).structured_content
    assert result is not None
    assert set(result) == {'status', 'data_type', 'own_userid', 'code', 'topic', 'identifier', 'shared_with'}
    assert result['status'] == 'prepared' and result['own_userid'] == OWN
    assert result['data_type'] == NEW and result['shared_with'] == recipient
    assert result['identifier'] == "Sura Novi's agent"
    assert result['topic'] == 'handshake ' + result['code']
    assert len(result['code']) == 32 and all(c in '0123456789abcdef' for c in result['code'])
    entry = next(e for e in creating.catalog if e['id'] == NEW)
    assert result['code'] in entry['description']
    creating.record_data_type.assert_not_called()
    if recipient:
        assert creating.create_datashare.call_args.kwargs['fulcra_data_types'] == [NEW]
        assert creating.create_datashare.call_args.kwargs['allowed_user_ids'] == [recipient]
    else:
        creating.create_datashare.assert_not_called()


async def test_create_public_error_can_follow_creation(creating, monkeypatch):
    from fastmcp import Client
    from fulcra_mcp import tools
    from fulcra_mcp.main import openai_mcp as mcp
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: creating)
    creating.update_data_type.side_effect = RuntimeError('synthetic failure')
    async with Client(mcp) as client:
        result = await client.call_tool('create_agent_invitation',
            {'inviter_name': 'Alex', 'recipient_name': 'Sura Novi'}, raise_on_error=False)
    assert result.is_error
    assert result.content[0].type == 'text'
    assert 'Invitation not verified' in result.content[0].text
    creating.create_data_type.assert_called_once()
    creating.create_datashare.assert_not_called()


def test_create_rejects_bad_recipient_id_before_writing(creating):
    for bad in ('not-a-uuid', OWN):
        with pytest.raises(ValueError):
            invitations.create(creating, 'Leif', 'Lucian', bad)
    creating.create_data_type.assert_not_called()
