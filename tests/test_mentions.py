"""Native mention protocol tests; only the backend is mocked."""

import json
from pathlib import Path

import pytest
from fastmcp import Client
from mcp.types import ResourceLink


def entry(id, owner=None):
    return {"id": f"MomentAnnotation/{id}", "name": "Mesh Outbox same name",
            "api_version": "v1", **({"fulcra_userid": owner, "categories": ["shared_type"]} if owner else {})}


def backend(fake, catalog, outgoing=(), incoming=()):
    fake.v1_catalog.return_value = catalog
    fake.get_datashares.return_value = list(outgoing)
    fake.get_shared_datasets.return_value = list(incoming)


async def search(client, query=""):
    return (await client.call_tool("mesh_mentions_search", {"query": query})).structured_content["items"]


async def test_incoming_exact_peers_not_channel_names(fake_fulcra):
    backend(fake_fulcra, [entry("a", "peer"), entry("b", "peer"), entry("a", "other")],
            incoming=[{"sharing_fulcra_userid": p, "sharing_fulcra_user_name": "Alex"}
                      for p in ["peer", "other"]])
    async with Client(mcp) as client:
        items = await search(client)
        assert [i["name"] for i in items] == ["other", "peer"]
        assert [i["title"] for i in items] == ["Alex (other)", "Alex (peer)"]
        for item in items:
            assert ResourceLink.model_validate(item).mimeType == "application/json"
            assert item["uri"] == "mesh://threads/id-" + item["name"]

from fulcra_mcp.main import mcp


CASES = json.loads((Path(__file__).parent / "fixtures/mesh-discovery.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
async def test_discovery_parity(case, fake_fulcra):
    narrow = {"data_types": ["MomentAnnotation/a"], "with_user_ids": ["peer"], "share_all_data": False}
    outgoing = case.get("outgoing", [narrow])
    if "extra" in case:
        outgoing = outgoing + [narrow | case["extra"]]
    # Fixtures use the same slim wire contract consumed by web/meshes.js.
    def raw(s):
        return {k: v for k, v in s.items() if k not in ("data_types", "with_user_ids", "with_group_ids", "file_paths", "file_history_paths")} | {
            "fulcra_data_types": s.get("data_types", []) + ["file:" + p for p in s.get("file_paths", [])]
                + ["filehistory:" + p for p in s.get("file_history_paths", [])],
            "permissions": [{"allowed_fulcra_userid": p} for p in s.get("with_user_ids", [])],
            "group_permissions": [{"allowed_group_id": p} for p in s.get("with_group_ids", [])],
        }
    catalog = [e | {"api_version": "v1", "categories": ["shared_type"],
                       "queryable": "group" not in case}
               for e in case.get("catalog", [{"id": "MomentAnnotation/a", "name": "Mesh Outbox"}])]
    fake_fulcra.get_fulcra_userid.return_value = "me"
    backend(fake_fulcra, catalog, [raw(s) for s in outgoing], [raw(s) for s in case.get("incoming", [])])
    async with Client(mcp) as client:
        assert [i["name"] for i in await search(client)] == case["expected"]



async def test_typeahead_is_bounded_sorted_and_matches_label_or_id(fake_fulcra):
    peers = [f"peer-{i:02}" for i in reversed(range(30))]
    backend(fake_fulcra, [entry(p, p) for p in peers], incoming=[
        {"sharing_fulcra_userid": "peer-29", "sharing_fulcra_user_name": "Zebra"},
        {"sharing_fulcra_userid": "peer-28", "sharing_fulcra_user_name": "Zebra"},
        {"sharing_fulcra_userid": "peer-27", "sharing_fulcra_user_name": "Conflicting"},
        {"sharing_fulcra_userid": "peer-27", "sharing_fulcra_user_name": "Labels"},
    ])
    async with Client(mcp) as client:
        items = await search(client)
        assert [i["name"] for i in items] == sorted(peers)[:20]
        assert [i["name"] for i in await search(client, "zEb")] == ["peer-28", "peer-29"]
        assert [i["name"] for i in await search(client, "PEER-29")] == ["peer-29"]
        assert await search(client, "Conflicting") == []
        assert await search(client, "Mesh Outbox") == []
        assert await search(client, "nobody") == []
        assert (await search(client, "peer-27"))[0]["title"] == "peer-27"


@pytest.mark.parametrize("peer", ["peer", "a/b ?#%雪", "%2F", "..", "a@b:c", " spaced "])
async def test_resource_resolution_preserves_encoded_exact_identity(peer, fake_fulcra):
    from urllib.parse import quote

    backend(fake_fulcra, [entry("a", peer)], incoming=[
        {"sharing_fulcra_userid": peer, "sharing_fulcra_user_name": "Alex"}])
    async with Client(mcp) as client:
        item = (await search(client))[0]
        assert item["uri"] == "mesh://threads/id-" + quote(peer, safe="")
        resource = (await client.read_resource(item["uri"]))[0]
        assert resource.mimeType == "application/json"
        assert json.loads(resource.text) == {"peer_fulcra_userid": peer, "title": f"Alex ({peer})"}
        assert str(resource.uri) == item["uri"]
    assert {c[0] for c in fake_fulcra.mock_calls} == {
        "v1_catalog", "get_fulcra_userid", "get_datashares", "get_shared_datasets"}
    assert fake_fulcra.v1_catalog.call_count == 2  # Read revalidates, never cached.


@pytest.mark.parametrize("failure", ["missing-own", "numeric-own", "catalog-owner", "catalog-offline", "shares-offline", "incoming-offline"])
async def test_discovery_failure_is_not_empty_success(failure, fake_fulcra):
    from fastmcp.exceptions import ToolError
    from mcp.shared.exceptions import McpError

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
        with pytest.raises(ToolError, match="Mesh thread discovery failed"):
            await search(client)
        with pytest.raises(McpError, match="Mesh thread discovery failed"):
            await client.read_resource("mesh://threads/id-peer")


@pytest.mark.parametrize("change", ["revoked", "broad-grant", "different-user"])
async def test_resource_rechecks_access_and_fails_closed(change, fake_fulcra):
    from mcp.shared.exceptions import McpError

    narrow = {"fulcra_data_types": ["MomentAnnotation/a"], "share_all_data": False,
              "permissions": [{"allowed_fulcra_userid": "peer"}]}
    backend(fake_fulcra, [entry("a")], outgoing=[narrow])
    async with Client(mcp) as client:
        uri = (await search(client))[0]["uri"]
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
        assert all(i["uri"] != uri for i in await search(client))
        with pytest.raises(McpError, match="Mesh thread is not available"):
            await client.read_resource("mesh://threads/id-unknown")
    assert {c[0] for c in fake_fulcra.mock_calls} == {
        "v1_catalog", "get_fulcra_userid", "get_datashares", "get_shared_datasets"}


async def test_hosted_requests_require_account_auth(monkeypatch):
    from fastmcp.exceptions import ToolError
    from mcp.shared.exceptions import McpError
    from fulcra_mcp.settings import settings

    monkeypatch.setattr(settings, "fulcra_environment", "test")
    async with Client(mcp) as client:
        with pytest.raises(ToolError, match="not connected to a Fulcra account"):
            await search(client)
        with pytest.raises(McpError, match="not connected to a Fulcra account"):
            await client.read_resource("mesh://threads/id-peer")


async def test_required_string_query_and_unbounded_resource_lookup(fake_fulcra):
    from fastmcp.exceptions import ToolError

    peers = [f"peer-{i:02}" for i in range(25)]
    backend(fake_fulcra, [entry(p, p) for p in peers])
    async with Client(mcp) as client:
        for args in [{}, {"query": None}, {"query": 123}, {"query": []}]:
            with pytest.raises(ToolError):
                await client.call_tool("mesh_mentions_search", args)
        assert not fake_fulcra.mock_calls
        assert len(await search(client)) == 20
        resource = (await client.read_resource("mesh://threads/id-peer-24"))[0]
        assert json.loads(resource.text)["peer_fulcra_userid"] == "peer-24"


@pytest.mark.parametrize("uri", ["mesh://threads/id-unknown", "mesh://threads/id-PEER",
                                     "mesh://threads/id-peer%252F", "mesh://threads/id-%FF",
                                     "mesh://threads/id-peer/other", "mesh://other/id-peer"])
async def test_inaccessible_uri_never_selects_another_peer(uri, fake_fulcra):
    from mcp.shared.exceptions import McpError

    backend(fake_fulcra, [entry("a", "peer")])
    async with Client(mcp) as client:
        with pytest.raises(McpError):
            await client.read_resource(uri)


@pytest.mark.parametrize("method", ["v1_catalog", "get_datashares", "get_shared_datasets"])
async def test_backend_denial_after_success_never_reuses_discovery(method, fake_fulcra):
    from conftest import http_error
    from fastmcp.exceptions import ToolError
    from mcp.shared.exceptions import McpError

    backend(fake_fulcra, [entry("a", "peer")])
    async with Client(mcp) as client:
        uri = (await search(client))[0]["uri"]
        getattr(fake_fulcra, method).side_effect = http_error(403)
        with pytest.raises(ToolError, match="Mesh thread discovery failed"):
            await search(client)
        with pytest.raises(McpError, match="Mesh thread discovery failed"):
            await client.read_resource(uri)


async def test_native_picker_metadata_and_empty_query(fake_fulcra):
    fake_fulcra.v1_catalog.return_value = []
    fake_fulcra.get_datashares.return_value = []
    fake_fulcra.get_shared_datasets.return_value = []
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
        assert "mesh_mentions_search" in tools
        tool = tools["mesh_mentions_search"]
        assert tool.meta["ui"] == {"visibility": ["app"]}
        assert tool.meta["openai/extensions"] == {"mentions/search": {}}
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.inputSchema["required"] == ["query"]
        assert tool.inputSchema["properties"]["query"]["type"] == "string"
        result = await client.call_tool("mesh_mentions_search", {"query": ""})
        assert result.structured_content == {"items": []}
        assert result.content == []
    assert {c[0] for c in fake_fulcra.mock_calls} == {
        "v1_catalog", "get_fulcra_userid", "get_datashares", "get_shared_datasets"}
