"""Private preference persistence and effective-policy boundaries."""
import io
import json

import pytest
from fastmcp import Client
from fulcra_mcp.main import mcp

ROOT = '/agent/chatgpt/contact-preferences'


@pytest.fixture
def storage(fake_fulcra):
    fake_fulcra.get_fulcra_userid.return_value = 'me'
    fake_fulcra.get_datashares.return_value = []
    files = {}
    fake_fulcra.list_files.side_effect = lambda path: {'files': [
        {'id': name, 'name': name} for name in files] if path == ROOT else [], 'folders': []}
    fake_fulcra.download_file.side_effect = lambda name: io.BytesIO(files[name])
    def upload(data, content_type, size, path):
        files[path.rsplit('/', 1)[1]] = data
        return {'id': path.rsplit('/', 1)[1]}
    fake_fulcra.upload_file.side_effect = upload
    return fake_fulcra, files


async def test_native_defaults_and_verified_partial_update(storage):
    api, files = storage
    async with Client(mcp) as client:
        initial = (await client.call_tool('fulcra_settings_read', {})).structured_content
        assert initial['values']['status_metadata'] is True
        assert initial['values']['autonomous_replies'] is False
        assert initial['values']['unanswered_days'] == 2
        assert initial['values']['attention_waiting'] is True
        assert initial['values']['attention_overdue'] is True
        assert initial['values']['attention_high_priority'] is True
        api.upload_file.assert_not_called()
        saved = (await client.call_tool('fulcra_settings_update', {'set': {'special_instructions': 'Keep replies brief.'}})).structured_content
        assert saved['verified'] is True
        current = (await client.call_tool('fulcra_settings_read', {})).structured_content
        assert current['values']['special_instructions'] == 'Keep replies brief.'
        assert current['values']['autonomous_replies'] is False
        assert len(files) == 1
        assert all('/mesh-checks/' not in str(c) for c in api.upload_file.call_args_list)


@pytest.mark.parametrize('changes', [dict(autonomous_replies='true'), dict(unanswered_days=True),
    dict(unanswered_days=0), dict(notifications='always'), dict(interval=30),
    dict(special_instructions='x' * 2001), {}])
async def test_invalid_updates_do_not_write(storage, changes):
    api, _ = storage
    async with Client(mcp) as client:
        result = await client.call_tool('fulcra_settings_update', {'set': changes}, raise_on_error=False)
        assert result.is_error
    api.upload_file.assert_not_called()


async def test_peer_membership_notification_default_and_persistence(storage):
    api, _ = storage
    async with Client(mcp) as client:
        initial = (await client.call_tool('fulcra_settings_read', {})).structured_content
        assert initial['values']['attention_peer_membership_announcements'] is True
        result = await client.call_tool('fulcra_settings_update', {'set': {'attention_peer_membership_announcements': False}})
        assert result.structured_content['verified'] is True
        current = (await client.call_tool('fulcra_settings_read', {})).structured_content
        assert current['values']['attention_peer_membership_announcements'] is False
        assert current['values']['autonomous_replies'] is False


async def test_preserve_unrelated_fields_and_fresh_reads(storage):
    api, files = storage
    from fulcra_mcp import contact_preferences as policy
    policy.update(api, {'notifications': 'none'})
    document = policy.load(api)
    document['future_metadata'] = {'keep': True}
    files['settings.md'] = ('```json\n' + json.dumps(document) + '\n```').encode()
    policy.update(api, {'autonomous_replies': True})
    assert policy.load(api)['future_metadata'] == {'keep': True}
    assert policy.read(api)['notifications'] == 'none'
    api.get_fulcra_userid.return_value = 'other'
    with pytest.raises(ValueError):
        policy.read(api)


@pytest.mark.parametrize('share', [dict(share_all_data=True),
    dict(share_all_data=False, fulcra_data_types=['file:/agent/']),
    dict(share_all_data=False, fulcra_data_types=['filehistory:' + ROOT + '/settings.md']),
    dict(share_all_data=False, fulcra_data_types=['file:/']),
    dict(share_all_data=False, file_paths=['/agent/']),
    dict(share_all_data=False, file_history_paths=[ROOT + '/settings.md'])])
def test_exposed_settings_fail_closed(storage, share):
    from fulcra_mcp import contact_preferences as policy
    api, _ = storage
    api.get_datashares.return_value = [share]
    with pytest.raises(ValueError):
        policy.update(api, {'autonomous_replies': True})
    api.upload_file.assert_not_called()


def test_malformed_and_unverified_save_not_success(storage):
    from fulcra_mcp import contact_preferences as policy
    api, files = storage
    files['settings.md'] = b'bad'
    with pytest.raises(ValueError): policy.update(api, {'notifications': 'none'})
    api.upload_file.assert_not_called()
    files.clear()
    api.upload_file.side_effect = None
    with pytest.raises(ValueError): policy.update(api, {'notifications': 'none'})


@pytest.mark.parametrize('legacy_status', [False, True, None])
def test_legacy_status_reset_is_read_only_and_later_choices_survive(storage, legacy_status):
    from fulcra_mcp import contact_preferences as policy
    api, files = storage
    preferences = {'notifications': 'none'}
    if legacy_status is not None:
        preferences['status_metadata'] = legacy_status
    document = dict(version=1, account_id='me', preferences=preferences, future='keep')
    files['settings.md'] = ('```json\n' + json.dumps(document) + '\n```').encode()
    assert policy.read(api)['status_metadata'] is True
    api.upload_file.assert_not_called()
    policy.update(api, {'special_instructions': 'Brief.'})
    assert policy.load(api)['version'] == 2
    assert policy.load(api)['future'] == 'keep'
    assert policy.read(api)['status_metadata'] is True
    policy.update(api, {'status_metadata': False})
    assert policy.read(api)['status_metadata'] is False
    policy.update(api, {'special_instructions': 'Even briefer.'})
    assert policy.read(api)['status_metadata'] is False
    assert policy.read(api)['notifications'] == 'none'


def test_explicit_opt_out_during_first_legacy_update_wins(storage):
    from fulcra_mcp import contact_preferences as policy
    api, files = storage
    files['settings.md'] = b'```json\n{"version":1,"account_id":"me","preferences":{"status_metadata":false}}\n```'
    policy.update(api, {'status_metadata': False})
    assert policy.read(api)['status_metadata'] is False


def test_owned_override_marker_precedence():
    from fulcra_mcp import contact_preferences as policy
    original = 'connect-agents-with-anyone channel\n[mesh_identifier: "Friend"]'
    description = policy.write_overrides(original, {'autonomous_replies': True, 'unanswered_days': 3})
    assert description.endswith('[mesh_identifier: "Friend"]')
    overrides = policy.parse_overrides(description)
    assert policy.effective(policy.DEFAULTS, overrides)['autonomous_replies'] is False
    assert policy.effective(policy.DEFAULTS, overrides)['unanswered_days'] == 3
    enabled = {**policy.DEFAULTS, 'autonomous_replies': True}
    assert policy.effective(enabled, overrides)['autonomous_replies'] is True
    assert policy.effective(enabled, {'autonomous_replies': False})['autonomous_replies'] is False
    assert policy.parse_overrides(policy.write_overrides(description, {})) == {}
    with pytest.raises(ValueError): policy.parse_overrides(description + '\n[contact_preferences: {}]')


def test_real_sdk_private_upload_and_independent_download(monkeypatch):
    from fulcra_api.core import FulcraAPI
    from fulcra_mcp import contact_preferences as policy
    api = FulcraAPI()
    monkeypatch.setattr(api, 'get_token_claims', lambda: {'fulcradynamics.com/userid': 'me'})
    stored = {}
    calls = []
    def transport(endpoint, **kwargs):
        calls.append((endpoint, kwargs.get('method', 'GET')))
        if endpoint == '/user/v1/datashare':
            return '[]'
        if endpoint == '/input/v1/file_upload':
            if kwargs.get('method') == 'POST':
                assert kwargs['data']['path'] == ROOT
                assert kwargs['data']['name'] == 'settings.md'
                return json.dumps({'url': 'https://upload.synthetic.invalid', 'id': 'private'})
            assert kwargs['query']['path'] == ROOT
            return json.dumps({'files': [{'name': 'settings.md', 'id': 'private'}] if stored else [], 'folders': []})
        assert endpoint == '/input/v1/file_upload/private/download'
        return io.BytesIO(stored['data'])
    def upload(request):
        assert request.full_url == 'https://upload.synthetic.invalid'
        assert request.method == 'POST'
        stored['data'] = request.data
        return io.BytesIO(b'')
    monkeypatch.setattr(api, 'fulcra_api', transport)
    monkeypatch.setattr('urllib.request.urlopen', upload)
    result = policy.update(api, {'special_instructions': 'Brief, please.'})
    assert result['special_instructions'] == 'Brief, please.'
    assert calls[-1] == ('/input/v1/file_upload/private/download', 'GET')
    assert sum(method == 'POST' for _, method in calls) == 1
