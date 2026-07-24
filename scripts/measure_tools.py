"""Measure the context cost of this server's MCP tool definitions.

Reports the size of each tool's ``tools/list`` entry (name + description +
input schema + annotations) — the fixed context cost every MCP client pays in
every conversation — plus the total. Sizes are characters with a chars/4 token
estimate (roughly ±15%; for exact Claude numbers, run the same payload through
Anthropic's ``count_tokens`` API).

Usage:
    uv run python scripts/measure_tools.py

    # Compare against another checkout (e.g. main) by passing a directory
    # whose fulcra_mcp package should be measured instead:
    uv run python scripts/measure_tools.py /path/to/other/checkout

Use this as a regression check when adding or editing tools: if a change adds
hundreds of tokens of definitions, it should be earning them.
"""

import asyncio
import json
import sys

if len(sys.argv) > 1:
    sys.path.insert(0, sys.argv[1])

from fastmcp import Client  # noqa: E402

from fulcra_mcp.tools import tools_mcp  # noqa: E402


def tool_payload(t) -> str:
    d = {"name": t.name, "description": t.description, "input_schema": t.inputSchema}
    if t.annotations:
        d["annotations"] = t.annotations.model_dump(exclude_none=True)
    return json.dumps(d)


async def main():
    async with Client(tools_mcp) as client:
        tools = await client.list_tools()
    rows = sorted(((len(tool_payload(t)), t.name) for t in tools), reverse=True)
    total = sum(n for n, _ in rows)
    for n, name in rows:
        print(f"  {n:>6,} chars  (~{n // 4:>5,} tok)  {name}")
    print(f"TOTAL {len(rows)} tools: {total:,} chars (~{total // 4:,} tokens)")


if __name__ == "__main__":
    asyncio.run(main())
