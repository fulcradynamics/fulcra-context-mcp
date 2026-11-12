"""Default tool workflows and endpoint contract isolation."""
import json
from pathlib import Path

import pytest
from fastmcp import Client
from fulcra_mcp.main import mcp, openai_mcp


async def contract(server):
    async with Client(server) as client:
        return {
            'instructions': client.instructions,
            'tools': [t.model_dump(mode='json', by_alias=True, exclude_none=True) for t in await client.list_tools()],
            'resources': [r.model_dump(mode='json', by_alias=True, exclude_none=True) for r in await client.list_resources()],
        }


async def test_openai_contract_unchanged():
    assert await contract(openai_mcp) == json.loads(
        Path(__file__).with_name('openai_contract.json').read_text())


@pytest.mark.parametrize('openai_first', [False, True])
async def test_fresh_factories_keep_endpoint_contracts_isolated(openai_first):
    from fulcra_mcp.endpoint import create_server
    from fulcra_mcp.openai_endpoint import create_openai_server

    factories = [(create_server, mcp), (create_openai_server, openai_mcp)]
    if openai_first:
        factories.reverse()
    for factory, mounted in factories * 2:
        assert await contract(factory()) == await contract(mounted)


@pytest.mark.parametrize('servers', [(mcp, openai_mcp), (openai_mcp, mcp)])
async def test_share_description_is_endpoint_local(servers, monkeypatch):
    from unittest.mock import Mock
    from fulcra_mcp import tools

    baseline = next(t for t in json.loads(
        Path(__file__).with_name('openai_contract.json').read_text())['tools']
        if t['name'] == 'create_share')
    generic_description = (
        "Share files or data types from this account with other Fulcra users (read-only).\n\n"
        "Recipients read them by passing this user's ID as `fulcra_userid` to the\n"
        "file and data tools; this share does not let them write to this account.\n"
        "Only share what the user authorized."
    )
    api = Mock()
    api.create_datashare.return_value = {'datashare': {'datashare_id': 'test-share'}}
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    results = []
    # Repeat discovery after both endpoints have listed and invoked the tool.
    for server in (*servers, *servers, tools.tools_mcp):
        async with Client(server) as client:
            share = next(t for t in await client.list_tools() if t.name == 'create_share')
            actual = share.model_dump(mode='json', by_alias=True, exclude_none=True)
            assert actual.pop('description') == (
                baseline['description'] if server is openai_mcp else generic_description)
            assert actual == {k: v for k, v in baseline.items() if k != 'description'}
            result = await client.call_tool('create_share', {
                'name': 'Authorized folder', 'with_user_ids': ['recipient'],
                'file_paths': ['/shared/topic/'],
            })
            results.append(result.content)
            api.create_datashare.assert_called_once_with(
                datashare_name='Authorized folder',
                fulcra_data_types=['file:/shared/topic/'],
                allowed_user_ids=['recipient'], allowed_group_ids=None,
                share_all_data=False, time_start=None, time_end=None,
            )
            api.reset_mock()
    assert all(result == results[0] for result in results)


async def test_standard_provider_invitation_contract():
    from fulcra_mcp.tools import tools_mcp

    names = {'create_agent_invitation', 'accept_agent_invitation', 'match_agent_invitations'}
    async with Client(tools_mcp) as client:
        standard = [t.model_dump(mode='json', by_alias=True, exclude_none=True)
                    for t in await client.list_tools() if t.name in names]
    expected = [t for t in (await contract(mcp))['tools'] if t['name'] in names]
    assert {t['name'] for t in standard} == names
    assert {t['name']: t for t in standard} == {t['name']: t for t in expected}


async def test_openai_excludes_direct_acceptance(monkeypatch):
    from fulcra_mcp import tools

    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: pytest.fail('Excluded tool accessed account'))
    async with Client(openai_mcp) as client:
        result = await client.call_tool('accept_agent_invitation', {
            'inviter_userid': '00000000-0000-4000-8000-000000000001',
            'topic': 'handshake ' + 'a' * 32, 'sender': 'Agent', 'introduction': 'Approved',
        }, raise_on_error=False)
    assert result.is_error
    assert 'Unknown tool' in result.content[0].text


async def test_standard_provider_prepares_ready_to_share_invitation(monkeypatch):
    from fulcra_mcp import tools
    from test_invitation_lifecycle import Account, OWN, PEER

    api = Account(OWN, {})
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    async with Client(tools.tools_mcp) as client:
        result = await client.call_tool('create_agent_invitation', {
            'inviter_name': 'Alex', 'recipient_name': 'Sura', 'recipient_userid': PEER,
        })
    invite = result.data
    assert invite['prepared'] and invite['shared']
    assert not invite['sent'] and not invite['connected']
    assert {OWN, invite['data_type'], invite['code']} <= set(invite['invitation_text'].split())
    assert invite['delivery']['body'] == invite['invitation_text']
    assert not api.rows


async def test_default_endpoint_discovery():
    async with Client(mcp) as client:
        tools = await client.list_tools()
        names = [t.name for t in tools]
        assert len(names) == len(set(names))
        assert 'accept_agent_invitation' in names
        match = next(t for t in tools if t.name == 'match_agent_invitations')
        assert 'model' in match.meta['ui']['visibility']
        assert 'set-up-agent-contacts' not in client.instructions
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
        assert 'text/html;profile=mcp-app' == (await client.read_resource(THREAD_UI_URI))[0].mime_type
    assert 'Duplicate list_tools' not in caplog.text
    await test_openai_contract_unchanged()


# Handshake-era hosts declare MCP Apps support only at `initialize`, which stateless
# HTTP can't see on later calls, so /mcp gates the panel. Sessionless-era clients
# declare capabilities on every request, so the gate sees them and opens it.
@pytest.mark.parametrize('mode', ['legacy', 'auto'])
@pytest.mark.parametrize('path', ['/mcp', '/openai/mcp'])
async def test_real_fastmcp_http_endpoint_discovery_and_call(tmp_path, path, mode, monkeypatch, app_capabilities):
    import httpx2
    from fastmcp.client.transports import StreamableHttpTransport
    from fulcra_mcp.main import app
    from fulcra_mcp import tools
    from test_invitation_lifecycle import Account, OWN, PEER
    from test_stateless import mcp_client
    api = Account(OWN, {})
    monkeypatch.setattr(tools, 'get_fulcra_object', lambda: api)
    def factory(**kwargs):
        return httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), **kwargs)
    async with mcp_client(tmp_path):
        transport = StreamableHttpTransport('http://testserver' + path,
            headers={'Authorization': 'Bearer mcp_test'}, httpx_client_factory=factory)
        async with Client(transport, mode=mode) as client:
            names = [tool.name for tool in await client.list_tools()]
            assert ('accept_agent_invitation' in names) == (path == '/mcp')
            assert len(names) == len(set(names))
            result = await client.call_tool('create_agent_invitation',
                dict(inviter_name='Alex', recipient_name='Sura', recipient_userid=PEER))
            assert result.data['status'] == 'prepared'
            assert ('invitation_text' in result.data) == (path == '/mcp')
            assert not api.rows
            opened = await client.call_tool('open_agent_contacts', {})
            if path == '/mcp' and mode == 'legacy':
                assert opened.data['status'] == 'unsupported_host'
            else:
                assert opened.data['presentation'] == 'thread'
