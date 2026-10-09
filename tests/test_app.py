"""The app is served by the real server without touching account data."""

from fastmcp import Client

from fulcra_mcp.main import mcp


async def test_direct_meshes_resource_contract():
    async with Client(mcp) as client:
        direct = (await client.read_resource("ui://fulcra/mesh/threads/v26.html?startup=resource"))[0]
        normal = (await client.read_resource("ui://fulcra/mesh/threads/v26.html"))[0]
        assert direct.mimeType == "text/html;profile=mcp-app"
        assert direct.meta["openai/ui"] == {"preferredDisplayMode": "inline", "availableDisplayModes": ["inline", "fullscreen"]}
        assert direct.text == normal.text.replace('</head>', '<meta name="mesh-startup" content="resource"></head>', 1)
        assert '<meta name="mesh-startup"' not in normal.text


async def test_inline_threads_opener():
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        assert "mesh_threads_open" in tools
        tool = tools["mesh_threads_open"]
        assert tool.title == "Mesh threads"
        assert tool.meta["ui"] == {
            "resourceUri": "ui://fulcra/mesh/threads/v26.html",
            "visibility": ["model", "app"],
        }
        assert not tool.meta.get("openai/ui", {}).get("entrypoints")
        assert tool.inputSchema.get("properties", {}) == {}
        assert not tool.inputSchema.get("required")
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.openWorldHint is False
        result = await client.call_tool("mesh_threads_open", {})
        assert result.data == {"presentation": "threads"}
        resource = (await client.read_resource(tool.meta["ui"]["resourceUri"]))[0]
        assert resource.mimeType == "text/html;profile=mcp-app"
        assert resource.meta["openai/ui"] == {
            "preferredDisplayMode": "inline",
            "availableDisplayModes": ["inline", "fullscreen"],
        }
        global_resource = (await client.read_resource(tools["aicq_open"].meta["ui"]["resourceUri"]))[0]
        assert resource.text == global_resource.text.replace(
            '<meta name="mesh-presentation" content="global">',
            '<meta name="mesh-presentation" content="threads">', 1)


async def test_thread_entrypoint():
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        assert "mesh_conversation_open" in tools
        tool = tools["mesh_conversation_open"]
        assert tool.title == "Mesh conversation"
        assert tool.meta["ui"]["resourceUri"] == "ui://fulcra/mesh/thread/v26.html"
        assert tool.meta["ui"]["visibility"] == ["model", "app"]
        assert tool.meta["openai/ui"]["entrypoints"] == [{"type": "thread"}]
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert not tool.inputSchema.get("required")
        for args in [{}, {"peer_fulcra_userid": "exact-peer"}, {"peer_fulcra_userid": " unknown "}]:
            result = await client.call_tool("mesh_conversation_open", args)
            assert result.data == {"presentation": "thread", "peer_fulcra_userid": args.get("peer_fulcra_userid")}
        import pytest
        for invalid in ["", "   ", 123, ["peer"]]:
            with pytest.raises(Exception):
                await client.call_tool("mesh_conversation_open", {"peer_fulcra_userid": invalid})
        resource = await client.read_resource(tool.meta["ui"]["resourceUri"])
        assert '<meta name="mesh-presentation" content="thread">' in resource[0].text


async def test_mesh_app():
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        assert "aicq_open" in tools
        tool = tools["aicq_open"]
        assert tool.meta["openai/ui"]["entrypoints"] == [{"type": "global"}]
        assert tool.title == "Fulcra Mesh"
        assert tool.meta["ui"]["resourceUri"] == "ui://fulcra/mesh/v26.html"
        assert tool.meta["ui"]["visibility"] == ["app"]
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.openWorldHint is False
        result = await client.call_tool("aicq_open", {})
        assert not result.is_error
        assert result.data == {"message": "Fulcra Mesh is ready."}
        resources = await client.read_resource("ui://fulcra/mesh/v26.html")
        assert resources[0].mimeType == "text/html;profile=mcp-app"
        assert "<h1>Fulcra Mesh</h1>" in resources[0].text
        assert "hello world" not in resources[0].text.lower()
        assert "data:font/woff2;base64," in resources[0].text
        assert "SIL OPEN FONT LICENSE" in resources[0].text
        assert "Invite someone</button>" in resources[0].text
        assert "fulcra-mesh" in resources[0].text
        assert 'id="mesh-status"' in resources[0].text
        assert 'id="mesh-detail"' in resources[0].text
        assert 'Refresh threads</button>' in resources[0].text
        assert 'New activity</button>' in resources[0].text
        assert 'Latest first</option>' in resources[0].text
        assert 'Oldest first</option>' in resources[0].text
        assert 'prefers-reduced-motion' in resources[0].text
        assert 'id="refresh-status"' not in resources[0].text
        assert 'Refreshing threads and selected messages' not in resources[0].text
        assert 'Accessible messages. Reading does not send or acknowledge anything.' not in resources[0].text
        assert 'id="message-loading"' in resources[0].text
        assert resources[0].text.index('id="message-area"') < resources[0].text.index('id="message-loading"') < resources[0].text.index('id="messages"')
        assert 'No messages in this date range.' in resources[0].text
        assert resources[0].text.index('id="message-range"') < resources[0].text.index('id="thread-composer"') < resources[0].text.index('id="messages"')
        assert 'get_records' in resources[0].text
        assert '<meta name="mesh-presentation" content="global">' in resources[0].text
        thread_resource = await client.read_resource("ui://fulcra/mesh/thread/v26.html")
        assert thread_resource[0].text == resources[0].text.replace(
            '<meta name="mesh-presentation" content="global">',
            '<meta name="mesh-presentation" content="thread">', 1)
        assert 'talk with my agent about this thread' in resources[0].text
        assert resources[0].text.count('id="thread-composer"') == 1
        assert 'peer_fulcra_userid' in resources[0].text
        assert 'omitted_records' in resources[0].text
        assert 'Context clipped' in resources[0].text
        assert "get_data_catalog" in resources[0].text
        assert "list_shares" in resources[0].text
        assert "Incoming" in resources[0].text
        assert "Outgoing" in resources[0].text
        assert "Conversation incomplete" in resources[0].text
        assert "Showing selected outbox only" not in resources[0].text
        assert resources[0].meta["openai/ui"]["preferredDisplayMode"] == "fullscreen"
        assert resources[0].meta["openai/ui"]["availableDisplayModes"] == ["fullscreen", "pip"]
        assert 'mesh_send' in resources[0].text
        assert "get_data_catalog" in tools  # Existing tools remain mounted.
