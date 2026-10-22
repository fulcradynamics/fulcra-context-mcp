import pytest
from fastmcp import Client
from fulcra_mcp.main import mcp
from fulcra_mcp import contact_preferences as policy


async def test_notification_labels_group_and_new_contact_defaults(fake_fulcra):
    fake_fulcra.get_fulcra_userid.return_value = '00000000-0000-4000-8000-000000000001'
    fake_fulcra.v1_catalog.return_value = []
    fake_fulcra.get_datashares.return_value = []
    async with Client(mcp) as client:
        result = (await client.call_tool('get_fulcra_settings', {})).structured_content
    for key in ['attention_new_unmatched_contact', 'attention_new_matched_contact']:
        assert result['values'][key] is True
        assert policy.DEFAULTS[key] is True
        with pytest.raises(ValueError):
            policy.validate({key: 'true'})
    group = next(g for g in result['layout'] if g['title'] == 'Notification Preferences')
    assert {p['property'] for p in group['items']} == {k for k in policy.SCHEMA if k.startswith('attention_')} | {'unanswered_days', 'notifications'}
    schema = result['schema']['properties']
    assert schema['notifications']['title'] == 'Push notifications and email'
    assert schema['notifications']['enum'] == ['only surfaced activity', 'all messages from my contacts', 'no notifications or emails']
    assert result['values']['notifications'] == 'only surfaced activity'
