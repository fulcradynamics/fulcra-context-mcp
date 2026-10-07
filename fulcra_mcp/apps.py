"""Minimal MCP App; OpenAI-specific navigation stays in registration metadata."""

from importlib.resources import files

from fastmcp import FastMCP

app_mcp = FastMCP("AICQ UI")
UI_URI = "ui://aicq/hello/v7.html"


@app_mcp.tool(
    title="AICQ",
    app={"resourceUri": UI_URI, "visibility": ["app"]},
    meta={"openai/ui": {"entrypoints": [{"type": "global"}]}},
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
)
def aicq_open() -> dict[str, str]:
    """Open the AICQ Hello World app. No account data is accessed."""
    return {"message": "Hello world"}


@app_mcp.resource(
    UI_URI,
    mime_type="text/html;profile=mcp-app",
    meta={
        "openai/ui": {
            "preferredDisplayMode": "fullscreen",
            "availableDisplayModes": ["fullscreen"],
        }
    },
)
def hello_html() -> str:
    """Serve the packaged UI through MCP, not a separate HTTP endpoint."""
    return files("fulcra_mcp").joinpath("ui/hello.html").read_text(encoding="utf-8")
