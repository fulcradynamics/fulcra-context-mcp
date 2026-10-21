"""Private preference persistence in one owned Event data type description."""
import json

import pytest
from fastmcp import Client
from fulcra_mcp.main import mcp
from fulcra_mcp import contact_preferences as policy

OWN = '00000000-0000-4000-8000-000000000001'
CONNECTION = 'Event/00000000-0000-4000-8000-0000000000aa'
PEER = '00000000-0000-4000-8000-000000000002'
PREFS = 'Event/00000000-0000-4000-8000-0000000000ff'


@pytest.fixture
def storage(fake_fulcra):
    fake_fulcra.get_fulcra_userid.return_value = OWN
    fake_fulcra.get_datashares.return_value = []
    catalog = []
    fake_fulcra.v1_catalog.side_effect = lambda **kwargs: [dict(e) for e in catalog]
    def create(base, body):
        assert base == 'Event' and set(body) == {'name', 'description'}
        catalog.append(dict(id=PREFS, fulcra_userid=OWN, api_version='v1', **body))
        return catalog[-1]
    def update(base, type_id, body):
        assert list(body) == ['description']
        next(e for e in catalog if e['id'] == base + '/' + type_id).update(body)
    fake_fulcra.create_data_type.side_effect = create
    fake_fulcra.update_data_type.side_effect = update
    return fake_fulcra, catalog


async def test_native_defaults_guidance_and_verified_update(storage):
    api, catalog = storage
    async with Client(mcp) as client:
        initial = (await client.call_tool('get_fulcra_settings', {})).structured_content
        assert initial['values'] == policy.native_values({k: policy.DEFAULTS[k] for k in policy.SCHEMA})
        assert initial['values']['acknowledge_messages'] is True
        assert initial['values']['share_contact_status'] is True
        assert initial['values']['pause_autonomous_replies'] is False
        assert initial['checking_preferences'] == ''
        assert 'checking_preferences' not in initial['schema']['properties']
        assert initial['layout'][-1]['title'] == 'For more specific preferences, chat with your agent.'
        api.create_data_type.assert_not_called()
        saved = (await client.call_tool('update_fulcra_settings', {'set': {
            'checking_preferences': 'Treecle messages about travel are important.',
            'pause_autonomous_replies': True}})).structured_content
        assert saved['verified'] is True
        current = (await client.call_tool('get_fulcra_settings', {})).structured_content
        assert current['values']['pause_autonomous_replies'] is True
        assert current['checking_preferences'] == 'Treecle messages about travel are important.'
    assert len(catalog) == 1 and catalog[0]['name'] == 'Fulcra Contact Preferences'
    policy.update(api, {'notifications': 'none'})
    api.create_data_type.assert_called_once()
    assert json.loads(catalog[0]['description'])['global_preferences']['notifications'] == 'none'


@pytest.mark.parametrize('changes', [dict(acknowledge_messages='true'), dict(unanswered_days=True),
    dict(unanswered_days=0), dict(notifications='always'), dict(interval=30), dict(autonomous_replies=True),
    dict(special_instructions='x'), dict(checking_preferences='x' * 2001), {}])
async def test_invalid_updates_do_not_write(storage, changes):
    api, _ = storage
    async with Client(mcp) as client:
        result = await client.call_tool('update_fulcra_settings', {'set': changes}, raise_on_error=False)
        assert result.is_error
    api.create_data_type.assert_not_called()


def test_contact_overrides_share_the_document(storage):
    api, _ = storage
    key = policy.scope(CONNECTION, PEER)
    policy.update(api, {'notifications': 'none'})
    policy.set_overrides(api, key, {'unanswered_days': 5, 'checking_preferences': 'Brief replies.'})
    values, overrides = policy.contact(api, key)
    assert values['unanswered_days'] == 5 and values['notifications'] == 'none'
    assert values['checking_preferences'] == 'Brief replies.'
    assert overrides == {'unanswered_days': 5, 'checking_preferences': 'Brief replies.'}
    policy.set_overrides(api, key, {})
    assert policy.contact(api, key) == (policy.read(api), {})
    assert policy.read(api)['notifications'] == 'none'
    assert api.update_data_type.call_count == 2


def test_global_pause_applies_to_every_contact():
    paused = {**policy.DEFAULTS, 'pause_autonomous_replies': True}
    assert policy.effective(paused, {'pause_autonomous_replies': False})['pause_autonomous_replies'] is True
    assert policy.effective(policy.DEFAULTS, {'pause_autonomous_replies': True})['pause_autonomous_replies'] is True
    assert policy.effective(policy.DEFAULTS, {'share_contact_status': False})['share_contact_status'] is False


async def test_notification_labels_roundtrip_to_canonical_storage(storage):
    api, catalog = storage
    async with Client(mcp) as client:
        for stored, label in policy.NOTIFICATION_LABELS.items():
            saved = (await client.call_tool('update_fulcra_settings', {'set': {
                'notifications': label, 'attention_new_unmatched_contact': False}})).structured_content
            assert saved['values']['notifications'] == label
            assert policy.read(api)['notifications'] == stored
            assert policy.read(api)['attention_new_unmatched_contact'] is False
            key = policy.scope(CONNECTION, PEER)
            policy.set_overrides(api, key, {'attention_new_matched_contact': False})
            values, _ = policy.contact(api, key)
            assert values['notifications'] == stored
            assert values['attention_new_matched_contact'] is False


@pytest.mark.parametrize('share', [dict(share_all_data=True, fulcra_data_types=[]),
    dict(share_all_data=False, fulcra_data_types=['Event/*']),
    dict(share_all_data=False, fulcra_data_types=[PREFS])])
def test_shared_preferences_fail_closed(storage, share):
    api, _ = storage
    policy.update(api, {'notifications': 'none'})
    api.get_datashares.return_value = [share]
    with pytest.raises(ValueError):
        policy.read(api)
    with pytest.raises(ValueError):
        policy.update(api, {'notifications': 'all_messages'})


@pytest.mark.parametrize('description', ['not json', '{"version":2,"global_preferences":{},"overrides":{}}',
    '{"version":1,"global_preferences":{"autonomous_replies":true},"overrides":{}}',
    '{"version":1,"global_preferences":{},"overrides":{"bad":{}}}'])
def test_malformed_document_fails_closed(storage, description):
    api, catalog = storage
    catalog.append(dict(id=PREFS, fulcra_userid=OWN, api_version='v1', name=policy.NAME, description=description))
    with pytest.raises(ValueError):
        policy.read(api)
    with pytest.raises(ValueError):
        policy.update(api, {'notifications': 'none'})
    api.update_data_type.assert_not_called()


def test_ignores_foreign_and_archived_types_and_detects_unverified_save(storage):
    api, catalog = storage
    catalog.append(dict(id='Event/00000000-0000-4000-8000-0000000000ee', fulcra_userid=PEER,
                        api_version='v1', name=policy.NAME, description='{}'))
    catalog.append(dict(id='Event/00000000-0000-4000-8000-0000000000dd', fulcra_userid=OWN, deprecated=True,
                        api_version='v1', name=policy.NAME, description='{}'))
    assert policy.read(api) == policy.DEFAULTS
    api.create_data_type.side_effect = None
    with pytest.raises(ValueError):
        policy.update(api, {'notifications': 'none'})


async def test_create_share_refuses_preferences_type(storage):
    api, _ = storage
    policy.update(api, {'notifications': 'none'})
    async with Client(mcp) as client:
        result = await client.call_tool('create_share', {
            'name': 'x', 'with_user_ids': [PEER], 'data_types': [PREFS]})
    assert 'private' in result.content[0].text
    api.create_datashare.assert_not_called()


def test_real_sdk_create_then_update_description(monkeypatch):
    from datetime import datetime, timedelta
    from email.message import Message
    from io import BytesIO
    from urllib.error import HTTPError
    from urllib.parse import urlparse
    from fulcra_api.core import FulcraAPI
    from fulcra_api.credentials import FulcraCredentials
    api = FulcraAPI(oidc_audience='https://synthetic.invalid')
    api.fulcra_credentials = FulcraCredentials(access_token='synthetic',
                                               access_token_expiration=datetime.now() + timedelta(hours=1))
    monkeypatch.setattr(api, 'get_token_claims', lambda: {'fulcradynamics.com/userid': OWN})
    monkeypatch.setattr(api, 'get_datashares', lambda: [])
    row = {}
    methods = []
    def transport(req):
        path = urlparse(req.full_url).path
        methods.append(req.get_method())
        if path == '/data/v1/catalog':
            return BytesIO(json.dumps([row] if row else []).encode())
        if req.get_method() == 'GET':
            return BytesIO(json.dumps(row).encode())
        body = json.loads(req.data)
        if req.get_method() == 'POST':
            assert path == '/input/v1/data_type/Event'
            row.update(id=PREFS, fulcra_userid=OWN, api_version='v1', **body)
        else:
            assert path == '/input/v1/data_type/' + PREFS and list(body) == ['description']
            row.update(body)
        headers = Message(); headers['Location'] = '/input/v1/data_type/' + PREFS
        raise HTTPError(req.full_url, 303, 'See Other', headers, None)
    monkeypatch.setattr('urllib.request.urlopen', transport)
    assert policy.update(api, {'acknowledge_messages': False})['acknowledge_messages'] is False
    assert policy.update(api, {'unanswered_days': 4})['acknowledge_messages'] is False
    assert methods.count('POST') == 1 and methods.count('PUT') == 1
    assert policy.read(api)['unanswered_days'] == 4
