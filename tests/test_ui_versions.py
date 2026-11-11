"""Earlier UI versions stay readable at the URIs they shipped under.

A host that stored a tool's resource URI when it was published keeps asking for
that URI. Dropping contacts v82 when v83 shipped broke the published ChatGPT
app's panel; see fulcra_mcp/ui_versions.py.
"""

import json
from importlib.resources import files

import pytest
from fastmcp import Client, FastMCP

from fulcra_mcp import apps, file_transfer, ui_versions
from fulcra_mcp.claude_endpoint import CLAUDE_MCP_PATH
from fulcra_mcp.main import claude_mcp, mcp, openai_mcp
from fulcra_mcp.openai_endpoint import OPENAI_MCP_PATH
from test_stateless import mcp_client

# The oldest version each app keeps. Every version from here up to the current
# one must be readable, so raising a version without keeping the outgoing one
# fails here.
FIRST_KEPT = {"contacts": 82, "file-manager": 4}
# The only exception: a number that never reached a deployed server (one used
# while iterating on a branch, say). Nothing can have stored its URI.
NEVER_DEPLOYED: dict[str, set[int]] = {"contacts": set(), "file-manager": set()}
CURRENT = {"contacts": apps.CONTACTS_UI_VERSION, "file-manager": file_transfer.FILE_MANAGER_VERSION}

ENDPOINTS = pytest.mark.parametrize("server", [mcp, openai_mcp, claude_mcp], ids=["mcp", "openai", "claude"])
EARLIER_CONTACTS = sorted(apps.CONTACTS_BUNDLES.keys() - {apps.CONTACTS_UI_VERSION})


@pytest.mark.parametrize("app", sorted(FIRST_KEPT))
def test_no_released_version_is_dropped(app):
    kept = ui_versions.bundles(app).keys() | {CURRENT[app]}
    dropped = set(range(FIRST_KEPT[app], CURRENT[app])) - kept - NEVER_DEPLOYED[app]
    assert not dropped, (
        f"{app} UI version(s) {sorted(dropped)} are no longer served, so a host that stored "
        f"their URIs can't open the panel. Restore fulcra_mcp/ui/{app}/v<N>.html "
        "(docs/contacts-app.md, \"UI versions\"). Add a number to NEVER_DEPLOYED only if "
        "no deployed server ever advertised it."
    )


def test_v82_is_kept():
    """The version the published ChatGPT app stored."""
    assert 82 in EARLIER_CONTACTS


@ENDPOINTS
@pytest.mark.parametrize("version", EARLIER_CONTACTS)
async def test_earlier_contacts_versions_are_readable(server, version):
    packaged = files("fulcra_mcp").joinpath(f"ui/contacts/v{version}.html").read_text(encoding="utf-8")
    current = apps.CONTACTS_BUNDLES[apps.CONTACTS_UI_VERSION].read_text(encoding="utf-8")
    assert packaged != current
    global_uri, thread_uri, direct_uri = apps.contacts_uris(version)
    async with Client(server) as client:
        [whole] = await client.read_resource(global_uri)
        [thread] = await client.read_resource(thread_uri)
        [direct] = await client.read_resource(direct_uri)
        [now] = await client.read_resource(apps.THREAD_UI_URI)
    assert whole.text == packaged  # that version's own bundle, not the current one
    assert thread.text == packaged.replace(
        '<meta name="connection-presentation" content="global">',
        '<meta name="connection-presentation" content="thread">', 1)
    assert thread.text != packaged
    assert direct.text == thread.text.replace(
        '</head>', '<meta name="connection-startup" content="resource"></head>', 1)
    assert direct.text != thread.text
    for content in (whole, thread, direct):
        assert content.mimeType == now.mimeType == "text/html;profile=mcp-app"
        assert content.meta["openai/ui"] == now.meta["openai/ui"]


@ENDPOINTS
async def test_only_current_versions_are_advertised(server, app_capabilities):
    async with Client(server) as client:
        listed = {str(r.uri) for r in await client.list_resources()}
        tools = {t.name: t for t in await client.list_tools()}
    assert set(apps.contacts_uris(apps.CONTACTS_UI_VERSION)) <= listed
    assert file_transfer.FILE_MANAGER_URI in listed
    for version in EARLIER_CONTACTS:
        assert listed.isdisjoint(apps.contacts_uris(version))
    assert tools["open_agent_contacts"].meta["ui"]["resourceUri"] == apps.THREAD_UI_URI
    assert tools["open_agent_contacts_home"].meta["ui"]["resourceUri"] == apps.UI_URI


async def test_earlier_version_follows_the_debug_setting(monkeypatch):
    from fulcra_mcp.settings import Settings

    monkeypatch.setenv("FULCRA_CONTACTS_DEBUG", "true")
    monkeypatch.setattr(apps, "settings", Settings())
    async with Client(mcp) as client:
        for uri in apps.contacts_uris(EARLIER_CONTACTS[-1]):
            assert '<meta name="connection-debug" content="true">' in (await client.read_resource(uri))[0].text


@pytest.mark.parametrize("path", ["/mcp", OPENAI_MCP_PATH, CLAUDE_MCP_PATH])
async def test_hosted_endpoints_serve_the_uri_the_published_app_stored(tmp_path, path):
    """The request that failed: resources/read of v82 over stateless HTTP."""
    uri = "ui://fulcra/contacts/thread/v82.html"
    async with mcp_client(tmp_path) as client:
        response = await client.post(path, json={
            "jsonrpc": "2.0", "id": 3, "method": "resources/read", "params": {"uri": uri}})
    message = next(json.loads(line.removeprefix("data: "))
                   for line in response.text.splitlines() if line.startswith("data: "))
    assert "error" not in message, message
    [content] = message["result"]["contents"]
    assert content["uri"] == uri
    assert content["mimeType"] == "text/html;profile=mcp-app"
    assert '<meta name="connection-presentation" content="thread">' in content["text"]


async def test_earlier_file_manager_versions_are_readable(tmp_path):
    """There is no earlier panel yet; this is what happens once there is."""
    saved = tmp_path / "v3.html"
    saved.write_text("<!doctype html><title>earlier panel</title>", encoding="utf-8")
    server = FastMCP("file manager versions")
    server.add_middleware(ui_versions.CurrentVersionsOnly())
    file_transfer.keep_earlier_file_managers(server, {3: saved, file_transfer.FILE_MANAGER_VERSION: saved})
    async with Client(server) as client:
        assert not await client.list_resources()
        [content] = await client.read_resource("ui://fulcra/file-manager/v3.html")
        with pytest.raises(Exception):
            await client.read_resource(file_transfer.FILE_MANAGER_URI)  # the current one isn't registered twice
    assert content.text == saved.read_text(encoding="utf-8")
    assert content.mimeType == "text/html;profile=mcp-app"


async def test_current_file_manager_is_its_versioned_file(client):
    packaged = files("fulcra_mcp").joinpath(
        f"ui/file-manager/v{file_transfer.FILE_MANAGER_VERSION}.html").read_text(encoding="utf-8")
    [content] = await client.read_resource(file_transfer.FILE_MANAGER_URI)
    assert content.text == packaged
    assert [str(r.uri) for r in await client.list_resources() if "file-manager" in str(r.uri)] == [
        file_transfer.FILE_MANAGER_URI]
