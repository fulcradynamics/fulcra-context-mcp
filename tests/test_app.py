"""The app is served by the real server without touching account data."""

from fastmcp import Client

from fulcra_mcp.main import mcp


async def test_hello_app():
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        assert "aicq_open" in tools
        tool = tools["aicq_open"]
        assert tool.meta["openai/ui"]["entrypoints"] == [{"type": "global"}]
        assert tool.meta["ui"]["resourceUri"] == "ui://aicq/hello/v4.html"
        assert tool.meta["ui"]["visibility"] == ["app"]
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.openWorldHint is False
        result = await client.call_tool("aicq_open", {})
        assert not result.is_error
        assert result.data == {"message": "Hello world"}
        resources = await client.read_resource("ui://aicq/hello/v4.html")
        assert resources[0].mimeType == "text/html;profile=mcp-app"
        assert "<h1>Hello world</h1>" in resources[0].text
        assert "Invite someone</button>" in resources[0].text
        assert "fulcra-mesh" in resources[0].text
        assert 'id="mesh-status"' in resources[0].text
        assert 'id="mesh-detail"' in resources[0].text
        assert 'get_records' in resources[0].text
        assert "get_data_catalog" in resources[0].text
        assert resources[0].meta["openai/ui"]["preferredDisplayMode"] == "fullscreen"
        assert resources[0].meta["openai/ui"]["availableDisplayModes"] == ["fullscreen"]
        assert "get_data_catalog" in tools  # Existing tools remain mounted.
