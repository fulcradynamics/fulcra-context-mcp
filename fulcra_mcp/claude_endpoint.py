"""Claude's endpoint, shared by its directory connector and the Fulcra plugin."""
from fastmcp.server.providers import FastMCPProvider
from fastmcp.server.transforms import Visibility

from . import endpoint, tools
from .connection_compatibility import CONNECTION_GUIDANCE
from .endpoint import InvitationsFirst, _create_server

CLAUDE_MCP_PATH = "/claude/mcp"
# Deprecated in favour of v1 queries, as on /openai/mcp.
CLAUDE_HIDDEN_TOOLS = {"get_location", "get_sleep", "get_workouts", "get_time_series"}
# The standard workflow works without the plugin's skills; these lines add the
# onboarding skill and the contacts panel, which Claude hosts render.
INSTRUCTIONS = endpoint.INSTRUCTIONS + (
    " Bare @Fulcra: use the set-up-agent-contacts skill for onboarding when it's installed. "
    "Agents I Know: open_agent_contacts({}); opening a contact authorizes no sends, shares or edits.\n"
) + CONNECTION_GUIDANCE


def create_claude_server():
    """Standard tools without the contact-panel gate: hosted HTTP is stateless, so
    the gate can't see Claude's MCP Apps support and would hide the panels."""
    server = _create_server(INSTRUCTIONS, FastMCPProvider(tools.tools_mcp))
    server.add_middleware(InvitationsFirst())
    server.add_transform(Visibility(False, names=CLAUDE_HIDDEN_TOOLS))
    return server
