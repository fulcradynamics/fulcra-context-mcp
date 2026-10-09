"""Static picker experiment and authorization of previously issued peer references."""

import json
from pathlib import Path
from urllib.parse import quote
from unittest.mock import Mock, AsyncMock

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mcp.types import ResourceLink
from mcp.shared.exceptions import McpError
from fulcra_mcp.main import mcp
from fulcra_mcp import mentions, tools

STATIC_ITEM = {"type": "resource_link", "uri": "ui://fulcra/mesh/threads/v22.html?startup=resource",
               "name": "Meshes", "title": "Meshes", "mimeType": "text/html;profile=mcp-app"}


def entry(id, owner=None):
    return {"id": f"MomentAnnotation/{id}", "name": "Mesh Outbox same name",
            "api_version": "v1", **({"fulcra_userid": owner, "categories": ["shared_type"]} if owner else {})}


def backend(fake, catalog, outgoing=(), incoming=()):
    fake.v1_catalog.return_value = catalog
    fake.get_datashares.return_value = list(outgoing)
    fake.get_shared_datasets.return_value = list(incoming)


async def search(client, query=""):
    return (await client.call_tool("mesh_mentions_search", {"query": query})).structured_content["items"]


@pytest.mark.parametrize("query", ["", "Meshes", "anyquery", "PEER-29", "雪", " " * 10000],
                         ids=["empty", "label", "anyquery", "old-peer", "unicode", "long"])
async def test_static_search_without_backend(query, fake_fulcra, monkeypatch):
    unavailable = Mock(side_effect=AssertionError("Backend must not be constructed"))
    discovery = AsyncMock(side_effect=AssertionError("Discovery must not run"))
    monkeypatch.setattr(tools, "get_fulcra_object", unavailable)
    monkeypatch.setattr(mentions, "_discover_threads", discovery)
    async with Client(mcp) as client:
        result = await client.call_tool("mesh_mentions_search", {"query": query})
        assert result.content == []
        assert result.structured_content == {"items": [STATIC_ITEM]}
        assert ResourceLink.model_validate(STATIC_ITEM).mimeType == "text/html;profile=mcp-app"
    unavailable.assert_not_called()
    discovery.assert_not_called()
    assert not fake_fulcra.mock_calls


async def test_old_descriptors_keep_exact_peers_and_label_rules(fake_fulcra):
    backend(fake_fulcra, [entry("a", p) for p in ["peer", "other", "conflicting", "unnamed"]]
            + [entry("b", "peer")], incoming=[
        {"sharing_fulcra_userid": p, "sharing_fulcra_user_name": "Alex"} for p in ["peer", "other", "conflicting"]
    ] + [{"sharing_fulcra_userid": "conflicting", "sharing_fulcra_user_name": "Different"}])
    async with Client(mcp) as client:
        for peer in ["peer", "other", "conflicting", "unnamed"]:
            resource = (await client.read_resource("mesh://threads/id-" + peer))[0]
            title = f"Alex ({peer})" if peer in ["peer", "other"] else peer
            assert json.loads(resource.text) == {"peer_fulcra_userid": peer, "title": title}


CASES = json.loads((Path(__file__).parent / "fixtures/mesh-discovery.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
async def test_discovery_parity(case, fake_fulcra):
    narrow = {"data_types": ["MomentAnnotation/a"], "with_user_ids": ["peer"], "share_all_data": False}
    outgoing = case.get("outgoing", [narrow])
    if "extra" in case:
        outgoing = outgoing + [narrow | case["extra"]]
    def raw(s):
        return {k: v for k, v in s.items() if k not in ("data_types", "with_user_ids", "with_group_ids", "file_paths", "file_history_paths")} | {
            "fulcra_data_types": s.get("data_types", []) + ["file:" + p for p in s.get("file_paths", [])]
                + ["filehistory:" + p for p in s.get("file_history_paths", [])],
            "permissions": [{"allowed_fulcra_userid": p} for p in s.get("with_user_ids", [])],
            "group_permissions": [{"allowed_group_id": p} for p in s.get("with_group_ids", [])],
        }
    catalog = [e | {"api_version": "v1", "categories": ["shared_type"], "queryable": "group" not in case}
               for e in case.get("catalog", [{"id": "MomentAnnotation/a", "name": "Mesh Outbox"}])]
    fake_fulcra.get_fulcra_userid.return_value = "me"
    backend(fake_fulcra, catalog, [raw(s) for s in outgoing], [raw(s) for s in case.get("incoming", [])])
    assert list(await mentions._discover_threads()) == case["expected"]


@pytest.mark.parametrize("peer", ["peer", "a/b ?#%雪", "%2F", "..", "a@b:c", " spaced "])
async def test_resource_resolution_preserves_encoded_exact_identity(peer, fake_fulcra):
    backend(fake_fulcra, [entry("a", peer)], incoming=[
        {"sharing_fulcra_userid": peer, "sharing_fulcra_user_name": "Alex"}])
    uri = "mesh://threads/id-" + quote(peer, safe="")
    async with Client(mcp) as client:
        for _ in range(2):
            resource = (await client.read_resource(uri))[0]
            assert resource.mimeType == "application/json"
            assert json.loads(resource.text) == {"peer_fulcra_userid": peer, "title": f"Alex ({peer})"}
            assert str(resource.uri) == uri
    assert {c[0] for c in fake_fulcra.mock_calls} == {
        "v1_catalog", "get_fulcra_userid", "get_datashares", "get_shared_datasets"}
    assert fake_fulcra.v1_catalog.call_count == 2


@pytest.mark.parametrize("failure", ["missing-own", "numeric-own", "catalog-owner", "catalog-offline", "shares-offline", "incoming-offline"])
async def test_descriptor_discovery_failure_is_not_empty_success(failure, fake_fulcra):
    backend(fake_fulcra, [entry("a", "peer")])
    if failure == "missing-own":
        fake_fulcra.get_fulcra_userid.return_value = None
    elif failure == "numeric-own":
        fake_fulcra.get_fulcra_userid.return_value = 42
    elif failure == "catalog-owner":
        fake_fulcra.v1_catalog.return_value = [entry("a", 42)]
    else:
        method = {"catalog-offline": "v1_catalog", "shares-offline": "get_datashares",
                  "incoming-offline": "get_shared_datasets"}[failure]
        getattr(fake_fulcra, method).side_effect = RuntimeError("private upstream detail")
    async with Client(mcp) as client:
        assert await search(client) == [STATIC_ITEM]
        with pytest.raises(McpError, match="Mesh thread discovery failed"):
            await client.read_resource("mesh://threads/id-peer")


@pytest.mark.parametrize("change", ["revoked", "broad-grant", "different-user"])
async def test_resource_rechecks_access_and_fails_closed(change, fake_fulcra):
    narrow = {"fulcra_data_types": ["MomentAnnotation/a"], "share_all_data": False,
              "permissions": [{"allowed_fulcra_userid": "peer"}]}
    backend(fake_fulcra, [entry("a")], outgoing=[narrow])
    async with Client(mcp) as client:
        uri = "mesh://threads/id-peer"
        await client.read_resource(uri)
        if change == "revoked":
            backend(fake_fulcra, [])
        elif change == "broad-grant":
            fake_fulcra.get_datashares.return_value = [narrow, {"share_all_data": True}]
        else:
            fake_fulcra.get_fulcra_userid.return_value = "another-account"
            backend(fake_fulcra, [entry("a", "other-peer")])
        with pytest.raises(McpError, match="Mesh thread is not available"):
            await client.read_resource(uri)


async def test_descriptor_requires_account_auth(monkeypatch):
    from fulcra_mcp.settings import settings
    monkeypatch.setattr(settings, "fulcra_environment", "test")
    async with Client(mcp) as client:
        # In-memory Client bypasses HTTP auth. Static search needs no backend;
        # hosted transport auth for both search and reads is tested separately.
        assert await search(client) == [STATIC_ITEM]
        with pytest.raises(McpError, match="not connected to a Fulcra account"):
            await client.read_resource("mesh://threads/id-peer")


async def test_required_string_query_and_unbounded_resource_lookup(fake_fulcra):
    backend(fake_fulcra, [entry(f"peer-{i:02}", f"peer-{i:02}") for i in range(25)])
    async with Client(mcp) as client:
        for args in [{}, {"query": None}, {"query": 123}, {"query": []}]:
            with pytest.raises(ToolError):
                await client.call_tool("mesh_mentions_search", args)
        assert not fake_fulcra.mock_calls
        resource = (await client.read_resource("mesh://threads/id-peer-24"))[0]
        assert json.loads(resource.text)["peer_fulcra_userid"] == "peer-24"


@pytest.mark.parametrize("uri", ["mesh://threads/id-unknown", "mesh://threads/id-PEER",
                                     "mesh://threads/id-peer%252F", "mesh://threads/id-%FF",
                                     "mesh://threads/id-peer/other", "mesh://other/id-peer"])
async def test_inaccessible_uri_never_selects_another_peer(uri, fake_fulcra):
    backend(fake_fulcra, [entry("a", "peer")])
    async with Client(mcp) as client:
        with pytest.raises(McpError):
            await client.read_resource(uri)


@pytest.mark.parametrize("method", ["v1_catalog", "get_datashares", "get_shared_datasets"])
async def test_backend_denial_after_success_never_reuses_discovery(method, fake_fulcra):
    from conftest import http_error
    backend(fake_fulcra, [entry("a", "peer")])
    async with Client(mcp) as client:
        uri = "mesh://threads/id-peer"
        await client.read_resource(uri)
        getattr(fake_fulcra, method).side_effect = http_error(403)
        assert await search(client) == [STATIC_ITEM]
        with pytest.raises(McpError, match="Mesh thread discovery failed"):
            await client.read_resource(uri)


async def test_native_picker_metadata(fake_fulcra):
    async with Client(mcp) as client:
        tool = next(t for t in await client.list_tools() if t.name == "mesh_mentions_search")
        assert tool.meta["ui"] == {"visibility": ["app"]}
        assert tool.meta["openai/extensions"] == {"mentions/search": {}}
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.inputSchema["required"] == ["query"]
        assert tool.inputSchema["properties"]["query"]["type"] == "string"
        assert await search(client) == [STATIC_ITEM]
    assert not fake_fulcra.mock_calls
