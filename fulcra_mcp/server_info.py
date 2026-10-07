"""The server's identity, kept in step with server.json (PLAT-617).

server.json at the repo root is the source of truth: the MCP Registry publishes
it, and the Server Card served at /mcp/server-card is built from it. The
hosted image includes it (the Dockerfile copies the whole repo). A PyPI install
doesn't, so there serverInfo falls back to the name and package version alone.

Server Cards: SEP-2127 and https://github.com/modelcontextprotocol/ext-server-card
"""

import json
from functools import cache
from importlib import metadata
from pathlib import Path

from mcp.types import Icon

PACKAGE = "fulcra-context-mcp"
SERVER_JSON = Path(__file__).resolve().parents[1] / "server.json"

# What clients display. The MCP spec intends serverInfo.name for programs and
# `title` for people, but FastMCP 3.x can't set a title, and clients fall back
# to showing the name. Until it can, the name is server.json's title (a test
# keeps the two equal); then it becomes server.json's `name`.
DISPLAY_NAME = "Fulcra"

SERVER_CARD_SCHEMA = "https://static.modelcontextprotocol.io/schemas/v1/server-card.schema.json"
SERVER_CARD_MEDIA_TYPE = "application/mcp-server-card+json"

# The Server Card fields copied from server.json. The card leaves out
# `packages`: install details belong to the registry, not the card.
CARD_FIELDS = ("name", "title", "description", "websiteUrl", "repository", "icons", "remotes")


def version() -> str:
    """The installed package's version, which is also the server's version."""
    return metadata.version(PACKAGE)


@cache
def server_json() -> dict | None:
    try:
        return json.loads(SERVER_JSON.read_text())
    except FileNotFoundError:
        return None


def website_url() -> str | None:
    return (server_json() or {}).get("websiteUrl")


def icons() -> list[Icon] | None:
    listed = (server_json() or {}).get("icons")
    return [Icon(**icon) for icon in listed] if listed else None


def server_card() -> dict:
    """The Server Card for the hosted server, built from server.json."""
    data = server_json()
    if data is None:
        raise FileNotFoundError(f"{SERVER_JSON} is needed to build the Server Card")
    card = {"$schema": SERVER_CARD_SCHEMA}
    for field in CARD_FIELDS:
        if field in data:
            card[field] = data[field]
    card["version"] = version()
    return card
