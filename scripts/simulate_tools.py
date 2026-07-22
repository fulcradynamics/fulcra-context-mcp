#!/usr/bin/env python3
"""Simulate what an agent actually sees of your MCP tool descriptions.
 
Reproduces the three progressively-detailed views observed in Claude's
client during a live session (July 2026):
 
  1. DIRECTORY view — the deferred-tool listing an agent sees before
     loading anything: one line per tool, first physical line of the
     description (split at the first newline), char-capped with an
     ellipsis.
  2. SEARCH view — what a tool-search result shows: tool name plus a
     compact parameter listing, where each param description is ALSO
     truncated to its first line and char-capped.
  3. FULL view — the complete JSON schema (what your FastMCP client
     shows you, and what the agent only gets after loading the tool).
 
IMPORTANT CAVEAT: views 1–2 reproduce one client's observed behavior at
one point in time — they are not a spec. Other clients (and future
versions of the same client) compress differently. The durable fix is
PEP-257 style: a complete, self-contained summary sentence on line one,
under the char cap, for every tool AND every parameter description.
 
Usage (this repo — main.py uses relative imports, so launch via the
entry point rather than the file path):
    FULCRA_ENVIRONMENT=stdio uv run python scripts/simulate_tools.py \
        --command "uv run fulcra-context-mcp"
    ... --view search
    ... --lint          # CI-friendly

Generic usage:
    python simulate_tools.py server.py                 # stdio server
    python simulate_tools.py http://localhost:8000/mcp # HTTP server
 
Exit code is nonzero in --lint mode if any first line fails the checks,
so you can wire this into CI to stop truncation regressions.
"""

import argparse
import asyncio
import json
import shlex
import sys

try:
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport
except ImportError:
    sys.exit("fastmcp not installed: pip install fastmcp")

# Observed caps in the wild. Not a spec — tune with --width.
DIRECTORY_WIDTH = 80
PARAM_WIDTH = 70
ELLIPSIS = "\u2026"


def first_line(text: str) -> str:
    """The only part of a description guaranteed to survive compaction."""
    return (text or "").split("\n")[0].strip()


def clip(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: width - 1].rstrip() + ELLIPSIS


def agent_line(text: str, width: int) -> str:
    """First line, then char cap — the observed order of operations."""
    return clip(first_line(text), width)


def iter_params(tool):
    """Yield (name, type, description, required) from a tool's inputSchema."""
    schema = getattr(tool, "inputSchema", None) or {}
    required = set(schema.get("required", []))
    for pname, pschema in (schema.get("properties") or {}).items():
        ptype = pschema.get("type") or ("any" if "anyOf" in pschema else "object")
        yield pname, ptype, pschema.get("description", ""), pname in required


def show_directory(tools, width):
    print(f"=== DIRECTORY VIEW (first line, capped at {width}) ===\n")
    for t in tools:
        print(f"  {t.name} \u2014 {agent_line(t.description or '', width)}")
    print()


def show_search(tools, width, param_width):
    print("=== SEARCH VIEW (per-tool compact schema) ===\n")
    for t in tools:
        print(f"  {t.name}: {agent_line(t.description or '', width)}")
        for pname, ptype, pdesc, req in iter_params(t):
            opt = "" if req else "?"
            print(f"    {pname}{opt}: {ptype} - {agent_line(pdesc, param_width)}")
        print()


def show_full(tools):
    print("=== FULL VIEW (what your fastmcp client shows) ===\n")
    for t in tools:
        print(f"### {t.name}")
        print(t.description or "(no description)")
        print(json.dumps(getattr(t, "inputSchema", {}), indent=2))
        print()


def lint(tools, width, param_width):
    """Flag first lines that truncate badly. Returns number of problems."""
    problems = []

    def check(owner, text, cap):
        fl = first_line(text)
        if not fl:
            problems.append(f"{owner}: empty description")
            return
        if len(fl) > cap:
            problems.append(
                f"{owner}: first line is {len(fl)} chars (cap {cap}); "
                f'agents see: "{clip(fl, cap)}"'
            )
        elif fl[-1] not in ".!?)":
            # A first line that doesn't end a sentence usually means the
            # docstring is hard-wrapped and the thought continues on line
            # 2 — i.e. the agent sees a fragment.
            problems.append(f'{owner}: first line ends mid-thought: "{fl}"')

    for t in tools:
        check(t.name, t.description or "", width)
        for pname, _ptype, pdesc, _req in iter_params(t):
            if pdesc:
                check(f"{t.name}.{pname}", pdesc, param_width)

    if problems:
        print(f"LINT: {len(problems)} first-line problem(s):\n")
        for p in problems:
            print(f"  \u2717 {p}")
    else:
        print("LINT: all first lines are self-contained. \u2713")
    return len(problems)


async def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("server", nargs="?", help="stdio script path or http(s) URL")
    ap.add_argument(
        "--command",
        help="stdio command to launch the server "
        "(e.g. 'uv run fulcra-context-mcp'); overrides the positional arg",
    )
    ap.add_argument(
        "--view",
        choices=["directory", "search", "full", "all"],
        default="all",
    )
    ap.add_argument("--width", type=int, default=DIRECTORY_WIDTH)
    ap.add_argument("--param-width", type=int, default=PARAM_WIDTH)
    ap.add_argument(
        "--lint",
        action="store_true",
        help="run first-line checks; nonzero exit on problems",
    )
    args = ap.parse_args()

    if args.command:
        cmd, *cmd_args = shlex.split(args.command)
        target = StdioTransport(cmd, cmd_args)
    elif args.server:
        target = args.server
    else:
        ap.error("provide a server spec or --command")

    async with Client(target) as client:
        tools = sorted(await client.list_tools(), key=lambda t: t.name)

    if args.lint:
        sys.exit(1 if lint(tools, args.width, args.param_width) else 0)

    if args.view in ("directory", "all"):
        show_directory(tools, args.width)
    if args.view in ("search", "all"):
        show_search(tools, args.width, args.param_width)
    if args.view == "full":
        show_full(tools)


if __name__ == "__main__":
    asyncio.run(main())
