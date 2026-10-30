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
        "accept_agent_invitation", "match_agent_invitations", "send_agent_message", "update_data_type",
        "create_data_type", "get_data_catalog", "record_data", "get_records", "list_shares",
        "list_files", "read_file", "write_file", "delete_file", "restore_file", "open_file_manager",
        "get_groups", "join_group", "leave_group", "create_group", "get_calendar_events",
        "get_location", "get_workouts", "get_sleep", "get_time_series",
    } <= model_names
    app_only = {"prepare_agent_invitation", "prepare_standing_agent_invitation", "send_agent_contact_message",
                "set_contact_identifier", "set_contact_status", "get_contact_preferences",
                "set_contact_preferences", "get_fulcra_settings", "update_fulcra_settings"}
    assert app_only <= names
    assert not app_only & model_names
    assert {"search_agent_contacts", "get_message_check_status",
            "start_file_upload", "upload_file_chunk"} <= names
