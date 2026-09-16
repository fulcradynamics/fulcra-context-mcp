"""The MCP endpoint must not depend on server-side session state.

Cloud Run replaces the instance on every deploy (and, before the leak fix,
every day or two on its own); with stateful sessions every connected client
then got ``404 Session not found``. See docs/disconnect-diagnosis.md.
"""

import time
from contextlib import asynccontextmanager

import httpx
import pytest
from mcp.server.auth.provider import AccessToken

from fulcra_mcp.main import app, oauth_provider
from fulcra_mcp.provider import OIDC_SCOPES
from fulcra_mcp.settings import settings

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
TOOLS_LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}


@asynccontextmanager
async def mcp_client(tmp_path):
    previous_state_path = settings.state_path
    settings.state_path = tmp_path
    oauth_provider.tokens["mcp_test"] = AccessToken(
        token="mcp_test",
        client_id="c",
        scopes=OIDC_SCOPES,
        expires_at=int(time.time()) + 3600,
    )
    transport = httpx.ASGITransport(app=app)
    try:
        # httpx does not run the ASGI lifespan, which is what starts the
        # session manager. Enter and exit it in the same task (not a fixture).
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                headers={"Authorization": "Bearer mcp_test", **MCP_HEADERS},
            ) as client,
        ):
            yield client
    finally:
        oauth_provider.tokens.pop("mcp_test", None)
        settings.state_path = previous_state_path


@pytest.mark.parametrize("path", ["/", "/mcp"])
async def test_requests_are_self_contained(tmp_path, path):
    async with mcp_client(tmp_path) as http_client:
        init = await http_client.post(path, json=INITIALIZE)
        assert init.status_code == 200
        assert "mcp-session-id" not in init.headers

        # No session id, no prior initialize on "this session": still served.
        listed = await http_client.post(path, json=TOOLS_LIST)
        assert listed.status_code == 200
        assert '"tools"' in listed.text

        # A stale session id from a previous instance is ignored, not a 404.
        stale = await http_client.post(
            path, json=TOOLS_LIST, headers={"mcp-session-id": "deadbeef" * 4}
        )
        assert stale.status_code == 200


async def test_server_initiated_stream_is_unsupported(tmp_path):
    async with mcp_client(tmp_path) as http_client:
        response = await http_client.get(
            "/mcp", headers={"Accept": "text/event-stream"}
        )
        assert response.status_code == 405


async def test_well_known_routes_coexist(tmp_path):
    """The Glama manifest is an exact-path route in front of the "/" mount; it
    must not shadow the OAuth discovery documents that share the prefix."""
    async with mcp_client(tmp_path) as http_client:
        glama = await http_client.get("/.well-known/glama.json")
        assert glama.status_code == 200
        assert "claim" in glama.json()

        auth_server = await http_client.get("/.well-known/oauth-authorization-server")
        assert auth_server.status_code == 200
        assert "issuer" in auth_server.json()

        resource = await http_client.get("/.well-known/oauth-protected-resource")
        assert resource.status_code == 200
        assert "resource" in resource.json()
