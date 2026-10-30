"""Synthetic accounts, real tool calls and shared domain/SDK message primitives."""
import copy
import json
from contextvars import ContextVar
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import jsonschema
from fastmcp import Client
from fulcra_api import connections
from fulcra_mcp import connection, tools
from fulcra_mcp.main import mcp, openai_mcp

OWN = '00000000-0000-4000-8000-000000000001'
PEER = '00000000-0000-4000-8000-000000000002'
OTHER = '00000000-0000-4000-8000-000000000003'


class Account:
    def __init__(self, owner, accounts):
        self.owner = owner
        self.accounts = accounts
        self.catalog = []
        self.shares = []
        self.rows = {}
        self.writes = []
        self.fail = None
        accounts[owner] = self

    def get_fulcra_userid(self):
        return self.owner

    def v1_catalog(self, fulcra_userid=None):
        return copy.deepcopy(self.accounts[fulcra_userid or self.owner].catalog)

    def resolve_data_type(self, channel, fulcra_userid):
        return [e for e in self.v1_catalog(fulcra_userid) if e['id'] == channel]

    def v1_catalog_schema(self, channel, version, fulcra_userid=None):
        entry = self.resolve_data_type(channel, fulcra_userid or self.owner)[0]
        schema = entry['record_spec']['schema']
        return {'type': 'object', **(json.loads(schema) if isinstance(schema, str) else copy.deepcopy(schema))}

    def create_data_type(self, base, body):
        self.writes.append(('create', copy.deepcopy(body)))
        entry = dict(id='Event/' + str(uuid4()), fulcra_userid=self.owner,
                     api_version='v1', recordable=True, **copy.deepcopy(body))
        entry['record_spec']['type'] = 'event'
        self.catalog.append(entry)
        if self.fail == 'create':
            raise TimeoutError()
        return copy.deepcopy(entry)

    def update_data_type(self, base, id, body):
        self.writes.append(('update', copy.deepcopy(body)))
        next(e for e in self.catalog if e['id'] == base + '/' + id).update(body)
        if self.fail == 'prepare':
            raise TimeoutError()

    def get_datashares(self):
        return copy.deepcopy(self.shares)

    def create_datashare(self, **kwargs):
        self.writes.append(('share', kwargs))
        if self.fail == 'share':
            raise TimeoutError()
        self.shares.append(dict(id=str(uuid4()), fulcra_data_types=kwargs['fulcra_data_types'],
                                share_all_data=False, datashare_name=kwargs['datashare_name'],
                                permissions=[dict(allowed_fulcra_userid=p) for p in kwargs['allowed_user_ids']]))

    def get_shared_datasets(self):
        return [dict(grant_type='user', sharing_fulcra_userid=owner,
                     fulcra_data_types=s['fulcra_data_types'], datashare_name=s['datashare_name'])
                for owner, api in self.accounts.items() for s in api.shares
                if self.owner in [p['allowed_fulcra_userid'] for p in s['permissions']]]

    def fulcra_v1_records(self, query, fulcra_userid):
        channel = query.split('"')[1]
        return '\n'.join(json.dumps(r) for r in self.read_records(fulcra_userid, channel))

    def read_records(self, owner, channel):
        if owner != self.owner and not any(
                grant['sharing_fulcra_userid'] == owner and channel in grant['fulcra_data_types']
                for grant in self.get_shared_datasets()):
            raise PermissionError('No incoming channel grant')
        return copy.deepcopy(self.accounts[owner].rows.get(channel, []))

    def validate_records(self, channel, rows, version):
        validator = jsonschema.Draft202012Validator(
            self.v1_catalog_schema(channel, version), format_checker=jsonschema.FormatChecker())
        return [error.message for row in rows for error in validator.iter_errors(row)]

    def record_data_type(self, channel, rows, version):
        self.writes.append(('send', copy.deepcopy(rows)))
        if self.fail == 'send':
            raise TimeoutError()
        self.rows.setdefault(channel, []).extend(dict(r, start_time=datetime.now(timezone.utc).isoformat()) for r in rows)
        return {'upload_id': 'synthetic'}


@pytest.fixture
def accounts(monkeypatch):
    accounts = {}
    a, b = Account(OWN, accounts), Account(PEER, accounts)
    active = ContextVar('synthetic_account', default=a)
    monkeypatch.setattr(tools, 'get_fulcra_object', active.get)
    monkeypatch.setattr(connection, 'RETRY_DELAY', 0)
    monkeypatch.setattr(connection.records, 'get_records',
        lambda api, entry, *args, **kwargs: api.read_records(entry['fulcra_userid'], entry['id']))
    return a, b, active


async def call(client, name, **args):
    result = await client.call_tool(name, args)
    return result.data if result.data is not None else result.content[0].text


@pytest.mark.parametrize('matcher', [mcp, openai_mcp], ids=['generic', 'openai'])
async def test_two_account_tool_only_lifecycle(accounts, matcher):
    a, b, active = accounts
    async with Client(mcp) as inviter:
        invite = await call(inviter, 'create_agent_invitation', inviter_name='Alex', recipient_name='Sura', recipient_userid=PEER)
        assert invite['prepared'] and invite['shared'] and not invite['sent'] and not invite['connected']
        assert not a.rows and not b.writes
        assert {invite['own_userid'], invite['data_type'], invite['code']} <= set(invite['invitation_text'].split())
        assert len(invite['invitation_text']) <= 4000
        assert 'plugin' not in invite['invitation_text'].lower()
        assert 'skill' not in invite['invitation_text'].lower()
        posted = await call(inviter, 'send_agent_message', sender='Alex agent', **invite['delivery'])
        assert posted['status'] == 'posted'
        assert a.rows[invite['data_type']][0]['body'] == invite['invitation_text']
    active.set(b)
    async with Client(mcp) as recipient:
        # The recipient actually reads the delivered invitation through a public tool.
        read = await call(recipient, 'get_records', data_type=invite['data_type'], fulcra_userid=OWN,
                          start_time='2026-01-01T00:00:00Z', end_time='2027-01-01T00:00:00Z')
        assert invite['code'] in json.dumps(read)
        acceptance = await call(recipient, 'accept_agent_invitation', inviter_userid=OWN,
            topic=invite['topic'], sender='Sura agent', introduction='Sura approved this introduction.')
        assert acceptance['status'] == 'introduction_posted' and not acceptance['connected']
        first = b.rows[acceptance['data_type']][0]
        assert first['topic'] == invite['topic'] and first['sender'] == 'Sura agent'
        assert first['kind'] == 'message'
        before = copy.deepcopy(b.writes)
        repeated = await call(recipient, 'accept_agent_invitation', inviter_userid=OWN,
            topic=invite['topic'], sender='Sura agent', introduction='Sura approved this introduction.')
        assert repeated['mid'] == acceptance['mid'] and b.writes == before
    active.set(a)
    async with Client(matcher) as inviter:
        matched = await call(inviter, 'match_agent_invitations')
        assert matched['results'][0]['status'] == 'matched'
        assert matched['results'][0]['peer_userid'] == PEER
        assert len(a.shares) == 1
        followup = await call(inviter, 'send_agent_message', connection=invite['data_type'], sender='Alex agent', body='Connected follow-up')
        assert followup['status'] == 'posted'
        assert (await call(inviter, 'match_agent_invitations'))['results'] == []


@pytest.mark.parametrize('stage', ['create', 'prepare', 'share'])
async def test_create_partial_failure_keeps_recovery_identity(accounts, stage):
    a, b, active = accounts
    a.fail = stage
    async with Client(mcp) as client:
        result = await call(client, 'create_agent_invitation', inviter_name='Alex', recipient_name='Sura', recipient_userid=PEER)
    assert result['status'] == 'uncertain' and result['retryable'] is False
    assert result['own_userid'] == OWN and not result['sent']
    if stage != 'create':
        assert result['data_type'] == a.catalog[0]['id']
    assert len([w for w in a.writes if w[0] == 'create']) == 1
    assert not a.rows


@pytest.mark.parametrize('stage', ['create', 'share', 'send'])
async def test_acceptance_partial_failure_never_retries(accounts, stage):
    a, b, active = accounts
    a.fail = stage
    args = dict(inviter_userid=PEER, topic='handshake ' + 'a'*32, sender='Actual agent', introduction='Approved hello')
    async with Client(mcp) as client:
        result = await call(client, 'accept_agent_invitation', **args)
        assert result['status'] == 'uncertain' and result['retryable'] is False
        if stage == 'send':
            assert result['sent'] is None
        before = copy.deepcopy(a.writes)
        recovery = await call(client, 'accept_agent_invitation', **args)
        assert recovery['status'] == 'recovery_required'
        assert a.writes == before
        assert recovery['mid'] == result['mid']
        assert sum(w[0] == 'send' for w in a.writes) <= 1


@pytest.mark.parametrize('bad', [dict(inviter_userid=OWN), dict(inviter_userid=PEER.upper()+' '),
    dict(topic='handshake ' + 'A'*32), dict(topic='unknown ' + 'a'*32),
    dict(sender=''), dict(introduction='')])
async def test_acceptance_malformed_identity_or_content_is_read_only(accounts, bad):
    a, b, active = accounts
    args = dict(inviter_userid=PEER, topic='handshake ' + 'a'*32, sender='Agent', introduction='Hello') | bad
    async with Client(mcp) as client:
        result = await call(client, 'accept_agent_invitation', **args)
    assert result['status'] == 'rejected' and not a.writes


async def test_reuse_empty_response_channel_and_reject_wrong_owner(accounts):
    a, b, active = accounts
    body = dict(name='Response', description='Agent contact channel', record_spec={'schema': connections.CHANNEL_FIELDS})
    other_channel = b.create_data_type('Event', body)['id']
    own_channel = a.create_data_type('Event', body)['id']
    args = dict(inviter_userid=PEER, topic='open_invitation ' + 'a'*32, sender='Agent', introduction='Approved hello')
    async with Client(mcp) as client:
        wrong = await call(client, 'accept_agent_invitation', response_channel=other_channel, **args)
        assert wrong['status'] == 'rejected'
        result = await call(client, 'accept_agent_invitation', response_channel=own_channel, **args)
    assert result['status'] == 'introduction_posted'
    assert len(a.catalog) == 1
    assert a.rows[own_channel][0]['topic'] == args['topic']


async def test_denied_acceptance_send_and_independent_broad_share(accounts, monkeypatch):
    from urllib.error import HTTPError
    a, b, active = accounts
    a.shares.append(dict(id=str(uuid4()), share_all_data=True, fulcra_data_types=[], permissions=[]))
    def deny(channel, rows, version):
        a.writes.append(('send', rows))
        raise HTTPError('synthetic', 403, 'denied', {}, None)
    monkeypatch.setattr(a, 'record_data_type', deny)
    args = dict(inviter_userid=PEER, topic='handshake ' + 'b'*32, sender='Agent', introduction='Approved hello')
    async with Client(mcp) as client:
        result = await call(client, 'accept_agent_invitation', **args)
        assert result['status'] == 'rejected' and result['shared'] and not result['sent']
        assert result['send_result']['retryable'] is False
        before = copy.deepcopy(a.writes)
        assert (await call(client, 'accept_agent_invitation', **args))['status'] == 'recovery_required'
        assert a.writes == before
    assert a.shares[0]['share_all_data'] is True
    assert sum(w[0] == 'send' for w in a.writes) == 1


async def test_generic_send_id_only_null_or_absent_fields(accounts):
    a, b, active = accounts
    async with Client(mcp) as client:
        invite = await call(client, 'create_agent_invitation', inviter_name='Alex', recipient_name='Sura', recipient_userid=PEER)
        mid = str(uuid4())
        a.rows[invite['data_type']] = [dict(id=mid, body='Different', topic=None, recipients=None)]
        before = copy.deepcopy(a.writes)
        for optional in ({}, dict(topic=None, recipients=None, artifacts=None)):
            result = await call(client, 'send_agent_message', connection=invite['data_type'],
                                sender='Agent', body='Approved text', record_id=mid, **optional)
            assert result['status'] == 'posted'
        assert a.writes == before
