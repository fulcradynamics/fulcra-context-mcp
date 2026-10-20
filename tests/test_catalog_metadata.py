"""Exact catalog reads expose lossless metadata for read-modify-write."""
import json

from conftest import FAKE_USER_ID


async def test_exact_catalog_metadata_roundtrip(call, fake_fulcra):
    entry = {
        'id': 'Event/df10403a-2115-4254-9e49-e48ca0af6f5d',
        'fulcra_userid': FAKE_USER_ID, 'api_version': 'v1',
        'name': 'Fulcra Agent Invitations', 'recordable': True,
        'deprecated': False, 'description': '{"version":1,"invitations":{}}',
    }
    fake_fulcra.v1_catalog.return_value = [entry]
    fake_fulcra.v1_catalog_schema.return_value = {}
    text = await call('get_data_catalog', {'data_type': entry['id'], 'fulcra_userid': FAKE_USER_ID})
    groups = json.loads(text.split(': ', 1)[1])
    row = next(iter(groups.values()))[0]
    assert row['metadata'] == {k: entry[k] for k in (
        'name', 'description', 'fulcra_userid', 'api_version', 'recordable', 'deprecated')}
    # Use the real invitation validator, not a second implementation of its schema.
    from fulcra_mcp.agent_invitations import _state
    fake_fulcra.v1_catalog.return_value = [{**entry, **row['metadata']}]
    fake_fulcra.get_datashares.return_value = []
    assert _state(fake_fulcra)[2] == {'version': 1, 'invitations': {}}
