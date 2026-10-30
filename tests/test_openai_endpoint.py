"""OpenAI keeps the plugin contract and its own RFC 9728 path-form discovery;
 generic tools have endpoint-local invitation and app-support behavior."""

import json

import httpx
import pytest

from fulcra_mcp.main import app
from fulcra_mcp.openai_endpoint import OPENAI_HIDDEN_TOOLS, OPENAI_MCP_PATH
from test_stateless import INITIALIZE, TOOLS_LIST, mcp_client


def _tool_names(response: httpx.Response) -> set[str]:
    data = next(
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    )
    return {tool["name"] for tool in data["result"]["tools"]}


async def test_openai_endpoint_hides_health_and_location_tools(tmp_path):
    async with mcp_client(tmp_path) as client:
        full = _tool_names(await client.post("/mcp", json=TOOLS_LIST))
        assert (await client.post(OPENAI_MCP_PATH, json=INITIALIZE)).status_code == 200
        openai = _tool_names(await client.post(OPENAI_MCP_PATH, json=TOOLS_LIST))

    assert OPENAI_HIDDEN_TOOLS <= full
    assert openai == (full - OPENAI_HIDDEN_TOOLS - {'accept_agent_invitation'}) | {'open_agent_contacts', 'open_agent_contacts_home'}
    assert {"get_records", "get_data_catalog"} <= openai


@pytest.mark.parametrize("path", ["/mcp", OPENAI_MCP_PATH])
async def test_single_person_invitation_discovery(tmp_path, path):
    async with mcp_client(tmp_path) as client:
        await client.post(path, json=INITIALIZE)
        response = await client.post(path, json=TOOLS_LIST)
    data = next(json.loads(line.removeprefix("data: "))
                for line in response.text.splitlines() if line.startswith("data: "))
    tools = {tool['name']: tool for tool in data['result']['tools']}
    invitation = tools['create_agent_invitation']
    assert invitation['description'].startswith(
        'Create a Fulcra invitation the user can share with another person to connect their agents.')
    assert 'Always creates a new outbox' not in invitation['description']
    assert 'shares only the invitation outbox with that user immediately' in (
        invitation['inputSchema']['properties']['recipient_userid']['description'])
    assert set(invitation['_meta']['ui']['visibility']) == {'model', 'app'}
    assert invitation['annotations']['readOnlyHint'] is False
    assert invitation['annotations']['destructiveHint'] is True
    assert invitation['annotations']['openWorldHint'] is True
    schema = invitation['inputSchema']
    assert set(schema['properties']) == {'inviter_name', 'recipient_name', 'recipient_userid'}
    assert set(schema['required']) == {'inviter_name', 'recipient_name'}
    for name in ('prepare_agent_invitation', 'prepare_standing_agent_invitation', 'match_agent_invitations'):
        expected = ['model', 'app'] if path == '/mcp' and name == 'match_agent_invitations' else ['app']
        assert tools[name]['_meta']['ui']['visibility'] == expected


async def test_openai_endpoint_refuses_hidden_tool_calls(tmp_path):
    call = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "get_location", "arguments": {}},
    }
    async with mcp_client(tmp_path) as client:
        response = await client.post(OPENAI_MCP_PATH, json=call)
    assert "Unknown tool" in response.text


async def test_openai_endpoint_requires_auth():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(OPENAI_MCP_PATH, json=TOOLS_LIST)
    assert response.status_code == 401
    assert "resource_metadata=" in response.headers["www-authenticate"]


@pytest.mark.parametrize("path", [OPENAI_MCP_PATH, f"{OPENAI_MCP_PATH}/"])
async def test_openai_endpoint_preflight(path):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.options(
            path,
            headers={
                "Origin": "https://chatgpt.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"


async def test_openai_path_form_protected_resource_metadata():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        root = (await client.get("/.well-known/oauth-protected-resource")).json()
        response = await client.get(f"/.well-known/oauth-protected-resource{OPENAI_MCP_PATH}")
    assert response.status_code == 200
    doc = response.json()
    assert doc["resource"] == root["resource"].rstrip("/") + OPENAI_MCP_PATH
    assert doc["authorization_servers"] == root["authorization_servers"]
    assert doc["scopes_supported"] == root["scopes_supported"]
