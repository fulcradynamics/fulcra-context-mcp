"""Every released MCP App UI version stays readable at its original URI.

A host can store a tool's ``ui.resourceUri`` when a connector or plugin is
published, and keep requesting that URI long after this server has moved to a
newer one. The published ChatGPT app did: it asked for contacts v82 once v83
had shipped and got "Unknown resource", so the panel never opened.

So a version is never removed. ``fulcra_mcp/ui/<app>/v<N>.html`` holds each
one. Tools and ``resources/list`` advertise only the current version; the
earlier ones are registered as resources that can be read but aren't listed.
"""

import re
from collections.abc import Callable
from importlib.resources import files
from importlib.resources.abc import Traversable

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware

EARLIER_VERSION = "earlier-ui-version"


def bundles(app: str) -> dict[int, Traversable]:
    """The packaged ``ui/<app>/v<N>.html`` files, by N."""
    folder = files("fulcra_mcp").joinpath("ui", app)
    if not folder.is_dir():
        return {}
    return {
        int(match[1]): entry
        for entry in folder.iterdir()
        if (match := re.fullmatch(r"v(\d+)\.html", entry.name))
    }


def keep_readable(server: FastMCP, uri: str, read: Callable[[], str], **options) -> None:
    """Serve an earlier version at `uri` without listing it."""

    def earlier_version() -> str:
        return read()

    server.resource(
        uri,
        name=f"Earlier version: {uri}",
        description="Kept for hosts that stored this URI. Superseded by the listed version.",
        tags={EARLIER_VERSION},
        **options,
    )(earlier_version)


class CurrentVersionsOnly(Middleware):
    """Leave earlier versions out of resources/list; reads don't go through it."""

    async def on_list_resources(self, context, call_next):
        return [r for r in await call_next(context) if EARLIER_VERSION not in r.tags]
