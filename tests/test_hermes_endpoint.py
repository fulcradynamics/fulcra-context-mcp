"""/hermes/mcp, the Hermes plugin's endpoint: for now it answers exactly as /mcp does."""

from fulcra_mcp.hermes_endpoint import HERMES_MCP_PATH
from test_claude_endpoint import _result
from test_stateless import INITIALIZE, TOOLS_LIST, mcp_client


async def test_hermes_endpoint_matches_mcp(tmp_path):
    async with mcp_client(tmp_path) as client:
        for request in (INITIALIZE, TOOLS_LIST):
            standard = _result(await client.post("/mcp", json=request))
            hermes = _result(await client.post(HERMES_MCP_PATH, json=request))
            assert hermes == standard
