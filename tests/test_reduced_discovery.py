"""Discovery retains consolidated data tools and connection workflows."""
from fastmcp import Client

from fulcra_mcp.main import mcp


async def test_model_tool_inventory_is_not_arbitrarily_capped():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {tool.name for tool in tools}
    model_names = {
        tool.name for tool in tools
        if "model" in (tool.meta or {}).get("ui", {}).get("visibility", ["model"])
    }
    assert {
        "prepare_agent_invitation", "match_agent_invitations", "agent_connection_send",
        "agent_contact_open", "agent_contacts_open", "send_agent_message",
        "set_contact_identifier", "set_contact_status", "get_contact_preferences",
        "set_contact_preferences", "fulcra_settings_read", "fulcra_settings_update",
        "create_data_type", "get_data_catalog", "record_data", "get_records", "list_shares",
        "list_files", "read_file", "write_file", "delete_file", "restore_file", "open_file_manager",
        "get_groups", "join_group", "leave_group", "create_group", "get_calendar_events",
        "get_location", "get_workouts", "get_sleep", "get_time_series",
    } <= model_names
    assert not names & {"get_calendars", "get_location_at_time", "get_location_time_series",
                        "annotations_catalog", "delete_group", "leave_share"}
    assert {"fulcra_open", "agent_contacts_search", "fulcra_check_status",
            "start_file_upload", "upload_file_chunk"} <= names
