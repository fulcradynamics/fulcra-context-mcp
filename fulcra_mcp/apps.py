"""Agents I Know MCP App; host navigation stays in registration metadata."""

from importlib.resources import files

from fastmcp import FastMCP

from mcp.types import Icon
from fulcra_mcp.settings import settings

app_mcp = FastMCP("Agents I Know UI")
# MCP Icon.theme names the host background, independent of the app's dark UI.
MENU_ICONS = [
    Icon(src=f"https://mcp.fulcradynamics.com/menu-{theme}.svg",
         mimeType="image/svg+xml", sizes=["any"], theme=theme)
    for theme in ("light", "dark")
]
UI_URI = "ui://fulcra/contacts/v71.html"
THREAD_UI_URI = "ui://fulcra/contacts/thread/v71.html"
CONTACTS_UI_URI = THREAD_UI_URI + "?startup=resource"
FULL_PANEL = {"openai/ui": {"preferredDisplayMode": "fullscreen", "availableDisplayModes": ["fullscreen"]}}


@app_mcp.tool(
    icons=MENU_ICONS,
    title="Agent Contacts",
    app={"resourceUri": THREAD_UI_URI, "visibility": ["model", "app"]},
    meta={"openai/ui": {"entrypoints": [{"type": "thread"}]}},
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
)
def agent_contact_open(peer_fulcra_userid: str | None = None, thread_id: str | None = None) -> dict:
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
def fulcra_open() -> dict[str, str]:
    """Open Agents I Know, selecting the first available contact read-only."""
    return {"message": "Agents I Know is ready."}


@app_mcp.resource(UI_URI, mime_type="text/html;profile=mcp-app", meta=FULL_PANEL)
def contacts_html_bundle() -> str:
    """Serve the packaged UI through MCP, not a separate HTTP endpoint."""
    html = files("fulcra_mcp").joinpath("ui/contacts.html").read_text(encoding="utf-8")
    # Replace the meta tag content for "chat" or "none" modes
    if settings.fulcra_contacts_controls != "full":
        html = html.replace('<meta name="connection-controls" content="full">',
                            f'<meta name="connection-controls" content="{settings.fulcra_contacts_controls}">', 1)
    # Apply debug mode setting
    html = html.replace('<meta name="connection-debug" content="true">',
                        f'<meta name="connection-debug" content="{str(settings.fulcra_contacts_debug).lower()}">', 1)
    return html
