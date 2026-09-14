"""Mechanical checks against Anthropic's Connectors Directory review criteria.

These enforce the requirements that can be verified without live data:
annotations, name length, description quality, and docs that match each tool's
actual signature. See docs/anthropic-review.md.
"""

import inspect
import re

# The first description line is what most MCP clients show in tool summaries;
# README.md asks for roughly one short line.
MAX_LEAD_LINE = 100


async def test_every_tool_has_title_and_hint(client):
    for tool in await client.list_tools():
        ann = tool.annotations
        assert ann is not None, f"{tool.name} has no annotations"
        assert ann.title, f"{tool.name} has no title"
        assert ann.readOnlyHint is True or ann.destructiveHint is not None, (
            f"{tool.name} needs readOnlyHint or destructiveHint"
        )


async def test_tool_names_within_directory_limit(client):
    for tool in await client.list_tools():
        assert len(tool.name) <= 64, f"{tool.name} exceeds the 64-character limit"


async def test_descriptions_present_with_short_lead_line(client):
    for tool in await client.list_tools():
        assert tool.description and tool.description.strip(), (
            f"{tool.name} has no description"
        )
        lead = tool.description.strip().splitlines()[0]
        assert len(lead) <= MAX_LEAD_LINE, (
            f"{tool.name} lead description line is {len(lead)} chars: {lead!r}"
        )


async def test_every_parameter_has_a_description(client):
    """FastMCP folds each docstring Args entry into the parameter's schema
    description; a parameter without one is undocumented to the client."""
    for tool in await client.list_tools():
        for name, prop in tool.inputSchema.get("properties", {}).items():
            assert prop.get("description", "").strip(), (
                f"{tool.name}.{name} has no description — document it in the "
                "docstring's Args: section"
            )


def _documented_args(docstring: str) -> set[str]:
    """Names documented in a cleaned docstring's Args: section."""
    args: set[str] = set()
    in_args = False
    for line in docstring.splitlines():
        if line.strip() == "Args:":
            in_args = True
            continue
        if line.strip().startswith("Returns:"):
            in_args = False
            continue
        if in_args:
            # Argument entries sit at the first indent level; deeper-indented
            # lines are continuations of the previous entry.
            m = re.match(r"^    ([a-z_][a-z0-9_]*): \S", line)
            if m:
                args.add(m.group(1))
    return args


async def test_docstrings_do_not_document_missing_params():
    """A docstring documenting a parameter the function doesn't accept means
    the description no longer matches the tool's behavior."""
    from fulcra_mcp.tools import tools_mcp

    tools = await tools_mcp.list_tools()
    assert len(tools) >= 20, f"only found {len(tools)} tools; discovery is broken"
    for tool in tools:
        params = set(inspect.signature(tool.fn).parameters)
        documented = _documented_args(inspect.getdoc(tool.fn) or "")
        stale = documented - params
        assert not stale, (
            f"{tool.name} documents nonexistent args: {sorted(stale)}"
        )
