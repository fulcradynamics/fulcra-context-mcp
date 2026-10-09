"""How the HTTP app answers a request that carries no credentials at all.

A client connecting for the first time sends no Authorization header. RFC 6750
section 3.1 says that response SHOULD NOT include an error code; the client
only needs the resource metadata pointer to start sign-in. fastmcp-slim 3.4.2
answered it with error="invalid_token" and told the user to "clear
authentication tokens" they never had; 3.4.3 and later answer correctly. This
guards against a dependency pin bringing that back.
"""

import httpx
import pytest

from fulcra_mcp.main import app

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    },
}
HEADERS = {
    "content-type": "application/json",
    "accept": "application/json, text/event-stream",
}


@pytest.fixture
async def http_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client


async def test_no_credentials_gets_a_plain_challenge(http_client):
    response = await http_client.post("/mcp", json=INITIALIZE, headers=HEADERS)
    assert response.status_code == 401
    challenge = response.headers["www-authenticate"]
    assert challenge.startswith("Bearer")
    assert "resource_metadata=" in challenge
    assert "error=" not in challenge
    assert "invalid_token" not in response.text


async def test_a_bad_token_is_still_rejected_as_invalid(http_client):
    response = await http_client.post(
        "/mcp",
        json=INITIALIZE,
        headers={**HEADERS, "authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401
    assert 'error="invalid_token"' in response.headers["www-authenticate"]
