"""Hosted discovery annotations describe all supported branches, including app tools."""

import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# Bounded private reads are closed-world even when the account is hosted.
READS = set("""
get_workouts get_data_catalog get_time_series get_records get_data_updates
get_sleep get_location get_calendar_events list_files list_shares get_user_info
open_file_manager open_agent_contacts open_agent_contacts_home search_agent_contacts
get_fulcra_settings get_contact_preferences get_message_check_status get_groups read_file
""".split())
# Additive operations do not carry the destructive hint.
ADDITIVE = set("""
create_data_type restore_data_type prepare_agent_invitation create_group
record_data write_file restore_file create_share join_group
start_file_upload upload_file_chunk
""".split())
# Preparation only adds a private code; standing preparation can overwrite a
# saved name. Matching creates return grants, unlike read-only contact discovery.
# Both send interfaces are destructive because a sent message cannot be unsent.
DESTRUCTIVE = set("""
update_data_type send_agent_message send_agent_contact_message end_agent_contact set_contact_identifier
set_contact_status archive_data_type delete_records create_agent_invitation
prepare_standing_agent_invitation match_agent_invitations delete_file delete_share
leave_group update_fulcra_settings set_contact_preferences
""".split())
# Public group queries are open-world despite being read-only. Existing-channel
# sends remain bounded by verified grants, unlike new arbitrary share recipients.
OPEN_WORLD = {"get_groups", "create_group", "join_group", "leave_group", "create_share",
              "create_agent_invitation", "match_agent_invitations"}


async def test_composed_hosted_annotations_over_json_transport():
    # conftest imports stdio settings; use a fresh process for hosted composition,
    # but a local JSON transport: no production server or account calls.
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from fulcra_mcp.main import mcp; mcp.run(transport='stdio', show_banner=False)"],
        env={**os.environ, "FULCRA_ENVIRONMENT": "prod"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
    assert result.nextCursor is None
    tools = {tool.name: tool for tool in result.tools}
    assert len(tools) == len(result.tools)
    assert set(tools) == READS | ADDITIVE | DESTRUCTIVE
    assert "debug_token_info" not in tools
    for name, tool in tools.items():
        # exclude_unset checks fields decoded from JSON, not Pydantic defaults.
        assert tool.annotations is not None, name
        annotations = tool.annotations.model_dump(exclude_unset=True)
        expected = {"readOnlyHint": name in READS,
                    "destructiveHint": name in DESTRUCTIVE,
                    "openWorldHint": name in OPEN_WORLD}
        for flag, value in expected.items():
            assert type(annotations.get(flag)) is bool, (name, flag, annotations)
            assert annotations[flag] is value, (name, flag, annotations)
