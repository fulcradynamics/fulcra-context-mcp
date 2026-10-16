"""Renamed protocol discovery preserves existing data and safety checks."""
import json

import pytest
from fastmcp import Client
from fulcra_mcp.main import mcp
from fulcra_mcp import tools
from test_mentions import backend, entry


@pytest.mark.parametrize('prefix', ['connect-agents-with-anyone', 'connect-our-agents'])
async def test_search_and_catalog_preserve_both_channel_prefixes(fake_fulcra, prefix):
    backend(fake_fulcra, [entry('a', 'peer')])
    description = f'{prefix} channel\nconverted_from_mesh: []\n[mesh_identifier: "Test"]'
    fake_fulcra.v1_catalog.return_value[0]['description'] = description
    fake_fulcra.get_shared_datasets.return_value[0]['datashare_name'] = f'{prefix}: test'
    async with Client(mcp) as client:
        result = await client.call_tool('agent_contacts_search', {'query': 'Test'})
        assert len(result.structured_content['items']) == 2
        opened = await client.call_tool('agent_contact_open', {'peer_fulcra_userid': 'peer'})
        assert opened.structured_content['peer_fulcra_userid'] == 'peer'
        catalog = json.loads((await tools.get_data_catalog()).removeprefix('Available data types, grouped by compatible tool: '))
        channel = next(e for entries in catalog.values() for e in entries if e['id'] == 'Event/a')
        assert channel['description'] == description
        assert channel['fields']
        fake_fulcra.get_shared_datasets.return_value = []
        result = await client.call_tool('agent_contacts_search', {'query': 'Test'})
        assert len(result.structured_content['items']) == 1
