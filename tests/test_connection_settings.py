"""Read-only scheduled-check status and native settings protocol."""

import io
import json

import pytest
from fastmcp import Client
from fulcra_mcp.main import mcp

ROOT = "/connect-our-agents/connection-checks/"


@pytest.fixture(autouse=True)
def default_preferences(monkeypatch):
    # Status-projection tests isolate the separate preference store; its real
    # persistence/authentication paths are covered in test_contact_preferences.
    from fulcra_mcp import contact_preferences as policy
    monkeypatch.setattr(policy, 'read', lambda api: dict(policy.DEFAULTS))


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
            "readTool": "fulcra_settings_read", "updateTool": "fulcra_settings_update"}
        tools = {t.name: t for t in await client.list_tools()}
        tool = tools["fulcra_settings_read"]
        assert tool.inputSchema.get("properties", {}) == {}
        assert set(tool.outputSchema["required"]) >= {"schema", "values"}
        result = (await client.call_tool(tool.name, {})).structured_content
        from fulcra_mcp.contact_preferences import DEFAULTS, SCHEMA, NOTIFICATION_LABELS, native_values
        assert result["schema"] == {"type": "object", "properties": {
            **SCHEMA, 'notifications': {**SCHEMA['notifications'], 'enum': list(NOTIFICATION_LABELS.values())}}}
        assert result["values"] == native_values({k: DEFAULTS[k] for k in SCHEMA})
        assert result["layout"][:2] == [
            {"kind": "group", "title": "Last contact check: Never checked", "items": []},
            {"kind": "group", "title": 'To change the schedule, ask in chat: “Change how often you check my Fulcra messages.”', "items": []},
        ]
        assert "PRIVATE MESSAGE" not in json.dumps(result)
        rejected = await client.call_tool("fulcra_settings_update", {"set": {"interval": 30}}, raise_on_error=False)
        assert rejected.is_error
    assert {c[0] for c in fake_fulcra.mock_calls} <= {
        "get_fulcra_userid", "list_files", "download_file"}


@pytest.mark.parametrize("scenario,label", [
    ("empty", "Not set up"),
    ("never", "Never checked"),
    ("checked", "2026-10-12T15:00:00Z"),
    ("unavailable", "Status unavailable"),
    ("wrong_account", "Status unavailable"),
    ("multiple", "Multiple configurations — ask in chat to choose one"),
])
async def test_native_titles_cover_status_without_actions_or_writes(fake_fulcra, scenario, label):
    state(fake_fulcra, "2026-10-12T10:00:00-05:00" if scenario == "checked" else None)
    if scenario == "empty":
        fake_fulcra.list_files.return_value["files"] = []
    elif scenario == "unavailable":
        fake_fulcra.list_files.side_effect = RuntimeError("PRIVATE ERROR")
    elif scenario == "wrong_account":
        fake_fulcra.get_fulcra_userid.return_value = "other"
    elif scenario == "multiple":
        fake_fulcra.list_files.return_value["files"].append({"id": "file-b", "name": "b.md"})
    async with Client(mcp) as client:
        for _ in range(2):
            result = (await client.call_tool("fulcra_settings_read", {})).structured_content
            from fulcra_mcp.contact_preferences import DEFAULTS, SCHEMA, NOTIFICATION_LABELS, native_values
            assert result["schema"] == {"type": "object", "properties": {
                **SCHEMA, 'notifications': {**SCHEMA['notifications'], 'enum': list(NOTIFICATION_LABELS.values())}}}
            assert result["values"] == native_values({k: DEFAULTS[k] for k in SCHEMA})
            assert result["layout"][0]["title"] == "Last contact check: " + label
            assert result["layout"][1]["title"] == (
                'To change the schedule, ask in chat: “Change how often you check my Fulcra messages.”')
            assert all(g["kind"] == "group" and g["items"] == [] for g in result["layout"][:2])
            assert all(item['kind'] == 'property' for item in result['layout'][2]['items'])
            assert "PRIVATE" not in json.dumps(result)
    assert {c[0] for c in fake_fulcra.mock_calls} <= {
        "get_fulcra_userid", "list_files", "download_file"}
    if scenario in {"empty", "unavailable", "multiple"}:
        fake_fulcra.download_file.assert_not_called()


@pytest.mark.parametrize("last,label", [(None, "Never checked"),
    ("2026-10-12T10:00:00-05:00", "2026-10-12T15:00:00Z")])
async def test_successful_status_read_is_repeatable_without_writes(fake_fulcra, last, label):
    state(fake_fulcra, last)
    async with Client(mcp) as client:
        for _ in range(2):
            result = (await client.call_tool("fulcra_check_status", {})).structured_content
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
        result = (await client.call_tool("fulcra_check_status", {})).structured_content
        assert result == {"status": "unavailable", "label": "Status unavailable"}


async def test_empty_listing_and_inaccessible_state_differ(fake_fulcra):
    state(fake_fulcra)
    async with Client(mcp) as client:
        fake_fulcra.list_files.return_value = {"folders": [], "files": []}
        assert (await client.call_tool("fulcra_check_status", {})).structured_content["status"] == "not_set_up"
        # A selected configuration disappearing is not a successful empty read.
        assert (await client.call_tool("fulcra_check_status", {"configuration_id": "a"})).structured_content["status"] == "unavailable"
        fake_fulcra.list_files.side_effect = RuntimeError("secret upstream error")
        result = (await client.call_tool("fulcra_check_status", {})).structured_content
        assert result == {"status": "unavailable", "label": "Status unavailable"}


async def test_configuration_selection_is_explicit_and_not_combined(fake_fulcra):
    state(fake_fulcra)
    fake_fulcra.list_files.return_value["files"].append({"id": "file-b", "path": ROOT, "name": "b.md"})
    async with Client(mcp) as client:
        choices = (await client.call_tool("fulcra_check_status", {})).structured_content
        assert choices["status"] == "choose_configuration"
        assert choices["configurations"] == ["a", "b"]
        fake_fulcra.download_file.assert_not_called()
        result = (await client.call_tool("fulcra_check_status", {"configuration_id": "b"})).structured_content
        assert result["state_path"] == ROOT + "b.md"
        fake_fulcra.download_file.assert_called_once_with("file-b")
        fake_fulcra.download_file.reset_mock()
        result = (await client.call_tool("fulcra_check_status", {"configuration_id": "../outside"})).structured_content
        assert result["status"] == "unavailable"
        fake_fulcra.download_file.assert_not_called()


@pytest.mark.parametrize("content", [b"bad state", b"x" * 1_000_001,
    b'```json\n{"version":1,"account_id":"me","task_id":null,"last_checked":null}\n```'])
async def test_malformed_truncated_or_incomplete_state(fake_fulcra, content):
    state(fake_fulcra)
    fake_fulcra.download_file.side_effect = lambda *args: io.BytesIO(content)
    async with Client(mcp) as client:
        assert (await client.call_tool("fulcra_check_status", {})).structured_content["status"] == "unavailable"


async def test_status_resolves_each_authenticated_request(monkeypatch, fake_fulcra):
    from unittest.mock import create_autospec
    from fulcra_api.core import FulcraAPI
    from fulcra_mcp import tools
    state(fake_fulcra, "2026-10-12T15:00:00Z")
    other = create_autospec(FulcraAPI, instance=True)
    other.get_fulcra_userid.return_value = "other"
    other.list_files.return_value = {"files": [], "folders": []}
    async with Client(mcp) as client:
        assert (await client.call_tool("fulcra_check_status", {})).structured_content["account_id"] == "me"
        monkeypatch.setattr(tools, "get_fulcra_object", lambda: other)
        assert (await client.call_tool("fulcra_check_status", {})).structured_content == {
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
        result = (await client.call_tool("fulcra_check_status", {})).structured_content
        assert result["status"] == "never_checked"
    assert requests == [
        ("/input/v1/file_upload", {"query": {"path": ROOT.rstrip('/'), "state": "uploaded"}}),
        ("/input/v1/file_upload/private-file/download", {"query": {}, "return_http_response": True}),
    ]
    assert stream.closed
