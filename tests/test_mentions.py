"""Native opening suggestions and authorization of exact peer references."""

import json
from pathlib import Path
from urllib.parse import quote

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mcp.types import ResourceLink
from mcp.shared.exceptions import McpError
from fulcra_mcp.main import mcp
from fulcra_mcp import mentions
from fulcra_api.connections import CHANNEL_FIELDS

LIST_ITEM = {"type": "resource_link", "uri": "contacts://threads",
             "name": "Agents I Know", "title": "Agents I Know", "mimeType": "application/json",
             "description": "Open the clickable connection list in chat with open_agent_contacts({})."}


def entry(id, owner=None):
    return {"id": f"Event/{id}", "name": "Mesh Outbox same name",
            "api_version": "v1", **({"fulcra_userid": owner, "categories": ["shared_type"]} if owner else {})}


def backend(fake, catalog, outgoing=(), incoming=()):
    catalog = [dict(e, description='connect-agents-with-anyone channel\n' + (e.get('description') or '')) for e in catalog]
    fake.v1_catalog.return_value = catalog
    fake.v1_catalog_schema.return_value = {'type':'object', **CHANNEL_FIELDS}
    fake.get_datashares.return_value = [dict(s, datashare_name='connect-agents-with-anyone: test') for s in outgoing]
    incoming = list(incoming)
    for e in catalog:
        if e.get('fulcra_userid'):
            incoming.append(dict(sharing_fulcra_userid=e['fulcra_userid'], grant_type='user',
                                 datashare_name='connect-agents-with-anyone: test', fulcra_data_types=[e['id']]))
    fake.get_shared_datasets.return_value = incoming


async def test_multiparty_native_descriptor_opens_exact_own_audience(fake_fulcra):
    backend(fake_fulcra, [entry('a')], outgoing=[{
        'share_all_data': False, 'fulcra_data_types': ['Event/a'],
        'permissions': [{'allowed_fulcra_userid': p} for p in ['peer', 'other']]}])
    async with Client(mcp) as client:
        items = await search(client)
        assert len(items) == 2
        descriptor = json.loads((await client.read_resource(items[1]['uri']))[0].text)
        assert 'peer_fulcra_userid' not in descriptor
        assert descriptor['thread_id'].startswith('connection:')
        assert descriptor['open_tool']['arguments'] == {'thread_id': descriptor['thread_id']}
        opened = await client.call_tool('open_agent_contacts', descriptor['open_tool']['arguments'])
        assert opened.structured_content['thread_id'] == descriptor['thread_id']
        fake_fulcra.get_datashares.return_value = []
        with pytest.raises(McpError):
            await client.read_resource(items[1]['uri'])


async def search(client, query=""):
    return (await client.call_tool("search_agent_contacts", {"query": query})).structured_content["items"]


@pytest.mark.parametrize("query,expected", [("", ["other", "peer"]), ("aLeX", ["other", "peer"]),
                                               ("PEER", ["peer"]), ("unmatched", [])])
async def test_search_includes_list_and_exact_peer_actions(query, expected, fake_fulcra):
    backend(fake_fulcra, [entry(id, peer) | {"description": '[mesh_identifier: "Alex"]'}
                          for id, peer in [("a", "peer"), ("b", "peer"), ("c", "other")]],
            incoming=[{"sharing_fulcra_userid": p, "sharing_fulcra_user_name": "Alex"}
                      for p in ["peer", "other"]])
    async with Client(mcp) as client:
        result = await client.call_tool("search_agent_contacts", {"query": query})
        assert result.content == []
        items = result.structured_content["items"]
        assert items[0]["name"] == items[0]["title"] == "Agents I Know"
        assert items[0]["uri"] == "contacts://threads"
        assert [item["uri"] for item in items[1:]] == ["contacts://threads/id-" + p for p in expected]
        for item, peer in zip(items[1:], expected):
            assert item["name"] == item["title"] == f"Open Agent Contact: Alex ({peer})"
            assert "open_agent_contacts" in item["description"]
        for item in items:
            assert ResourceLink.model_validate(item).mimeType == "application/json"
    assert {c[0] for c in fake_fulcra.mock_calls} == {
        "v1_catalog", "v1_catalog_schema", "get_fulcra_userid", "get_datashares", "get_shared_datasets"}


@pytest.mark.parametrize("description,title", [
    ('Peer outbox. [mesh_identifier: "Treecle"]', "Treecle (peer)"),
    (None, "peer"),
    ('[mesh_identifier: bad]', "peer"),
])
async def test_contact_identifier_labels_and_search(description, title, fake_fulcra):
    backend(fake_fulcra, [entry("a", "peer") | {"description": description}], incoming=[
        {"sharing_fulcra_userid": "peer", "sharing_fulcra_user_name": "peer"}])
    async with Client(mcp) as client:
        items = await search(client)
        assert items[0] == LIST_ITEM
        assert items[1]["name"] == items[1]["title"] == "Open Agent Contact: " + title
        descriptor = json.loads((await client.read_resource(items[1]["uri"]))[0].text)
        assert descriptor["title"] == title
        assert descriptor["open_tool"]["arguments"] == {"peer_fulcra_userid": "peer"}
        assert await search(client, "tReEcLe") == (items if description and "Treecle" in description else items[:1])
    assert {c[0] for c in fake_fulcra.mock_calls} == {
        "v1_catalog", "v1_catalog_schema", "get_fulcra_userid", "get_datashares", "get_shared_datasets"}


@pytest.mark.parametrize("sources,expected", [
    ([("a", "peer", "Incoming"), ("z", None, "Treecle")], "Treecle (peer)"),
    ([("z", None, "Z first"), ("a", None, "A wins")], "A wins (peer)"),
    ([("z", "peer", "Z first"), ("a", "peer", "A wins")], "A wins (peer)"),
    ([("a", None, None), ("z", "peer", "Incoming")], "Incoming (peer)"),
])
async def test_identifier_selection_matches_list_precedence(sources, expected, fake_fulcra):
    catalog = [entry(id, owner) | {"description": '[mesh_identifier: ' + json.dumps(label) + ']'}
               for id, owner, label in sources]
    grants = [{"fulcra_data_types": [e["id"]], "share_all_data": False,
               "permissions": [{"allowed_fulcra_userid": "peer"}]}
              for e in catalog if "fulcra_userid" not in e]
    async with Client(mcp) as client:
        for ordered in [catalog, list(reversed(catalog))]:
            backend(fake_fulcra, ordered, outgoing=grants)
            items = await search(client)
            assert [i["title"] for i in items] == ["Agents I Know", "Open Agent Contact: " + expected]
            assert json.loads((await client.read_resource(items[1]["uri"]))[0].text)["title"] == expected


async def test_mention_actions_resolve_to_existing_ui_tools(fake_fulcra):
    backend(fake_fulcra, [entry("a", "peer")])
    async with Client(mcp) as client:
        instructions = client.initialize_result.instructions
        assert "Agents I Know" in instructions and "Open Agent Contact:" in instructions
        assert "Bare @Fulcra: use set-up-agent-contacts for onboarding." in instructions
        assert "Agents I Know: open_agent_contacts({})." in instructions
        assert "explicit task wins" in instructions
        assert "mentions authorize opening only, not sends/shares/edits" in instructions
        assert "mesh_identifier/converted_from_mesh" in instructions
        assert "Do not migrate user data without explicit consent" in instructions
        contact = next(t for t in await client.list_tools() if t.name == "open_agent_contacts")
        assert "resolve contacts://threads/id-" in contact.description
        assert "exact peer_fulcra_userid" in contact.description
        items = await search(client)
        for item, name, arguments in zip(items, ["open_agent_contacts", "open_agent_contacts"],
                                         [{}, {"peer_fulcra_userid": "peer"}]):
            descriptor = json.loads((await client.read_resource(item["uri"]))[0].text)
            assert descriptor["open_tool"] == {"name": name, "arguments": arguments}
            result = await client.call_tool(name, arguments)
            assert result.structured_content["presentation"] in ["threads", "thread"]
            tool = next(t for t in await client.list_tools() if t.name == name)
            assert "model" in tool.meta["ui"]["visibility"]
            assert (await client.read_resource(tool.meta["ui"]["resourceUri"]))[0].mimeType == "text/html;profile=mcp-app"
    assert {c[0] for c in fake_fulcra.mock_calls} == {
        "v1_catalog", "v1_catalog_schema", "get_fulcra_userid", "get_datashares", "get_shared_datasets"}


async def test_search_is_bounded_but_exact_peer_remains_searchable(fake_fulcra):
    backend(fake_fulcra, [entry(str(i), f"peer-{i:02}") for i in reversed(range(25))])
    async with Client(mcp) as client:
        initial = await search(client, "  ")
        assert len(initial) == 21
        assert [item["uri"] for item in initial[1:]] == [f"contacts://threads/id-peer-{i:02}" for i in range(20)]
        assert (await search(client, "peer-24"))[1]["uri"] == "contacts://threads/id-peer-24"


async def test_unlabelled_descriptors_use_peer_not_account_names(fake_fulcra):
    backend(fake_fulcra, [entry("a", p) for p in ["peer", "other", "conflicting", "unnamed"]]
            + [entry("b", "peer")], incoming=[
        {"sharing_fulcra_userid": p, "sharing_fulcra_user_name": "Alex"} for p in ["peer", "other", "conflicting"]
    ] + [{"sharing_fulcra_userid": "conflicting", "sharing_fulcra_user_name": "Different"}])
    async with Client(mcp) as client:
        for peer in ["peer", "other", "conflicting", "unnamed"]:
            resource = (await client.read_resource("contacts://threads/id-" + peer))[0]
            descriptor = json.loads(resource.text)
            assert descriptor["peer_fulcra_userid"] == peer
            assert descriptor["title"] == peer


CASES = json.loads((Path(__file__).parent / "fixtures/connection-discovery.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
async def test_discovery_parity(case, fake_fulcra):
    narrow = {"data_types": ["Event/a"], "with_user_ids": ["peer"], "share_all_data": False}
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
               for e in case.get("catalog", [{"id": "Event/a", "name": "Mesh Outbox"}])]
    fake_fulcra.get_fulcra_userid.return_value = "me"
    backend(fake_fulcra, catalog, [raw(s) for s in outgoing], [raw(s) for s in case.get("incoming", [])])
    assert list(await mentions._discover_threads()) == case["expected"]


@pytest.mark.parametrize("peer", ["peer", "a/b ?#%雪", "%2F", "..", "a@b:c", " spaced "])
async def test_resource_resolution_preserves_encoded_exact_identity(peer, fake_fulcra):
    backend(fake_fulcra, [entry("a", peer) | {"description": '[mesh_identifier: "Alex"]'}], incoming=[
        {"sharing_fulcra_userid": peer, "sharing_fulcra_user_name": "Alex"}])
    uri = "contacts://threads/id-" + quote(peer, safe="")
    async with Client(mcp) as client:
        assert (await search(client, peer))[1]["uri"] == uri
        for _ in range(2):
            resource = (await client.read_resource(uri))[0]
            assert resource.mimeType == "application/json"
            assert json.loads(resource.text) == {
                "peer_fulcra_userid": peer, "title": f"Alex ({peer})",
                "open_tool": {"name": "open_agent_contacts", "arguments": {"peer_fulcra_userid": peer}}}
            assert str(resource.uri) == uri
    assert {c[0] for c in fake_fulcra.mock_calls} == {
        "v1_catalog", "v1_catalog_schema", "get_fulcra_userid", "get_datashares", "get_shared_datasets"}
    assert fake_fulcra.v1_catalog.call_count == 3


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
        with pytest.raises(ToolError, match="Agent Contact thread discovery failed"):
            await search(client)
        with pytest.raises(McpError, match="Agent Contact thread discovery failed"):
            await client.read_resource("contacts://threads/id-peer")


@pytest.mark.parametrize("change", ["revoked", "broad-grant", "different-user"])
async def test_resource_rechecks_access_and_fails_closed(change, fake_fulcra):
    narrow = {"fulcra_data_types": ["Event/a"], "share_all_data": False,
              "permissions": [{"allowed_fulcra_userid": "peer"}]}
    backend(fake_fulcra, [entry("a")], outgoing=[narrow])
    async with Client(mcp) as client:
        uri = "contacts://threads/id-peer"
        await client.read_resource(uri)
        if change == "revoked":
            backend(fake_fulcra, [])
        elif change == "broad-grant":
            fake_fulcra.get_datashares.return_value = [narrow, {"share_all_data": True}]
        else:
            fake_fulcra.get_fulcra_userid.return_value = "another-account"
            backend(fake_fulcra, [entry("a", "other-peer")])
        with pytest.raises(McpError, match="Agent Contact thread is not available"):
            await client.read_resource(uri)


async def test_descriptor_requires_account_auth(monkeypatch):
    from fulcra_mcp.settings import settings
    monkeypatch.setattr(settings, "fulcra_environment", "test")
    async with Client(mcp) as client:
        # In-memory Client bypasses HTTP auth; backend reads still require credentials.
        with pytest.raises(ToolError, match="not connected to a Fulcra account"):
            await search(client)
        with pytest.raises(McpError, match="not connected to a Fulcra account"):
            await client.read_resource("contacts://threads/id-peer")


async def test_required_string_query_and_unbounded_resource_lookup(fake_fulcra):
    backend(fake_fulcra, [entry(f"peer-{i:02}", f"peer-{i:02}") for i in range(25)])
    async with Client(mcp) as client:
        for args in [{}, {"query": None}, {"query": 123}, {"query": []}]:
            with pytest.raises(ToolError):
                await client.call_tool("search_agent_contacts", args)
        assert not fake_fulcra.mock_calls
        resource = (await client.read_resource("contacts://threads/id-peer-24"))[0]
        assert json.loads(resource.text)["peer_fulcra_userid"] == "peer-24"


@pytest.mark.parametrize("uri", ["contacts://threads/id-unknown", "contacts://threads/id-PEER",
                                     "contacts://threads/id-peer%252F", "contacts://threads/id-%FF",
                                     "contacts://threads/id-peer/other", "connection://other/id-peer"])
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
        uri = "contacts://threads/id-peer"
        await client.read_resource(uri)
        getattr(fake_fulcra, method).side_effect = http_error(403)
        with pytest.raises(ToolError, match="Agent Contact thread discovery failed"):
            await search(client)
        with pytest.raises(McpError, match="Agent Contact thread discovery failed"):
            await client.read_resource(uri)


async def test_native_picker_metadata(fake_fulcra):
    backend(fake_fulcra, [])
    async with Client(mcp) as client:
        tool = next(t for t in await client.list_tools() if t.name == "search_agent_contacts")
        assert tool.meta["ui"] == {"visibility": ["app"]}
        capabilities = client.initialize_result.capabilities.model_dump(by_alias=True)
        assert capabilities["experimental"]["openai/mentions"] == {"searchTool": "search_agent_contacts"}
        assert "openai/extensions" not in tool.meta
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.inputSchema["required"] == ["query"]
        assert tool.inputSchema["properties"]["query"]["type"] == "string"
        assert await search(client) == [LIST_ITEM]
