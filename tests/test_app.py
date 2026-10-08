"""The app is served by the real server without touching account data."""

from fastmcp import Client

from fulcra_mcp.main import mcp


async def test_mesh_app():
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        assert "aicq_open" in tools
        tool = tools["aicq_open"]
        assert tool.meta["openai/ui"]["entrypoints"] == [{"type": "global"}]
        assert tool.title == "Fulcra Mesh"
        assert tool.meta["ui"]["resourceUri"] == "ui://fulcra/mesh/v9.html"
        assert tool.meta["ui"]["visibility"] == ["app"]
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.openWorldHint is False
        result = await client.call_tool("aicq_open", {})
        assert not result.is_error
        assert result.data == {"message": "Fulcra Mesh is ready."}
        resources = await client.read_resource("ui://fulcra/mesh/v9.html")
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
        assert resources[0].text.index('id="message-range"') < resources[0].text.index('id="thread-composer"') < resources[0].text.index('id="messages"')
        assert 'get_records' in resources[0].text
        assert 'Tell my agent' in resources[0].text
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
        assert resources[0].meta["openai/ui"]["availableDisplayModes"] == ["fullscreen"]
        assert "get_data_catalog" in tools  # Existing tools remain mounted.
