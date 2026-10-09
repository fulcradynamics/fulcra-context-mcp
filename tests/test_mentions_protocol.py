"""Serialized HTTP MCP smoke with real request auth and only synthetic backend data."""

import json
from datetime import datetime, timedelta
from unittest.mock import create_autospec, Mock

from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials
from mcp.server.auth.provider import AccessToken

from fulcra_mcp import credentials, tools
from fulcra_mcp.main import oauth_provider
from fulcra_mcp.settings import settings
from test_stateless import INITIALIZE, mcp_client
from test_mentions import STATIC_ITEM


async def test_mentions_http_protocol(tmp_path, monkeypatch):
    fake = create_autospec(FulcraAPI, instance=True)
    fake.get_fulcra_userid.return_value = "synthetic-own"
    fake.v1_catalog.return_value = [{
        "id": "MomentAnnotation/synthetic", "name": "Mesh Outbox", "api_version": "v1",
        "fulcra_userid": "peer/%2F", "categories": ["shared_type"],
    }]
    fake.get_datashares.return_value = []
    fake.get_shared_datasets.return_value = []
    creds = FulcraCredentials(access_token="synthetic-backend-token",
                             access_token_expiration=datetime.now() + timedelta(hours=1))
    other_creds = FulcraCredentials(access_token="synthetic-other-token",
                                   access_token_expiration=creds.access_token_expiration)
    other = create_autospec(FulcraAPI, instance=True)
    other.get_fulcra_userid.return_value = "synthetic-other"
    other.v1_catalog.return_value = []
    other.get_datashares.return_value = []
    other.get_shared_datasets.return_value = []
    # Keep the actual get_fulcra_object and HTTP OAuth middleware. No real
    # credentials are loaded and no API object capable of networking is created.
    monkeypatch.setattr(settings, "fulcra_environment", "test")
    factory = Mock(side_effect=lambda **kwargs: fake if kwargs["credentials"] is creds else other)
    monkeypatch.setattr(credentials, "FulcraAPI", factory)
    monkeypatch.setattr(oauth_provider, "credentials_for_token",
                        lambda token: {"mcp_test": ("synthetic-grant", creds),
                                       "mcp_other": ("synthetic-other-grant", other_creds)}.get(token))
    assert tools.get_fulcra_object is credentials.get_fulcra_object

    async with mcp_client(tmp_path) as http:
        monkeypatch.setitem(oauth_provider.tokens, "mcp_other", AccessToken(
            token="mcp_other", client_id="other", scopes=oauth_provider.tokens["mcp_test"].scopes,
            expires_at=oauth_provider.tokens["mcp_test"].expires_at))
        async def rpc(method, params=None):
            response = await http.post("/mcp", json={"jsonrpc": "2.0", "id": 2,
                                                     "method": method, "params": params or {}})
            assert response.status_code == 200
            # Streamable HTTP may return JSON directly or an SSE data event.
            body = response.text
            return json.loads(next(line[6:] for line in body.splitlines() if line.startswith("data: "))
                              if body.startswith("event:") else body)

        assert (await http.post("/mcp", json=INITIALIZE)).status_code == 200
        listed = (await rpc("tools/list"))["result"]["tools"]
        tool = next(t for t in listed if t["name"] == "mesh_mentions_search")
        assert tool["_meta"]["openai/extensions"] == {"mentions/search": {}}
        assert tool["_meta"]["ui"] == {"visibility": ["app"]}
        templates = (await rpc("resources/templates/list"))["result"]["resourceTemplates"]
        assert any(t["uriTemplate"] == "mesh://threads/id-{peer}" for t in templates)
        call = {"name": "mesh_mentions_search", "arguments": {"query": ""}}
        result = (await rpc("tools/call", call))["result"]
        assert result["content"] == []
        assert not result.get("isError")
        item, = result["structuredContent"]["items"]
        assert item == STATIC_ITEM
        direct_read = {"uri": item["uri"]}
        ui, = (await rpc("resources/read", direct_read))["result"]["contents"]
        assert ui["uri"] == item["uri"]
        assert ui["mimeType"] == item["mimeType"]
        assert ui["_meta"]["openai/ui"]["preferredDisplayMode"] == "inline"
        assert '<meta name="mesh-startup" content="resource">' in ui["text"]
        assert '<meta name="mesh-presentation" content="threads">' in ui["text"]
        factory.assert_not_called()
        assert not fake.mock_calls and not other.mock_calls
        # Backend unavailable: real authenticated routing still returns the static item.
        factory.side_effect = RuntimeError("backend offline")
        for query in ["anyquery", "Meshes", "unmatched"]:
            assert (await rpc("tools/call", {"name": "mesh_mentions_search", "arguments": {"query": query}}))["result"]["structuredContent"] == {"items": [item]}
        factory.assert_not_called()
        factory.side_effect = lambda **kwargs: fake if kwargs["credentials"] is creds else other
        # Old references continue to resolve only with current account authorization.
        read = {"uri": "mesh://threads/id-peer%2F%252F"}
        resource, = (await rpc("resources/read", read))["result"]["contents"]
        assert resource["mimeType"] == "application/json"
        assert json.loads(resource["text"]) == {"peer_fulcra_userid": "peer/%2F", "title": "peer/%2F"}

        # A new account context on the next request must not inherit discovery.
        http.headers["Authorization"] = "Bearer mcp_other"
        assert (await rpc("tools/call", call))["result"]["structuredContent"] == {"items": [item]}
        assert "error" in await rpc("resources/read", read)
        http.headers["Authorization"] = "Bearer mcp_test"
        assert (await rpc("tools/call", call))["result"]["structuredContent"]["items"] == [item]
        fake.v1_catalog.return_value = []
        assert "error" in await rpc("resources/read", read)
        for authorization in ["", "Bearer invalid-token"]:
            for method, params in [("tools/call", call), ("resources/read", read), ("resources/read", direct_read)]:
                response = await http.post("/mcp", headers={"Authorization": authorization},
                                           json={"jsonrpc": "2.0", "id": 3, "method": method, "params": params})
                assert response.status_code == 401

    assert {c[0] for c in fake.mock_calls} == {
        "v1_catalog", "get_fulcra_userid", "get_datashares", "get_shared_datasets"}
    assert {c[0] for c in other.mock_calls} == {
        "v1_catalog", "get_fulcra_userid", "get_datashares", "get_shared_datasets"}
