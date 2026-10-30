"""Native tool workflows and endpoint contract isolation."""
import json
from pathlib import Path

import pytest
from fastmcp import Client
from fulcra_mcp.main import mcp, openai_mcp


async def contract(server):
    async with Client(server) as client:
        return {
            'instructions': client.initialize_result.instructions,
            'tools': [t.model_dump(mode='json', exclude_none=True) for t in await client.list_tools()],
            'resources': [r.model_dump(mode='json', exclude_none=True) for r in await client.list_resources()],
        }


async def test_openai_contract_unchanged():
    assert await contract(openai_mcp) == json.loads(
        Path(__file__).with_name('openai_contract.json').read_text())


async def test_generic_native_discovery():
    async with Client(mcp) as client:
        tools = await client.list_tools()
        names = [t.name for t in tools]
        assert len(names) == len(set(names))
        assert 'accept_agent_invitation' in names
        match = next(t for t in tools if t.name == 'match_agent_invitations')
        assert 'model' in match.meta['ui']['visibility']
        assert 'set-up-agent-contacts' not in client.initialize_result.instructions
        assert 'open_agent_contacts' not in names
        result = await client.call_tool('open_agent_contacts', {})
        assert result.data['status'] == 'unsupported_host'
        assert 'list_shares' in result.data['next_step']


async def test_capable_host_retains_resources_and_openai_is_isolated(app_capabilities, monkeypatch, caplog):
    from fulcra_mcp import tools
    from fulcra_mcp.apps import THREAD_UI_URI
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: pytest.fail('UI opening must not access accounts'))
    async with Client(mcp) as client:
        names = [t.name for t in await client.list_tools()]
        assert names.count('create_agent_invitation') == 1
        assert names.count('match_agent_invitations') == 1
        assert 'open_agent_contacts' in names
        result = await client.call_tool('open_agent_contacts', {})
        assert result.data['presentation'] == 'thread'
        assert 'text/html;profile=mcp-app' == (await client.read_resource(THREAD_UI_URI))[0].mimeType
    assert 'Duplicate list_tools' not in caplog.text
    await test_openai_contract_unchanged()


@pytest.mark.parametrize('path', ['/mcp', '/openai/mcp'])
async def test_real_fastmcp_http_endpoint_discovery_and_call(tmp_path, path, monkeypatch, app_capabilities):
    import httpx
    from fastmcp.client.transports import StreamableHttpTransport
    from fulcra_mcp.main import app
    from fulcra_mcp import tools
    from test_native_lifecycle import Account, OWN, PEER
    from test_stateless import mcp_client
    api = Account(OWN, {})
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), **kwargs)
    async with mcp_client(tmp_path):
        transport = StreamableHttpTransport('http://testserver' + path,
            headers={'Authorization': 'Bearer mcp_test'}, httpx_client_factory=factory)
        async with Client(transport) as client:
            names = [tool.name for tool in await client.list_tools()]
            assert ('accept_agent_invitation' in names) == (path == '/mcp')
            assert len(names) == len(set(names))
            result = await client.call_tool('create_agent_invitation',
                dict(inviter_name='Alex', recipient_name='Sura', recipient_userid=PEER))
            assert result.data['status'] == 'prepared'
            assert ('invitation_text' in result.data) == (path == '/mcp')
            assert not api.rows
            opened = await client.call_tool('open_agent_contacts', {})
            if path == '/mcp':
                assert opened.data['status'] == 'unsupported_host'
            else:
                assert opened.data['presentation'] == 'thread'
