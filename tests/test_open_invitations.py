"""Open invitations isolate each authenticated responder from the template."""
import json
import pytest
from test_agent_invitations import api, channel, incoming, handshake, OWN, PEER, OTHER, OUT, IN
from fulcra_mcp import agent_invitations as invitations


def test_open_preparation_is_distinct_and_cannot_switch_modes(api):
    prepared = invitations.prepare(api, OUT, open_invitation=True)
    assert prepared['topic'] == 'open_invitation ' + prepared['code']
    assert invitations.prepare(api, OUT, open_invitation=True) == prepared
    with pytest.raises(ValueError):
        invitations.prepare(api, OUT)
    handshake(api, prepared['code'])
    assert not any(r['status'] == 'matched' for r in invitations.match(api)['results'])
    api.create_datashare.assert_not_called()


def respond(api, code, peer=PEER):
    handshake(api, code, owner=peer)
    api.rows[(peer, IN)][0].update(topic='open_invitation ' + code, sender='Alex')


def clone_api(api):
    original = api.create_data_type.side_effect
    def create(base, body):
        if body.get('name') == invitations.NAME:
            return original(base, body)
        id = 'Event/00000000-0000-4000-8000-' + str(100 + len(api.catalog)).zfill(12)
        api.catalog.append(dict(channel(id, OWN), **body))
        api.catalog[-1]['record_spec']['type'] = 'event'  # Inherited from Event by the backend.
        return {'id': id}
    api.create_data_type.side_effect = create


def test_multiple_responders_get_distinct_outboxes_and_rechecks_do_not_write(api):
    clone_api(api)
    prepared = invitations.prepare(api, OUT, open_invitation=True)
    api.catalog.append(channel(IN, OTHER))
    api.get_shared_datasets.return_value.append(incoming(OTHER))
    respond(api, prepared['code'])
    respond(api, prepared['code'], OTHER)
    results = invitations.match(api)['results']
    assert len(results) == 2
    assert {r['peer_userid'] for r in results} == {PEER, OTHER}
    assert all(r['status'] == 'matched' for r in results)
    assert len({r['data_type'] for r in results}) == 2
    assert OUT not in {r['data_type'] for r in results}
    assert all(r['identifier'] == 'Alex via ' + OUT for r in results)
    created = api.create_data_type.call_count
    assert invitations.match(api)['results'] == []
    assert api.create_data_type.call_count == created
    assert api.create_datashare.call_count == 2
    state = invitations._state(api)[2]['invitations'][OUT]
    assert state['state'] == 'prepared'
    assert state['prefix'] == 'open_invitation'


@pytest.mark.parametrize('failure', ['create', 'share'])
def test_uncertain_open_writes_are_not_retried(api, failure):
    clone_api(api)
    code = invitations.prepare(api, OUT, open_invitation=True)['code']
    respond(api, code)
    target = api.create_data_type if failure == 'create' else api.create_datashare
    target.side_effect = TimeoutError
    invitations.match(api)
    count = target.call_count
    invitations.match(api)
    assert target.call_count == count
    api.get_datashares.return_value = []
    invitations.match(api)
    assert target.call_count == count


def test_template_schema_read_failure_can_recover_before_creation(api, monkeypatch):
    clone_api(api)
    code = invitations.prepare(api, OUT, open_invitation=True)['code']
    respond(api, code)
    original_channel = invitations._channel
    schema = api.v1_catalog_schema.return_value

    def checked_channel(*args, **kwargs):
        result = original_channel(*args, **kwargs)
        if args[2] == OUT and kwargs.get('own'):
            api.v1_catalog_schema.side_effect = TimeoutError
        return result

    monkeypatch.setattr(invitations, '_channel', checked_channel)
    created = api.create_data_type.call_count
    assert invitations.match(api)['results'][0]['status'] == 'pending'
    assert api.create_data_type.call_count == created
    monkeypatch.setattr(invitations, '_channel', original_channel)
    api.v1_catalog_schema.side_effect = None
    api.v1_catalog_schema.return_value = schema
    assert invitations.match(api)['results'][0]['status'] == 'matched'
    assert api.create_data_type.call_count == created + 1


def test_open_prefix_cannot_redeem_individual_code(api):
    code = invitations.prepare(api, OUT)['code']
    respond(api, code)
    assert invitations.match(api)['results'][0]['status'] == 'pending'
    api.create_datashare.assert_not_called()


async def test_open_mode_is_available_over_mcp(api, monkeypatch):
    from fastmcp import Client
    from fulcra_mcp import tools
    from fulcra_mcp.main import mcp
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    async with Client(mcp) as client:
        result = (await client.call_tool('prepare_agent_invitation',
            {'data_type': OUT, 'open_invitation': True})).structured_content
        assert result['topic'] == 'open_invitation ' + result['code']


def test_bound_outbox_cannot_be_reprepared_after_revocation(api):
    clone_api(api)
    code = invitations.prepare(api, OUT, open_invitation=True)['code']
    respond(api, code)
    result = invitations.match(api)['results'][0]
    api.get_datashares.return_value = []
    before = invitations._state(api)[2]
    with pytest.raises(ValueError):
        invitations.prepare(api, result['data_type'])
    assert invitations._state(api)[2] == before
    assert invitations.match(api)['results'] == []


def test_duplicate_channels_from_one_owner_are_ambiguous_not_new_connections(api):
    clone_api(api)
    code = invitations.prepare(api, OUT, open_invitation=True)['code']
    respond(api, code)
    second = IN[:-1] + '1'
    api.catalog.append(channel(second, PEER))
    api.get_shared_datasets.return_value.append(incoming(PEER, second))
    api.rows[(PEER, second)] = api.rows[(PEER, IN)]
    count = api.create_data_type.call_count
    assert all(r['status'] == 'pending' for r in invitations.match(api)['results'])
    assert api.create_data_type.call_count == count
    api.create_datashare.assert_not_called()


def test_open_responder_gets_label_and_standard_channel_schema_without_private_code(api):
    from fulcra_mcp.contact_identifier import write_contact_identifier, parse_contact_identifier
    clone_api(api)
    api.catalog[0]['description'] = write_contact_identifier('connect-our-agents channel', 'Study group')
    code = invitations.prepare(api, OUT, open_invitation=True)['code']
    respond(api, code)
    api.rows[(PEER, IN)][0]['sender'] = OTHER
    result = invitations.match(api)['results'][0]
    assert result['status'] == 'matched'
    created = next(e for e in api.catalog if e['id'] == result['data_type'])
    assert parse_contact_identifier(created['description']) == OTHER + ' via Study group'
    from fulcra_api.connections import CHANNEL_FIELDS
    assert json.loads(created['record_spec']['schema'])['properties'] == CHANNEL_FIELDS['properties']
    assert code not in json.dumps(created)
    assert api.create_datashare.call_args.kwargs['allowed_user_ids'] == [PEER]


def test_long_valid_sender_is_bounded_not_replaced_by_generic_label(api):
    clone_api(api)
    code = invitations.prepare(api, OUT, open_invitation=True)['code']
    respond(api, code)
    api.rows[(PEER, IN)][0]['sender'] = 'A' * 128
    result = invitations.match(api)['results'][0]
    assert result['status'] == 'matched'
    assert result['identifier'].startswith('AAAA')
    assert result['identifier'].endswith(' via ' + OUT)
    assert len(result['identifier']) <= 80


STANDING = 'Event/00000000-0000-4000-8000-000000000040'


@pytest.fixture
def standing_api(api):
    create_state = api.create_data_type.side_effect
    def create(base, body):
        if body.get('name') == invitations.NAME:
            return create_state(base, body)
        id = STANDING if body['name'] == invitations.STANDING_NAME else 'Event/00000000-0000-4000-8000-' + str(100 + len(api.catalog)).zfill(12)
        api.catalog.append(dict(channel(id, OWN), name=body['name'], description=body['description']))
        return {'id': id}
    api.create_data_type.side_effect = create
    return api


def test_standing_invitation_is_created_once_and_remembers_the_name(standing_api):
    first = invitations.standing(standing_api)
    assert first['data_type'] == STANDING and first['inviter_name'] == ''
    assert first['topic'] == 'open_invitation ' + first['code']
    assert invitations.standing(standing_api, 'Leif') == dict(first, inviter_name='Leif')
    assert invitations.standing(standing_api) == dict(first, inviter_name='Leif')
    assert invitations.standing(standing_api, '') == first
    assert sum(e.get('name') == invitations.STANDING_NAME for e in standing_api.catalog) == 1
    standing_api.create_datashare.assert_not_called()


def test_standing_responders_get_their_own_outbox_without_the_private_name(standing_api):
    code = invitations.standing(standing_api, 'Leif')['code']
    respond(standing_api, code)
    result = invitations.match(standing_api)['results'][0]
    assert result['status'] == 'matched' and result['data_type'] != STANDING
    outbox = next(e for e in standing_api.catalog if e['id'] == result['data_type'])
    assert outbox['name'] == 'Alex via Open invitation'
    assert invitations.STANDING_INVITER not in outbox['description']


def test_standing_name_survives_whitespace_folding(standing_api):
    import re
    from fulcra_mcp.contact_identifier import parse_contact_identifier
    invitations.standing(standing_api, 'Leif')
    entry = next(e for e in standing_api.catalog if e['id'] == STANDING)
    folded = re.sub(r'\s+', ' ', entry['description'])
    assert invitations._standing_inviter(folded) == 'Leif'
    assert parse_contact_identifier(entry['description']) == 'Open invitation'
    assert invitations.STANDING_INVITER not in invitations._without_inviter(folded)
    entry['description'] = folded
    assert invitations.standing(standing_api, 'Sura')['inviter_name'] == 'Sura'
    assert parse_contact_identifier(entry['description']) == 'Open invitation'
