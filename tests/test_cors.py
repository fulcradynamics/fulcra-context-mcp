"""CORS regression tests for browser-based MCP clients.

Browser clients (claude.ai web, MCP Inspector) send an OPTIONS preflight before
every cross-origin request. These previously 405'd because nothing handled
OPTIONS, which blocked all browser MCP traffic while the connector still showed
"active". See docs/auth-state-and-routing-plan.md (finding R9).
"""

import httpx
import pytest

from fulcra_mcp.main import app

ORIGIN = "https://claude.ai"

PREFLIGHT_HEADERS = {
    "Origin": ORIGIN,
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "authorization,content-type,mcp-session-id",
}


@pytest.fixture
async def http_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client


# The connector checker probes all three forms of the endpoint path.
@pytest.mark.parametrize("path", ["/", "/mcp", "/mcp/"])
async def test_preflight_allows_mcp_post(http_client, path):
    response = await http_client.options(path, headers=PREFLIGHT_HEADERS)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"
    allowed_methods = response.headers.get("access-control-allow-methods", "")
    assert "POST" in allowed_methods
    allowed_headers = response.headers.get("access-control-allow-headers", "").lower()
    assert "authorization" in allowed_headers
    assert "mcp-session-id" in allowed_headers


async def test_actual_request_carries_cors_headers(http_client):
    # Any cross-origin response must carry allow-origin for the browser to
    # surface it; the metadata endpoint is reachable unauthenticated.
    response = await http_client.get(
        "/.well-known/oauth-protected-resource", headers={"Origin": ORIGIN}
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"


async def test_session_id_exposed_to_browser_js(http_client):
    # The initialize response's mcp-session-id header is unreadable from
    # browser JS unless exposed via CORS.
    response = await http_client.options("/mcp/", headers=PREFLIGHT_HEADERS)
    # Preflight itself doesn't carry expose-headers; verify on a real response.
    response = await http_client.get(
        "/.well-known/oauth-protected-resource", headers={"Origin": ORIGIN}
    )
    exposed = response.headers.get("access-control-expose-headers", "").lower()
    assert "mcp-session-id" in exposed
