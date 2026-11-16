"""The app gets schemas with one catalog read; model catalog stays unchanged."""
import json
import threading
from unittest.mock import Mock

from fulcra_api import connections

from fulcra_mcp import contact_catalog, tools


async def test_contact_catalog_loads_schemas_concurrently_from_one_snapshot(monkeypatch):
    method = getattr(contact_catalog, 'get_agent_contact_catalog', None)
    assert method is not None, 'The panel needs a bulk contact catalog'
    api = Mock()
    ids = ['Event/00000000-0000-0000-0000-000000000001', 'Event/00000000-0000-0000-0000-000000000002']
    api.v1_catalog.return_value = [
        {'id': id, 'name': 'Ordinary name', 'description': 'Ordinary description', 'fulcra_userid': owner,
         'categories': ['shared_type'] if owner == 'peer' else []}
        for id, owner in zip(ids, ['me', 'peer'])
    ]
    api.v1_catalog.return_value.append(api.v1_catalog.return_value[0].copy())
    barrier = threading.Barrier(2)
    loop_thread = threading.get_ident()

    def schema(id, version, fulcra_userid=None):
        assert threading.get_ident() != loop_thread
        assert fulcra_userid == ('me' if id == ids[0] else 'peer')
        barrier.wait(timeout=1)
        return connections.CHANNEL_FIELDS

    api.v1_catalog_schema.side_effect = schema
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    result = await method()
    entries = next(iter(json.loads(result.split(': ', 1)[1]).values()))
    assert [e['id'] for e in entries] == ids
    assert entries[1]['fulcra_userid'] == 'peer'
    assert all('body' in e['fields'] for e in entries)
    api.v1_catalog.assert_called_once_with()
    assert api.v1_catalog_schema.call_count == 2


async def test_unavailable_schema_does_not_discard_healthy_contacts(monkeypatch):
    from urllib.error import HTTPError
    api = Mock()
    api.v1_catalog.return_value = [{'id': 'Event/healthy'}, {'id': 'Event/gone'}]
    def schema(id, *args, **kwargs):
        if id == 'Event/gone':
            raise HTTPError('https://example.invalid', 404, 'Gone', {}, None)
        return connections.CHANNEL_FIELDS
    api.v1_catalog_schema.side_effect = schema
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    entries = next(iter(json.loads((await contact_catalog.get_agent_contact_catalog()).split(': ', 1)[1]).values()))
    assert 'body' in entries[0]['fields']
    assert entries[1]['schema_error'] is True
    assert 'fields' not in entries[1]


async def test_bulk_catalog_is_app_only_on_each_endpoint():
    from fastmcp import Client
    from fulcra_mcp.endpoint import create_server
    from fulcra_mcp.openai_endpoint import create_openai_server
    from fulcra_mcp.claude_endpoint import create_claude_server
    for factory in (create_server, create_openai_server, create_claude_server):
        async with Client(factory()) as client:
            inventory = {tool.name: tool for tool in await client.list_tools()}
            assert 'get_agent_contact_catalog' in inventory
            assert inventory['get_agent_contact_catalog'].meta['ui']['visibility'] == ['app']
