"""The server's identity (PLAT-617): one name, title and version across
server.json, the Server Card at /mcp/server-card, and the serverInfo clients see."""

import json
import re

import httpx
import pytest
from fastmcp import Client

from fulcra_mcp import server_info
from fulcra_mcp.main import app, mcp

SERVER_JSON = json.loads(server_info.SERVER_JSON.read_text())


@pytest.fixture
async def http_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def get_card(http_client, **headers):
    return await http_client.get(
        "/mcp/server-card", headers={"Accept": server_info.SERVER_CARD_MEDIA_TYPE, **headers}
    )


async def test_card_is_served_with_the_spec_headers(http_client):
    response = await get_card(http_client)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(server_info.SERVER_CARD_MEDIA_TYPE)
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.headers["access-control-expose-headers"] == "ETag"
    assert response.headers["cache-control"] == "public, max-age=3600"
    assert response.headers["etag"]


async def test_card_matches_server_json(http_client):
    card = (await get_card(http_client)).json()
    assert card["$schema"] == server_info.SERVER_CARD_SCHEMA
    for field in ("name", "title", "description", "websiteUrl", "repository", "icons", "remotes"):
        assert card[field] == SERVER_JSON[field], field
    # One version everywhere: the card, the package and the registry listing.
    assert card["version"] == server_info.version() == SERVER_JSON["version"]
    # Install details stay in the registry's server.json.
    assert "packages" not in card


async def test_card_follows_the_server_card_rules(http_client):
    card = (await get_card(http_client)).json()
    assert re.fullmatch(r"[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+", card["name"])
    assert 1 <= len(card["description"]) <= 100
    assert 1 <= len(card["title"]) <= 100


async def test_unchanged_card_is_not_resent(http_client):
    etag = (await get_card(http_client)).headers["etag"]
    for sent in (etag, f"W/{etag}", f'"other", {etag}'):
        response = await get_card(http_client, **{"If-None-Match": sent})
        assert response.status_code == 304, sent
        assert response.headers["etag"] == etag
    assert (await get_card(http_client, **{"If-None-Match": '"stale"'})).status_code == 200


async def test_card_preflight_allows_revalidation(http_client):
    response = await http_client.options(
        "/mcp/server-card",
        headers={"Origin": "https://example.com", "Access-Control-Request-Method": "GET",
                 "Access-Control-Request-Headers": "if-none-match"},
    )
    assert response.status_code == 204
    assert "If-None-Match" in response.headers["access-control-allow-headers"]


async def test_mcp_endpoint_is_not_shadowed(http_client):
    # Only /mcp/server-card is ours; /mcp itself still reaches the MCP app.
    response = await http_client.get("/mcp/")
    assert response.status_code != 404


async def test_server_info_matches_the_card():
    async with Client(mcp) as client:
        info = client.initialize_result.serverInfo
    # FastMCP can't set a title yet, so the name is what clients display.
    assert info.name == server_info.DISPLAY_NAME == SERVER_JSON["title"]
    assert info.version == server_info.version()
    assert info.websiteUrl == SERVER_JSON["websiteUrl"]
    assert [icon.src for icon in info.icons] == [icon["src"] for icon in SERVER_JSON["icons"]]


def test_server_info_without_server_json_falls_back(monkeypatch, tmp_path):
    # A PyPI install has no server.json: serverInfo still has a name and version.
    monkeypatch.setattr(server_info, "SERVER_JSON", tmp_path / "server.json")
    server_info.server_json.cache_clear()
    try:
        assert server_info.website_url() is None
        assert server_info.icons() is None
        assert server_info.version()
        with pytest.raises(FileNotFoundError):
            server_info.server_card()
    finally:
        server_info.server_json.cache_clear()
