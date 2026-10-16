"""Agents I Know MCP App; host navigation stays in registration metadata."""

from importlib.resources import files

from fastmcp import FastMCP

from fulcra_mcp import server_info

app_mcp = FastMCP("Agents I Know UI")
UI_URI = "ui://fulcra/contacts/v54.html"
THREAD_UI_URI = "ui://fulcra/contacts/thread/v54.html"
THREADS_UI_URI = "ui://fulcra/contacts/threads/v54.html"
CONTACTS_UI_URI = THREADS_UI_URI + "?startup=resource"


@app_mcp.tool(
    icons=server_info.icons(),
    title="Agents I Know",
    app={"resourceUri": THREADS_UI_URI, "visibility": ["model", "app"]},
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
)
def agent_contacts_open() -> dict[str, str]:
    """Show clickable Agents I Know in chat. Select a peer to request a conversation panel.

    Does not write account data or send messages.
    Use for a bare Fulcra mention or a submitted Agents I Know mention unless the
    user asks for another task.
    """
    return {"presentation": "threads"}


@app_mcp.resource(
    THREADS_UI_URI,
    mime_type="text/html;profile=mcp-app",
    meta={"openai/ui": {"preferredDisplayMode": "inline", "availableDisplayModes": ["inline", "fullscreen"]}},
)
def threads_html() -> str:
    """Same compiled app, initially a compact thread list."""
    return contacts_html_bundle().replace('<meta name="connection-presentation" content="global">',
                               '<meta name="connection-presentation" content="threads">', 1)


@app_mcp.resource(
    CONTACTS_UI_URI,
    mime_type="text/html;profile=mcp-app",
    meta={"openai/ui": {"preferredDisplayMode": "inline", "availableDisplayModes": ["inline", "fullscreen"]}},
)
def contacts_html() -> str:
    """Direct-resource variant: no invoking tool result is required for startup."""
    return threads_html().replace('</head>', '<meta name="connection-startup" content="resource"></head>', 1)


@app_mcp.tool(
    icons=server_info.icons(),
    title="Agent Contacts",
    app={"resourceUri": THREAD_UI_URI, "visibility": ["model", "app"]},
    meta={"openai/ui": {"entrypoints": [{"type": "thread"}]}},
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
)
def agent_contact_open(peer_fulcra_userid: str | None = None, thread_id: str | None = None) -> dict:
    """Open an Agent Contact with an exact peer ID or discovered multiparty thread_id.

    Omit both IDs to choose an Agent Contact. Accessible audiences are discovered by the app;
    names are not identifiers. Does not write account data or send messages.
    Use for a submitted Open Agent Contact: mention after resolving its exact peer ID.
    """
    if peer_fulcra_userid is not None and not peer_fulcra_userid.strip():
        raise ValueError("Provide a nonblank exact peer user ID or omit it.")
    if thread_id is not None:
        if peer_fulcra_userid is not None or not thread_id.startswith('connection:'):
            raise ValueError('Use one exact discovered thread_id or peer user ID, not both.')
        return {"presentation": "thread", "thread_id": thread_id}
    return {"presentation": "thread", "peer_fulcra_userid": peer_fulcra_userid}


@app_mcp.resource(
    THREAD_UI_URI,
    mime_type="text/html;profile=mcp-app",
    meta={"openai/ui": {"preferredDisplayMode": "fullscreen", "availableDisplayModes": ["fullscreen", "pip"]}},
)
def thread_html() -> str:
    """Same compiled app; presentation is fixed by the server resource."""
    return contacts_html_bundle().replace('<meta name="connection-presentation" content="global">',
                               '<meta name="connection-presentation" content="thread">', 1)


@app_mcp.tool(
    icons=server_info.icons(),
    title="Agents I Know",
    app={"resourceUri": UI_URI, "visibility": ["app"]},
    meta={"openai/ui": {"entrypoints": [{"type": "global"}]}},
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
)
def fulcra_open() -> dict[str, str]:
    """Open Agents I Know to browse peer threads and ask your agent to help.

    This entrypoint does not access account data; the app loads shared channels
    after connecting.
    """
    return {"message": "Agents I Know is ready."}


@app_mcp.resource(
    UI_URI,
    mime_type="text/html;profile=mcp-app",
    meta={
        "openai/ui": {
            "preferredDisplayMode": "fullscreen",
            "availableDisplayModes": ["fullscreen", "pip"],
        }
    },
)
def contacts_html_bundle() -> str:
    """Serve the packaged UI through MCP, not a separate HTTP endpoint."""
    return files("fulcra_mcp").joinpath("ui/contacts.html").read_text(encoding="utf-8")
