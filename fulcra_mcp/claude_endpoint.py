"""Claude's endpoint, shared by its directory connector and the Fulcra plugin."""
import copy

from fastmcp.server.providers import FastMCPProvider
from fastmcp.server.transforms import Transform, Visibility

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

# Claude's directory review wants an annotation title on every tool and a
# description on every parameter. These shared tools lack them; they're added
# here so the other endpoints' metadata stays as it is.
DIRECTORY_TITLES = {
    "open_agent_contacts": "Agent Contacts",
    "open_agent_contacts_home": "Agents I Know",
    "search_agent_contacts": "Search Agent Contact mentions",
    "get_fulcra_settings": "Get Fulcra Settings",
    "update_fulcra_settings": "Update Fulcra Settings",
    "get_contact_preferences": "Get Contact Preferences",
    "set_contact_preferences": "Set Contact Preferences",
    "get_message_check_status": "Get Message Check Status",
}
_CHANNEL = "Your own connection channel, as Event/<UUID>."
_PEER = "The peer's exact Fulcra user ID."
_EXPECTED_PEERS = ("Every peer the channel is shared with, for a multiparty connection. "
                   "Defaults to just peer_userid.")
DIRECTORY_ARGUMENTS = {
    "open_agent_contacts": {
        "peer_fulcra_userid": "The exact Fulcra user ID of one contact to open.",
        "thread_id": "A discovered multiparty thread ID (connection:...), instead of peer_fulcra_userid.",
    },
    "search_agent_contacts": {"query": "Text to match against contact names; empty matches all."},
    "update_fulcra_settings": {
        "set": "Preference names and their new values, as get_fulcra_settings describes them.",
    },
    "get_contact_preferences": {
        "data_type": _CHANNEL, "peer_userid": _PEER, "expected_peer_userids": _EXPECTED_PEERS,
    },
    "set_contact_preferences": {
        "data_type": _CHANNEL, "peer_userid": _PEER, "expected_peer_userids": _EXPECTED_PEERS,
        "overrides": "Preference names and values that replace this contact's overrides; {} removes them all.",
    },
    "get_message_check_status": {
        "configuration_id": "A configuration from the choices this returns without one.",
    },
}


class DirectoryMetadata(Transform):
    """Add the missing titles and parameter descriptions to copies of the tools,
    leaving the shared tool objects unchanged."""

    @staticmethod
    def _complete(tool):
        title = DIRECTORY_TITLES.get(tool.name)
        arguments = DIRECTORY_ARGUMENTS.get(tool.name, {})
        update = {}
        if title is not None and not tool.annotations.title:
            update["annotations"] = tool.annotations.model_copy(update={"title": title})
        if arguments:
            parameters = copy.deepcopy(tool.parameters)
            for name, description in arguments.items():
                parameters["properties"][name].setdefault("description", description)
            update["parameters"] = parameters
        return tool.model_copy(update=update) if update else tool

    async def list_tools(self, tools):
        return [self._complete(tool) for tool in tools]

    async def get_tool(self, name, call_next, *, version=None):
        tool = await call_next(name, version=version)
        return tool if tool is None else self._complete(tool)


def create_claude_server():
    """Standard tools without the contact-panel gate: hosted HTTP is stateless, so
    the gate can't see Claude's MCP Apps support and would hide the panels."""
    server = _create_server(INSTRUCTIONS, FastMCPProvider(tools.tools_mcp))
    server.add_middleware(InvitationsFirst())
    server.add_transform(Visibility(False, names=CLAUDE_HIDDEN_TOOLS))
    server.add_transform(DirectoryMetadata())
    return server
