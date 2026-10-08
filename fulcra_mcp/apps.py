"""Fulcra Mesh MCP App; host navigation stays in registration metadata."""

from importlib.resources import files

from fastmcp import FastMCP

app_mcp = FastMCP("Fulcra Mesh UI")
UI_URI = "ui://fulcra/mesh/v14.html"


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
