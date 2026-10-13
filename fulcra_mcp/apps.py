"""Fulcra Mesh MCP App; host navigation stays in registration metadata."""

from importlib.resources import files

from fastmcp import FastMCP

app_mcp = FastMCP("Fulcra Mesh UI")
UI_URI = "ui://fulcra/mesh/v40.html"
THREAD_UI_URI = "ui://fulcra/mesh/thread/v40.html"
THREADS_UI_URI = "ui://fulcra/mesh/threads/v40.html"
MESHES_UI_URI = THREADS_UI_URI + "?startup=resource"


@app_mcp.tool(
    title="Mesh threads",
    app={"resourceUri": THREADS_UI_URI, "visibility": ["model", "app"]},
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
)
def mesh_threads_open() -> dict[str, str]:
    """Show clickable Mesh threads in chat. Select a peer to request a conversation panel.

    Does not write account data or send messages.
    Use for a bare Fulcra mention or a submitted List Meshes mention unless the
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
    return mesh_html().replace('<meta name="mesh-presentation" content="global">',
                               '<meta name="mesh-presentation" content="threads">', 1)


@app_mcp.resource(
    MESHES_UI_URI,
    mime_type="text/html;profile=mcp-app",
    meta={"openai/ui": {"preferredDisplayMode": "inline", "availableDisplayModes": ["inline", "fullscreen"]}},
)
def meshes_html() -> str:
    """Direct-resource variant: no invoking tool result is required for startup."""
    return threads_html().replace('</head>', '<meta name="mesh-startup" content="resource"></head>', 1)


@app_mcp.tool(
    title="Mesh conversation",
    app={"resourceUri": THREAD_UI_URI, "visibility": ["model", "app"]},
    meta={"openai/ui": {"entrypoints": [{"type": "thread"}]}},
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
)
def mesh_conversation_open(peer_fulcra_userid: str | None = None, thread_id: str | None = None) -> dict:
    """Open a Mesh conversation with an exact peer ID or discovered multiparty thread_id.

    Omit both IDs to choose a thread. Accessible audiences are discovered by the app;
    names are not identifiers. Does not write account data or send messages.
    Use for a submitted Open Mesh: mention after resolving its exact peer ID.
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
    return mesh_html().replace('<meta name="mesh-presentation" content="global">',
                               '<meta name="mesh-presentation" content="thread">', 1)


@app_mcp.tool(
    title="Fulcra Mesh",
    app={"resourceUri": UI_URI, "visibility": ["app"]},
    meta={"openai/ui": {"entrypoints": [{"type": "global"}]}},
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
)
def aicq_open() -> dict[str, str]:
    """Open Fulcra Mesh to browse peer threads and ask your agent to help.

    This entrypoint does not access account data; the app loads shared channels
    after connecting.
    """
    return {"message": "Fulcra Mesh is ready."}


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
def mesh_html() -> str:
    """Serve the packaged UI through MCP, not a separate HTTP endpoint."""
    return files("fulcra_mcp").joinpath("ui/mesh.html").read_text(encoding="utf-8")
