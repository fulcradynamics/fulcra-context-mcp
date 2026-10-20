"""The app is served by the real server without touching account data."""

from fastmcp import Client

from fulcra_mcp import server_info
from fulcra_mcp.main import mcp


async def test_app_tools_advertise_navigation_icons():
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        for name in ("fulcra_open", "agent_contact_open"):
            assert tools[name].icons == server_info.icons()


async def test_direct_contacts_resource_contract():
    async with Client(mcp) as client:
        direct = (await client.read_resource("ui://fulcra/contacts/thread/v67.html?startup=resource"))[0]
        normal = (await client.read_resource("ui://fulcra/contacts/thread/v67.html"))[0]
        assert direct.mimeType == "text/html;profile=mcp-app"
        assert direct.meta["openai/ui"] == {"preferredDisplayMode": "fullscreen", "availableDisplayModes": ["fullscreen"]}
        assert direct.text == normal.text.replace('</head>', '<meta name="connection-startup" content="resource"></head>', 1)
        assert '<meta name="connection-startup"' not in normal.text


async def test_single_full_panel_opener():
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        tool = tools['agent_contact_open']
        result = await client.call_tool(tool.name, {})
        assert result.data == {'presentation': 'thread', 'peer_fulcra_userid': None}
        resource = (await client.read_resource(tool.meta['ui']['resourceUri']))[0]
        assert resource.meta['openai/ui'] == {
            'preferredDisplayMode': 'fullscreen', 'availableDisplayModes': ['fullscreen']}


async def test_thread_entrypoint():
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        tool = tools["agent_contact_open"]
        assert tool.title == "Agent Contacts"
        assert tool.meta["ui"]["resourceUri"] == "ui://fulcra/contacts/thread/v67.html"
        assert tool.meta["ui"]["visibility"] == ["model", "app"]
        assert tool.meta["openai/ui"]["entrypoints"] == [{"type": "thread"}]
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert not tool.inputSchema.get("required")
        for args in [{}, {"peer_fulcra_userid": "exact-peer"}, {"peer_fulcra_userid": " unknown "}]:
            result = await client.call_tool("agent_contact_open", args)
            assert result.data == {"presentation": "thread", "peer_fulcra_userid": args.get("peer_fulcra_userid")}
        import pytest
        for invalid in ["", "   ", 123, ["peer"]]:
            with pytest.raises(Exception):
                await client.call_tool("agent_contact_open", {"peer_fulcra_userid": invalid})
        resource = await client.read_resource(tool.meta["ui"]["resourceUri"])
        assert '<meta name="connection-presentation" content="thread">' in resource[0].text


async def test_contacts_app():
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        assert "fulcra_open" in tools
        tool = tools["fulcra_open"]
        assert tool.meta["openai/ui"]["entrypoints"] == [{"type": "global"}]
        assert tool.title == "Agents I Know"
        assert tool.meta["ui"]["resourceUri"] == "ui://fulcra/contacts/v67.html"
        assert tool.meta["ui"]["visibility"] == ["app"]
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.openWorldHint is False
        result = await client.call_tool("fulcra_open", {})
        assert not result.is_error
        assert result.data == {"message": "Agents I Know is ready."}
        resources = await client.read_resource("ui://fulcra/contacts/v67.html")
        assert resources[0].mimeType == "text/html;profile=mcp-app"
        assert "<h1>Agents I Know</h1>" in resources[0].text
        assert "data:font/woff2;base64," in resources[0].text
        assert "SIL OPEN FONT LICENSE" in resources[0].text
        assert "Invite someone’s agent</button>" in resources[0].text
        assert "connect-agents-with-anyone" in resources[0].text
        assert 'id="connection-status"' in resources[0].text
        assert 'id="connection-detail"' in resources[0].text
        assert 'id="connection-retry"' in resources[0].text
        assert 'bubble-body' in resources[0].text
        assert 'thread-time' in resources[0].text
        assert 'unread-dot' in resources[0].text
        assert 'prefers-reduced-motion' in resources[0].text
        assert 'id="message-loading"' in resources[0].text
        assert resources[0].text.index('id="message-area"') < resources[0].text.index('id="message-loading"') < resources[0].text.index('id="messages"')
        assert 'No messages with ' in resources[0].text
        assert resources[0].text.index('id="messages"') < resources[0].text.index('Load more history</button>') < resources[0].text.index('id="thread-composer"')
        assert 'get_records' in resources[0].text
        assert '<meta name="connection-presentation" content="global">' in resources[0].text
        thread_resource = await client.read_resource("ui://fulcra/contacts/thread/v67.html")
        assert thread_resource[0].text == resources[0].text.replace(
            '<meta name="connection-presentation" content="global">',
            '<meta name="connection-presentation" content="thread">', 1)
        assert 'Continue in ' in resources[0].text
        assert resources[0].text.count('id="thread-composer"') == 1
        assert 'peer_fulcra_userid' in resources[0].text
        assert 'omitted_records' in resources[0].text
        assert 'Context clipped' in resources[0].text
        assert "get_data_catalog" in resources[0].text
        assert "list_shares" in resources[0].text
        assert "Incoming" in resources[0].text
        assert "Outgoing" in resources[0].text
        assert "Conversation incomplete" in resources[0].text
        assert resources[0].meta["openai/ui"]["preferredDisplayMode"] == "fullscreen"
        assert resources[0].meta["openai/ui"]["availableDisplayModes"] == ["fullscreen"]
        assert 'agent_connection_send' in resources[0].text
        assert "get_data_catalog" in tools  # Existing tools remain mounted.


async def test_contacts_controls_default_full_and_chat_by_env(monkeypatch):
    from fulcra_mcp.settings import settings
    uris = ("ui://fulcra/contacts/v67.html", "ui://fulcra/contacts/thread/v67.html",
            "ui://fulcra/contacts/thread/v67.html?startup=resource")
    async with Client(mcp) as client:
        for uri in uris:
            text = (await client.read_resource(uri))[0].text
            assert '<meta name="connection-controls" content="full">' in text
        monkeypatch.setattr(settings, "fulcra_contacts_controls", "chat")
        for uri in uris:
            text = (await client.read_resource(uri))[0].text
            assert '<meta name="connection-controls" content="chat">' in text
