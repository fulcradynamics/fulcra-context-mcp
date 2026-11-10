"""The /claude/mcp endpoint, shared by Claude's directory connector and plugin:
the native invitation tools and instructions plus Claude's guidance, contact
openers always listed, and the deprecated health/location tools hidden. Same
OAuth and RFC 9728 path-form discovery."""

import json

import httpx
import pytest

from fulcra_mcp.claude_endpoint import CLAUDE_HIDDEN_TOOLS, CLAUDE_MCP_PATH
from fulcra_mcp.endpoint import APP_OPENERS, INSTRUCTIONS
from fulcra_mcp.main import app
from fulcra_mcp.openai_endpoint import OPENAI_MCP_PATH
from test_stateless import INITIALIZE, TOOLS_LIST, mcp_client


def _result(response: httpx.Response) -> dict:
    return next(
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    )["result"]


def _tools(response: httpx.Response) -> dict[str, dict]:
    return {tool["name"]: tool for tool in _result(response)["tools"]}


async def test_claude_endpoint_tools(tmp_path):
    async with mcp_client(tmp_path) as client:
        native = set(_tools(await client.post("/mcp", json=TOOLS_LIST)))
        openai = set(_tools(await client.post(OPENAI_MCP_PATH, json=TOOLS_LIST)))
        claude = _tools(await client.post(CLAUDE_MCP_PATH, json=TOOLS_LIST))

    assert CLAUDE_HIDDEN_TOOLS <= native
    # /mcp hides the openers on stateless HTTP; Claude always lists them.
    assert set(claude) == (native - CLAUDE_HIDDEN_TOOLS) | APP_OPENERS
    assert set(claude) == openai | {'accept_agent_invitation'}
    for name in ('create_agent_invitation', 'accept_agent_invitation', 'match_agent_invitations'):
        assert set(claude[name]['_meta']['ui']['visibility']) == {'model', 'app'}
    for name in ('prepare_agent_invitation', 'prepare_standing_agent_invitation'):
        assert claude[name]['_meta']['ui']['visibility'] == ['app']


async def test_claude_endpoint_lists_invitations_first(tmp_path):
    invitations = ['create_agent_invitation', 'accept_agent_invitation', 'match_agent_invitations']
    async with mcp_client(tmp_path) as client:
        for path in ("/mcp", CLAUDE_MCP_PATH):
            names = [tool["name"] for tool in _result(await client.post(path, json=TOOLS_LIST))["tools"]]
            assert names[:3] == invitations, path


async def test_claude_endpoint_instructions(tmp_path):
    async with mcp_client(tmp_path) as client:
        result = _result(await client.post(CLAUDE_MCP_PATH, json=INITIALIZE))
    instructions = result["instructions"]
    # Usable without the plugin: the generic workflow plus Claude's guidance.
    assert instructions.startswith(INSTRUCTIONS)
    assert "set-up-agent-contacts skill" in instructions
    assert "open_agent_contacts({})" in instructions


async def test_claude_endpoint_opens_contacts_without_app_capability(tmp_path):
    call = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "open_agent_contacts", "arguments": {}},
    }
    async with mcp_client(tmp_path) as client:
        generic = await client.post("/mcp", json=call)
        claude = await client.post(CLAUDE_MCP_PATH, json=call)
    assert "unsupported_host" in generic.text
    assert "unsupported_host" not in claude.text
    assert _result(claude).get("isError") is not True


async def test_claude_endpoint_refuses_hidden_tool_calls(tmp_path):
    call = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "get_location", "arguments": {}},
    }
    async with mcp_client(tmp_path) as client:
        response = await client.post(CLAUDE_MCP_PATH, json=call)
    assert "Unknown tool" in response.text


@pytest.mark.parametrize("path", [CLAUDE_MCP_PATH, f"{CLAUDE_MCP_PATH}/"])
async def test_claude_endpoint_requires_auth(path):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(path, json=TOOLS_LIST)
    assert response.status_code == 401
    # Its own path-form document, whose resource is the URL Claude connected to.
    challenge = response.headers["www-authenticate"]
    assert f'/.well-known/oauth-protected-resource{CLAUDE_MCP_PATH}"' in challenge


@pytest.mark.parametrize("path", [CLAUDE_MCP_PATH, f"{CLAUDE_MCP_PATH}/"])
async def test_claude_endpoint_preflight(path):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.options(
            path,
            headers={
                "Origin": "https://claude.ai",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"


async def test_claude_path_form_protected_resource_metadata():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        root = (await client.get("/.well-known/oauth-protected-resource")).json()
        response = await client.get(f"/.well-known/oauth-protected-resource{CLAUDE_MCP_PATH}")
    assert response.status_code == 200
    doc = response.json()
    assert doc["resource"] == root["resource"].rstrip("/") + CLAUDE_MCP_PATH
    assert doc["authorization_servers"] == root["authorization_servers"]
    assert doc["scopes_supported"] == root["scopes_supported"]
