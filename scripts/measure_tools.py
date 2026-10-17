"""Measure the context cost of this server's MCP tool definitions.

Reports the size of each tool's ``tools/list`` entry (name + description +
input schema + annotations) — the fixed context cost every MCP client pays in
every conversation — plus the total. App-only tools (MCP Apps
``visibility: ["app"]``) are totalled separately: hosts that show MCP Apps hide
them from the model, though clients without MCP Apps still list them. Sizes are
characters with a chars/4 token estimate (roughly ±15%; for exact Claude
numbers, run the same payload through Anthropic's ``count_tokens`` API).

It measures the hosted server's tool list (FULCRA_ENVIRONMENT=prod) unless
FULCRA_ENVIRONMENT is set, then lists the tools only a local stdio server adds,
such as debug_token_info.

Usage:
    uv run python scripts/measure_tools.py
    FULCRA_ENVIRONMENT=stdio uv run python scripts/measure_tools.py   # local server

    # Compare against another checkout (e.g. main) by passing a directory
    # whose fulcra_mcp package should be measured instead:
    uv run python scripts/measure_tools.py /path/to/other/checkout

Use this as a regression check when adding or editing tools: if a change adds
hundreds of tokens of definitions, it should be earning them.
"""

import asyncio
import json
import os
import subprocess
import sys

# Internal: print the model-visible tool sizes as JSON, for the stdio comparison.
JSON_FLAG = "--json"
args = [a for a in sys.argv[1:] if a != JSON_FLAG]
if args:
    sys.path.insert(0, args[0])

# Some tools are registered only for a local stdio server; measure what the
# hosted server lists unless told otherwise. Settings read this on import.
ENVIRONMENT = os.environ.setdefault("FULCRA_ENVIRONMENT", "prod")

from fastmcp import Client  # noqa: E402

from fulcra_mcp.tools import tools_mcp  # noqa: E402


def tool_payload(t) -> str:
    d = {"name": t.name, "description": t.description, "input_schema": t.inputSchema}
    if t.annotations:
        d["annotations"] = t.annotations.model_dump(exclude_none=True)
    return json.dumps(d)


def app_only(t) -> bool:
    """An MCP Apps tool that only its panel calls. Hosts that show MCP Apps keep
    it out of the model's tool list; other clients list it like any tool."""
    visibility = ((t.meta or {}).get("ui") or {}).get("visibility")
    return visibility is not None and "model" not in visibility


def report(label: str, tools) -> None:
    rows = sorted(((len(tool_payload(t)), t.name) for t in tools), reverse=True)
    total = sum(n for n, _ in rows)
    for n, name in rows:
        print(f"  {n:>6,} chars  (~{n // 4:>5,} tok)  {name}")
    print(f"{label} {len(rows)} tools: {total:,} chars (~{total // 4:,} tokens)")


def stdio_only(hosted_names: set[str]) -> dict[str, int]:
    """The model-visible tools a local stdio server adds, with their sizes."""
    out = subprocess.run(
        [sys.executable, __file__, *args, JSON_FLAG],
        env={**os.environ, "FULCRA_ENVIRONMENT": "stdio"},
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {name: n for name, n in json.loads(out).items() if name not in hosted_names}


async def main():
    async with Client(tools_mcp) as client:
        tools = await client.list_tools()
    visible = [t for t in tools if not app_only(t)]
    if JSON_FLAG in sys.argv:
        print(json.dumps({t.name: len(tool_payload(t)) for t in visible}))
        return
    where = "a local stdio server" if ENVIRONMENT == "stdio" else "the hosted server"
    print(f"Measured as {where} (FULCRA_ENVIRONMENT={ENVIRONMENT}).")
    report("TOTAL", visible)
    if panel := [t for t in tools if app_only(t)]:
        print("\nApp-only (hidden from the model in hosts that show MCP Apps):")
        report("APP-ONLY", panel)
    if ENVIRONMENT != "stdio" and (extra := stdio_only({t.name for t in visible})):
        print("\nOnly on a local stdio server (not counted above):")
        for name, n in sorted(extra.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>6,} chars  (~{n // 4:>5,} tok)  {name}")


if __name__ == "__main__":
    asyncio.run(main())
