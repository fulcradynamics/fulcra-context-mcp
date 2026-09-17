"""Files served under /.well-known alongside the OAuth discovery documents.

The fastmcp app is mounted at "/" and owns /.well-known/oauth-*. Anything else
we serve under that prefix must be an explicit route, not a StaticFiles mount,
or it shadows OAuth discovery for every client.
"""

import json

import httpx
import pytest

from fulcra_mcp.main import app


@pytest.fixture
async def http_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client


async def test_glama_manifest_is_served(http_client):
    response = await http_client.get("/.well-known/glama.json")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = json.loads(response.text)
    assert body["$schema"] == "https://glama.ai/mcp/schemas/connector.json"
    assert body["claim"].startswith("glama_claim_")


@pytest.mark.parametrize(
    "path",
    [
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-authorization-server",
    ],
)
async def test_oauth_discovery_still_reachable(http_client, path):
    # Regression guard: serving glama.json must not shadow the fastmcp
    # discovery endpoints under the same prefix.
    response = await http_client.get(path)
    assert response.status_code == 200


async def test_icon_is_served(http_client):
    # server.json's icons[].src points at this URL; registries and directories
    # fetch it when rendering the listing.
    response = await http_client.get("/icon.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


async def test_path_form_protected_resource_metadata(http_client):
    # RFC 9728 §3.1: a client connecting to <base>/mcp fetches
    # /.well-known/oauth-protected-resource/mcp and expects the document's
    # `resource` to identify that endpoint, not the root.
    root = await http_client.get("/.well-known/oauth-protected-resource")
    path_form = await http_client.get("/.well-known/oauth-protected-resource/mcp")
    assert path_form.status_code == 200
    assert path_form.headers["content-type"].startswith("application/json")

    root_doc, doc = root.json(), path_form.json()
    assert doc["resource"] == root_doc["resource"].rstrip("/") + "/mcp"
    # Everything except the resource identifier must match the root document,
    # so the two can never disagree about where tokens come from.
    assert doc["authorization_servers"] == root_doc["authorization_servers"]
    assert doc["scopes_supported"] == root_doc["scopes_supported"]
    assert doc["bearer_methods_supported"] == ["header"]
