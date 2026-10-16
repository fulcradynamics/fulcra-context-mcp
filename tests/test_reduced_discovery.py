"""Temporary discovery experiment; revert with the server visibility filter."""
from fastmcp import Client

from fulcra_mcp.main import mcp


async def test_reduced_model_tool_inventory():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {tool.name for tool in tools}
    model_names = {
        tool.name for tool in tools
        if "model" in (tool.meta or {}).get("ui", {}).get("visibility", ["model"])
    } - {"debug_token_info"}  # Local stdio diagnostic is never hosted.
    assert len(model_names) == 32, sorted(model_names)
    assert {
        "prepare_agent_invitation", "match_agent_invitations", "agent_connection_send",
        "create_data_type", "record_data", "get_records", "list_shares",
        "list_files", "read_file", "write_file", "open_file_manager", "restore_file",
    } <= model_names
    assert not names & {
        "get_groups", "join_group", "leave_group", "create_group", "delete_group",
        "get_calendars", "get_calendar_events", "get_location_at_time",
        "get_location_time_series", "get_workouts", "get_sleep",
        "get_time_series",
    }
    assert {"fulcra_open", "agent_contacts_search", "fulcra_check_status",
            "start_file_upload", "upload_file_chunk"} <= names
