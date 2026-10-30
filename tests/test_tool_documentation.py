"""Protect released names and keep public references aligned with discovery."""
from pathlib import Path

from fastmcp import Client

from fulcra_mcp.main import mcp


# Released hosted model surface, captured from composed MCP discovery.
RELEASED_MODEL_TOOLS = set("""
archive_data_type create_data_type create_group create_share delete_file
 delete_records delete_share get_calendar_events get_data_catalog get_data_updates
 get_groups get_location get_records get_sleep get_time_series get_user_info
 get_workouts join_group leave_group list_files list_shares open_file_manager
 read_file record_data restore_data_type restore_file send_agent_message write_file
""".split())
RELEASED_APP_TOOLS = {"start_file_upload", "upload_file_chunk"}
LOCAL_TOOLS = {"debug_token_info"}
ROOT = Path(__file__).resolve().parents[1]


async def discovered_tools():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    model = {
        t.name for t in tools
        if "model" in (t.meta or {}).get("ui", {}).get("visibility", ["model"])
    }
    return model, {t.name for t in tools} - model


async def test_released_tool_names_keep_their_visibility():
    model, app = await discovered_tools()
    assert RELEASED_MODEL_TOOLS | LOCAL_TOOLS <= model
    assert RELEASED_APP_TOOLS <= app


async def test_public_summaries_cover_model_additions():
    model, _ = await discovered_tools()
    added = model - RELEASED_MODEL_TOOLS - LOCAL_TOOLS
    assert added  # Do not silently pass after a discovery failure.
    for path in ("README.md", "AGENTS.md"):
        text = (ROOT / path).read_text()
        for name in added:
            reference = text
            if path == 'AGENTS.md' and name in {'accept_agent_invitation', 'match_agent_invitations'}:
                reference = (ROOT / 'docs/native-invitations.md').read_text()
            assert f"`{name}`" in reference, (path, name)
