"""Agents I Know MCP App; host navigation stays in registration metadata."""

from importlib.resources import files

from fastmcp import FastMCP

from mcp.types import Icon
from fulcra_mcp.settings import settings

app_mcp = FastMCP("Agents I Know UI")
# Use favicon.png for menu thumbnails (works on both light and dark backgrounds)
MENU_ICONS = [
    Icon(src="https://mcp.fulcradynamics.com/favicon.png",
         mimeType="image/png", sizes=["512x512"])
]
UI_URI = "ui://fulcra/contacts/v75.html"
THREAD_UI_URI = "ui://fulcra/contacts/thread/v75.html"
CONTACTS_UI_URI = THREAD_UI_URI + "?startup=resource"
FULL_PANEL = {"openai/ui": {"preferredDisplayMode": "fullscreen", "availableDisplayModes": ["fullscreen"]}}


@app_mcp.tool(
    icons=MENU_ICONS,
    title="Agent Contacts",
    app={"resourceUri": THREAD_UI_URI, "visibility": ["model", "app"]},
    meta={"openai/ui": {"entrypoints": [{"type": "thread"}]}},
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
)
def open_agent_contacts(peer_fulcra_userid: str | None = None, thread_id: str | None = None) -> dict:
    """Open Agents I Know as a full panel; omit IDs for the list and Invite someone.
    Read-only. For an exact contact, resolve contacts://threads/id- and pass its
    exact peer_fulcra_userid or discovered multiparty thread_id. Names are not IDs.
    """
    if peer_fulcra_userid is not None and not peer_fulcra_userid.strip():
        raise ValueError("Provide a nonblank exact peer user ID or omit it.")
    if thread_id is not None:
        if peer_fulcra_userid is not None or not thread_id.startswith('connection:'):
            raise ValueError('Use one exact discovered thread_id or peer user ID, not both.')
        return {"presentation": "thread", "thread_id": thread_id}
    return {"presentation": "thread", "peer_fulcra_userid": peer_fulcra_userid}


@app_mcp.resource(THREAD_UI_URI, mime_type="text/html;profile=mcp-app", meta=FULL_PANEL)
def thread_html() -> str:
    """Same full-panel renderer; startup waits for the optional exact target."""
    return contacts_html_bundle().replace('<meta name="connection-presentation" content="global">',
                               '<meta name="connection-presentation" content="thread">', 1)


@app_mcp.resource(CONTACTS_UI_URI, mime_type="text/html;profile=mcp-app", meta=FULL_PANEL)
def contacts_html() -> str:
    """Direct-resource list: no invoking tool result is required for startup."""
    return thread_html().replace('</head>', '<meta name="connection-startup" content="resource"></head>', 1)


@app_mcp.tool(
    icons=MENU_ICONS,
    title="Agents I Know",
    app={"resourceUri": UI_URI, "visibility": ["app"]},
    meta={"openai/ui": {"entrypoints": [{"type": "global"}]}},
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
)
def open_agent_contacts_home() -> dict[str, str]:
    """Open Agents I Know, selecting the first available contact read-only."""
    return {"message": "Agents I Know is ready."}


@app_mcp.resource(UI_URI, mime_type="text/html;profile=mcp-app", meta=FULL_PANEL)
def contacts_html_bundle() -> str:
    """Serve the packaged UI through MCP, not a separate HTTP endpoint."""
    html = files("fulcra_mcp").joinpath("ui/contacts.html").read_text(encoding="utf-8")
    return html.replace('<meta name="connection-debug" content="false">',
                        f'<meta name="connection-debug" content="{str(settings.fulcra_contacts_debug).lower()}">', 1)
