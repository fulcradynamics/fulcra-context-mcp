"""Trim what every client pays for this server's tool list and results.

Two things FastMCP adds by default cost context without telling a model
anything:

* A tool that returns a string gets an output schema of ``{"result": string}``,
  and each call then returns its text twice: once as ``content`` and again as
  ``structuredContent``. Dropping that schema leaves the text once. Tools that
  return objects (such as the file manager's upload tools) keep theirs.
* An optional parameter is advertised as
  ``{"anyOf": [{"type": "string"}, {"type": "null"}], "default": null}``.
  Advertising just ``{"type": "string"}`` says the same to a model: it's
  optional because it isn't listed in ``required``. Arguments are still
  validated against each tool function's own signature, which accepts null.
"""

from collections.abc import Sequence
from typing import Any

from fastmcp.server.transforms import GetToolNext, Transform
from fastmcp.tools import Tool

NULL = {"type": "null"}


def compact_schema(schema: Any) -> Any:
    """``schema`` with every nullable ``anyOf`` of one other type replaced by
    that type, and every ``"default": null`` dropped."""
    if isinstance(schema, list):
        return [compact_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    out = {key: compact_schema(value) for key, value in schema.items()}
    options = out.get("anyOf")
    if isinstance(options, list) and len(options) == 2 and NULL in options:
        [other] = [option for option in options if option != NULL]
        if isinstance(other, dict) and not set(other) & set(out):
            del out["anyOf"]
            out.update(other)
    if "default" in out and out["default"] is None:
        del out["default"]
    return out


def compact_tool(tool: Tool) -> Tool:
    update: dict[str, Any] = {"parameters": compact_schema(tool.parameters)}
    if tool.output_schema and tool.output_schema.get("x-fastmcp-wrap-result"):
        update["output_schema"] = None
    return tool.model_copy(update=update)


class CompactTools(Transform):
    """Applies compact_tool to tools as they're listed and as they're called,
    so a call returns text without the duplicate structured copy."""

    async def list_tools(self, tools: Sequence[Tool]) -> Sequence[Tool]:
        return [compact_tool(tool) for tool in tools]

    async def get_tool(self, name: str, call_next: GetToolNext, *, version=None) -> Tool | None:
        tool = await call_next(name, version=version)
        return compact_tool(tool) if tool is not None else None
