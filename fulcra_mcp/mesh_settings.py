"""Read-only projection of private ChatGPT mesh-check state for settings."""

import json
import re
from datetime import datetime, timezone
from importlib.resources import files

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from . import tools

settings_mcp = FastMCP("Mesh check settings")
STATE_ROOT = "/agent/chatgpt/mesh-checks/"
SETTINGS_URI = "ui://fulcra/mesh/settings/v1.html"
READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
SETTINGS_OUTPUT = {
    "type": "object", "properties": {
        "schema": {"type": "object"}, "values": {"type": "object"},
        "layout": {"type": "array", "items": {"type": "object"}},
    }, "required": ["schema", "values", "layout"],
}


def check_status(configuration_id: str | None = None) -> dict:
    """Never cache account state or return pending/reported message contents."""
    try:
        fulcra = tools.get_fulcra_object()
        account = fulcra.get_fulcra_userid()
        if not isinstance(account, str) or not account:
            raise ValueError("Missing account")
        listing = fulcra.list_files(STATE_ROOT.rstrip("/"))
        records = {f["name"][:-3]: f for f in listing["files"]
                   if f["name"].endswith(".md")}
        if not records:
            if configuration_id is not None:
                raise ValueError("Configuration unavailable")
            return {"status": "not_set_up", "label": "Not set up"}
        if configuration_id is None:
            if len(records) > 1:
                return {"status": "choose_configuration", "label": "Choose a configuration",
                        "configurations": sorted(records)}
            configuration_id = next(iter(records))
        if not isinstance(configuration_id, str) or configuration_id not in records:
            raise ValueError("Configuration unavailable")
        record = records[configuration_id]
        with fulcra.download_file(record["id"]) as response:
            data = response.read(1_000_001)
        if len(data) > 1_000_000:
            raise ValueError("State exceeds status reader limit")
        blocks = re.findall(r"^```json\s*\n(.*?)^```\s*$", data.decode("utf-8"), re.M | re.S)
        if len(blocks) != 1:
            raise ValueError("Invalid state")
        state = json.loads(blocks[0])
        if type(state["version"]) is not int or state["version"] != 1 or state["account_id"] != account:
            raise ValueError("Invalid state identity")
        start = datetime.fromisoformat(state["start_time"].replace("Z", "+00:00"))
        if start.tzinfo is None or not isinstance(state["agent_name"], str) or not state["agent_name"].strip():
            raise ValueError("Invalid configuration")
        if state["scope"] is None or not isinstance(state["pending"], list) or not isinstance(state["reported"], list):
            raise ValueError("Incomplete state")
        last = state["last_checked"]
        task = state["task_id"]
        if task is not None and (not isinstance(task, str) or not task.strip()):
            raise ValueError("Invalid task reference")
        label = "Never checked"
        if last is not None:
            timestamp = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("Missing timezone")
            last = timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            label = last
        return {"status": "checked" if last else "never_checked", "label": label,
                "configuration_id": configuration_id, "account_id": account,
                "state_path": STATE_ROOT + configuration_id + ".md",
                "task_id": task, "last_checked": last}
    except Exception:
        # Do not return upstream errors: they may contain credentials or file data.
        return {"status": "unavailable", "label": "Status unavailable"}


@settings_mcp.tool(app={"visibility": ["app"]}, annotations=READ_ONLY,
                   output_schema=SETTINGS_OUTPUT)
def aicq_settings_read() -> dict:
    """Read mesh check status and the settings action; no editable scheduler values."""
    status = check_status()
    return {"schema": {"type": "object", "properties": {}}, "values": {},
            "layout": [{"kind": "group", "title": "Mesh checks", "items": [
                {"kind": "tool", "tool": "aicq_schedule_settings",
                 "description": "Last mesh check: " + status["label"]}]}]}


@settings_mcp.tool(app={"visibility": ["app"]}, annotations=READ_ONLY)
def aicq_settings_update(set: dict) -> dict:
    """Reject edits: cadence is managed through the host's existing task in chat."""
    raise ToolError("No editable settings. Use Reschedule checks in Chat to manage the existing task.")


@settings_mcp.tool(title="Mesh check settings", annotations=READ_ONLY,
                   app={"resourceUri": SETTINGS_URI, "visibility": ["app"]})
def aicq_schedule_settings() -> dict:
    """Open read-only check status and an explicit schedule-management chat handoff."""
    return check_status()


@settings_mcp.tool(app={"visibility": ["app"]}, annotations=READ_ONLY)
def aicq_check_status(configuration_id: str | None = None) -> dict:
    """Read a selected private check configuration; omit the ID to discover choices."""
    return check_status(configuration_id)


@settings_mcp.resource(SETTINGS_URI, mime_type="text/html;profile=mcp-app")
def settings_html() -> str:
    """Serve the bundled settings modal without account data embedded in the HTML."""
    return files("fulcra_mcp").joinpath("ui/mesh-settings.html").read_text(encoding="utf-8")
