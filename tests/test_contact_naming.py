"""Public names change without migrating stored connection metadata."""
from fastmcp import Client

from fulcra_mcp.main import mcp


async def test_contact_tool_names_and_titles():
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    assert tools['fulcra_open'].title == 'Agents I Know'
    assert tools['agent_contacts_open'].title == 'Agents I Know'
    assert tools['agent_contact_open'].title == 'Agent Contacts'
    assert 'Open an Agent Contact' in tools['agent_contact_open'].description
    assert {'agent_connection_send', 'set_contact_identifier', 'fulcra_settings_read',
            'fulcra_settings_update', 'fulcra_check_status', 'agent_contacts_search'} <= tools.keys()
    assert not any('mesh' in name or 'aicq' in name for name in tools)


async def test_contact_resources_and_bundle():
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        uri = tools['fulcra_open'].meta['ui']['resourceUri']
        assert uri == 'ui://fulcra/contacts/v50.html'
        html = (await client.read_resource(uri))[0].text
    assert '<h1>Agents I Know</h1>' in html
    assert 'Agent Contacts' in html
    assert 'Fulcra Mesh' not in html


def test_existing_label_marker_is_not_migrated():
    from fulcra_mcp.contact_identifier import parse_contact_identifier, write_contact_identifier
    original = 'connect-agents-with-anyone channel\nconverted_from_mesh: []\n[mesh_identifier: "Trip"]'
    assert parse_contact_identifier(original) == 'Trip'
    assert write_contact_identifier(original, 'Trip') == original
    assert '[mesh_identifier:' in write_contact_identifier(original, 'New')
