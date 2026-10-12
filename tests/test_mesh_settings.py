"""Read-only scheduled-check status and native settings protocol."""

import io
import json

import pytest
from fastmcp import Client
from fulcra_mcp.main import mcp

ROOT = "/agent/chatgpt/mesh-checks/"


def state(fake, last_checked=None, **changes):
    fake.get_fulcra_userid.return_value = "me"
    fake.list_files.return_value = {"folders": [], "files": [
        {"id": "file-a", "path": ROOT.rstrip("/"), "name": "a.md"}]}
    data = dict(version=1, account_id="me", agent_name="chatgpt", scope="all",
                start_time="2026-10-01T00:00:00Z", task_id="task-a",
                last_checked=last_checked, pending=[{"body": "PRIVATE MESSAGE"}], reported=[])
    data.update(changes)
    fake.download_file.side_effect = lambda *args: io.BytesIO(
        ('---\ntype: Task\n---\n```json\n' + json.dumps(data) + '\n```\n').encode())


async def test_native_settings_read_contract(fake_fulcra):
    state(fake_fulcra)
    async with Client(mcp) as client:
        capabilities = client.initialize_result.capabilities.experimental
        assert capabilities["openai/settings"] == {
            "readTool": "aicq_settings_read", "updateTool": "aicq_settings_update"}
        tools = {t.name: t for t in await client.list_tools()}
        tool = tools["aicq_settings_read"]
        assert tool.inputSchema.get("properties", {}) == {}
        assert set(tool.outputSchema["required"]) >= {"schema", "values"}
        result = (await client.call_tool(tool.name, {})).structured_content
        assert result["schema"] == {"type": "object", "properties": {}}
        assert result["values"] == {}
        action = result["layout"][0]["items"][0]
        assert action["tool"] == "aicq_schedule_settings"
        assert action["description"] == "Last mesh check: Never checked"
        opener = tools[action["tool"]]
        assert opener.inputSchema.get("properties", {}) == {}
        assert opener.meta["ui"]["visibility"] == ["app"]
        assert opener.annotations.readOnlyHint
        status = (await client.call_tool(opener.name, {})).structured_content
        assert status["status"] == "never_checked"
        resource = (await client.read_resource(opener.meta["ui"]["resourceUri"]))[0]
        assert resource.mimeType == "text/html;profile=mcp-app"
        assert "Reschedule checks in Chat" in resource.text
        assert "PRIVATE MESSAGE" not in json.dumps(result) + json.dumps(status)
        rejected = await client.call_tool("aicq_settings_update", {"set": {"interval": 30}}, raise_on_error=False)
        assert rejected.is_error
    assert {c[0] for c in fake_fulcra.mock_calls} <= {
        "get_fulcra_userid", "list_files", "download_file"}


@pytest.mark.parametrize("last,label", [(None, "Never checked"),
    ("2026-10-12T10:00:00-05:00", "2026-10-12T15:00:00Z")])
async def test_successful_status_read_is_repeatable_without_writes(fake_fulcra, last, label):
    state(fake_fulcra, last)
    async with Client(mcp) as client:
        for _ in range(2):
            result = (await client.call_tool("aicq_check_status", {})).structured_content
            assert result["label"] == label
            assert result["task_id"] == "task-a"
            assert "PRIVATE MESSAGE" not in json.dumps(result)
    assert {c[0] for c in fake_fulcra.mock_calls} == {
        "get_fulcra_userid", "list_files", "download_file"}


@pytest.mark.parametrize("changes", [{"account_id": "other"}, {"last_checked": "2026-10-12"},
    {"last_checked": "bad"}, {"version": 2}, {"task_id": 123}, {"version": True},
    {"start_time": "bad"}, {"agent_name": ""}])
async def test_malformed_or_wrong_account_state_is_not_never_checked(fake_fulcra, changes):
    state(fake_fulcra, **changes)
    async with Client(mcp) as client:
        result = (await client.call_tool("aicq_check_status", {})).structured_content
        assert result == {"status": "unavailable", "label": "Status unavailable"}


async def test_empty_listing_and_inaccessible_state_differ(fake_fulcra):
    state(fake_fulcra)
    async with Client(mcp) as client:
        fake_fulcra.list_files.return_value = {"folders": [], "files": []}
        assert (await client.call_tool("aicq_check_status", {})).structured_content["status"] == "not_set_up"
        # A selected configuration disappearing is not a successful empty read.
        assert (await client.call_tool("aicq_check_status", {"configuration_id": "a"})).structured_content["status"] == "unavailable"
        fake_fulcra.list_files.side_effect = RuntimeError("secret upstream error")
        result = (await client.call_tool("aicq_check_status", {})).structured_content
        assert result == {"status": "unavailable", "label": "Status unavailable"}


async def test_configuration_selection_is_explicit_and_not_combined(fake_fulcra):
    state(fake_fulcra)
    fake_fulcra.list_files.return_value["files"].append({"id": "file-b", "path": ROOT, "name": "b.md"})
    async with Client(mcp) as client:
        choices = (await client.call_tool("aicq_check_status", {})).structured_content
        assert choices["status"] == "choose_configuration"
        assert choices["configurations"] == ["a", "b"]
        fake_fulcra.download_file.assert_not_called()
        result = (await client.call_tool("aicq_check_status", {"configuration_id": "b"})).structured_content
        assert result["state_path"] == ROOT + "b.md"
        fake_fulcra.download_file.assert_called_once_with("file-b")
        fake_fulcra.download_file.reset_mock()
        result = (await client.call_tool("aicq_check_status", {"configuration_id": "../outside"})).structured_content
        assert result["status"] == "unavailable"
        fake_fulcra.download_file.assert_not_called()


@pytest.mark.parametrize("content", [b"bad state", b"x" * 1_000_001,
    b'```json\n{"version":1,"account_id":"me","task_id":null,"last_checked":null}\n```'])
async def test_malformed_truncated_or_incomplete_state(fake_fulcra, content):
    state(fake_fulcra)
    fake_fulcra.download_file.side_effect = lambda *args: io.BytesIO(content)
    async with Client(mcp) as client:
        assert (await client.call_tool("aicq_check_status", {})).structured_content["status"] == "unavailable"


async def test_status_resolves_each_authenticated_request(monkeypatch, fake_fulcra):
    from unittest.mock import create_autospec
    from fulcra_api.core import FulcraAPI
    from fulcra_mcp import tools
    state(fake_fulcra, "2026-10-12T15:00:00Z")
    other = create_autospec(FulcraAPI, instance=True)
    other.get_fulcra_userid.return_value = "other"
    other.list_files.return_value = {"files": [], "folders": []}
    async with Client(mcp) as client:
        assert (await client.call_tool("aicq_check_status", {})).structured_content["account_id"] == "me"
        monkeypatch.setattr(tools, "get_fulcra_object", lambda: other)
        assert (await client.call_tool("aicq_check_status", {})).structured_content == {
            "status": "not_set_up", "label": "Not set up"}
    other.download_file.assert_not_called()


async def test_real_sdk_uses_authenticated_private_file_transport(monkeypatch):
    from fulcra_api.core import FulcraAPI
    from fulcra_mcp import tools
    fulcra = FulcraAPI()
    monkeypatch.setattr(fulcra, "get_token_claims", lambda: {"fulcradynamics.com/userid": "me"})
    requests = []
    payload = dict(version=1, account_id="me", agent_name="chatgpt", scope="all",
                   start_time="2026-10-01T00:00:00Z", task_id="task", last_checked=None,
                   pending=[], reported=[])
    stream = io.BytesIO(('```json\n' + json.dumps(payload) + '\n```').encode())
    def transport(endpoint, **kwargs):
        requests.append((endpoint, kwargs))
        if endpoint == "/input/v1/file_upload":
            return json.dumps({"files": [{"id": "private-file", "name": "a.md", "path": ROOT.rstrip('/')}], "folders": []})
        assert endpoint == "/input/v1/file_upload/private-file/download"
        return stream
    monkeypatch.setattr(fulcra, "fulcra_api", transport)
    monkeypatch.setattr(tools, "get_fulcra_object", lambda: fulcra)
    async with Client(mcp) as client:
        result = (await client.call_tool("aicq_check_status", {})).structured_content
        assert result["status"] == "never_checked"
    assert requests == [
        ("/input/v1/file_upload", {"query": {"path": ROOT.rstrip('/'), "state": "uploaded"}}),
        ("/input/v1/file_upload/private-file/download", {"query": {}, "return_http_response": True}),
    ]
    assert stream.closed
