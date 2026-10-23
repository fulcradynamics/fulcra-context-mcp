"""Measure MCP definitions, or simulate a pinned public Codex plugin budget.

    uv run python scripts/measure_tools.py [checkout]
    uv run python scripts/measure_tools.py --codex --json
    uv run python scripts/measure_tools.py --codex --inventory snapshot.json

Default: legacy tools_mcp character counts and chars/4 token estimates (not a
host budget). --codex: composed hosted server, serialized UTF-8 JSON bytes,
including each tool's repeated namespace wrapper. --inventory accepts a saved
{instructions, tools} snapshot. --namespace must match the host configuration.

Public Codex source at CODEX_REVISION: core/src/mcp_tool_exposure.rs (shared
admission), core/src/tools/handlers/mcp.rs (one-tool namespace),
codex-mcp/src/rmcp_client.rs (regular MCP namespace = server name/instructions),
tools/src/{responses_api,mcp_tool,json_schema}.rs (lowering/fallback), and
 tools/src/json_schema/{types,compaction}.rs. Paths are under codex-rs/.

This is a local simulation, not native-host acceptance. It models regular MCP
servers supplied by enabled agent plugins, not connector naming/policy. Schema
lowering covers a bounded reference-free subset; malformed retained fields and
explicit null fields are rejected rather than silently mismeasured. Recognized
singleton type arrays are collapsed; unknown/empty type arrays are rejected.
JSON uses compact separators, ensure_ascii=False, then UTF-8. Retained floats
and integers outside serde_json's i64/u64 range are rejected; minItems is bounded
to portable 32-bit usize values. Output schemas, annotations, defaults and unsupported
schema keywords are not serialized to the model. Host registry order/configuration
and other enabled plugins must be supplied to budget() to reproduce admission.
"""

import argparse
import asyncio
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

CODEX_REVISION = "221e4e7c05386d06aa7b91da2a9b04f7f2bd921f"
SPEC_LIMIT = 8000
TOTAL_LIMIT = 64000
DESCRIPTION_LIMIT = 1000
SCHEMA_LIMIT = 5000


def _validate_json(value):
    """Exact serde_json byte accounting only for integer-only JSON values."""
    if value is None or type(value) in (str, bool):
        return
    if type(value) is int and -(2**63) <= value < 2**64:
        return
    if type(value) is list:
        for child in value:
            _validate_json(child)
        return
    if type(value) is dict and all(type(k) is str for k in value):
        for child in value.values():
            _validate_json(child)
        return
    raise ValueError("unsupported JSON value: floats, oversized integers and non-JSON values require native serialization")


def serialized_bytes(value) -> int:
    _validate_json(value)
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8"))


def truncate_utf8(text: str, limit: int) -> str:
    return text.encode("utf-8")[:limit].decode("utf-8", errors="ignore")


def _schema_children(schema):
    yield from schema.get("properties", {}).values()
    for key in ("items", "additionalProperties"):
        if isinstance(schema.get(key), dict):
            yield schema[key]
    for key in ("anyOf", "oneOf", "allOf"):
        yield from schema.get(key, [])


def _lower_schema(schema):
    """Codex's supported schema fields, for reference-free server schemas."""
    if isinstance(schema, bool):
        return {"type": "string"}
    if not isinstance(schema, dict):
        raise ValueError("unsupported schema: expected object or boolean")
    if any(key in schema for key in ("$ref", "$defs", "definitions")):
        raise ValueError("reference/definition schemas require native Codex normalization")
    schema = copy.deepcopy(schema)
    # A bounded subset, not a replacement JSON Schema parser. Reject malformed
    # retained fields even if Codex might discard them during compaction.
    expected = {"description": str, "encrypted": bool, "enum": list,
                "properties": dict, "required": list, "minItems": int,
                "items": (dict, bool), "additionalProperties": (dict, bool),
                "anyOf": list, "oneOf": list, "allOf": list}
    for key, kind in expected.items():
        if key in schema and (not isinstance(schema[key], kind) or
                              (key == "minItems" and type(schema[key]) is not int)):
            raise ValueError(f"unsupported {key} value")
    if "minItems" in schema and not 0 <= schema["minItems"] < 2**32:
        raise ValueError("minItems outside portable usize subset (0..2**32-1)")
    if any(not isinstance(v, str) for v in schema.get("required", [])):
        raise ValueError("required must contain strings")
    if any(not isinstance(k, str) for k in schema.get("properties", {})):
        raise ValueError("properties must have string keys")
    if "type" in schema:
        types = schema["type"]
        types = [types] if isinstance(types, str) else types
        if not isinstance(types, list) or not types or any(
            not isinstance(t, str) or t not in ("string", "number", "boolean", "integer", "object", "array", "null")
            for t in types
        ):
            raise ValueError("unsupported schema type")
        schema["type"] = types[0] if len(types) == 1 else types
    if "const" in schema:
        schema["enum"] = [schema.pop("const")]
    if "type" not in schema and not any(k in schema for k in ("anyOf", "oneOf", "allOf")):
        if any(k in schema for k in ("properties", "required", "additionalProperties")):
            schema["type"] = "object"
        elif any(k in schema for k in ("items", "prefixItems")):
            schema["type"] = "array"
        elif any(k in schema for k in ("enum", "format")):
            schema["type"] = "string"
        elif any(k in schema for k in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf")):
            schema["type"] = "number"
        else:
            return {}
    types = schema.get("type", [])
    types = [types] if isinstance(types, str) else types
    if "object" in types:
        schema.setdefault("properties", {})
    if "array" in types:
        schema.setdefault("items", {"type": "string"})
    fields = ("type", "description", "encrypted", "enum", "items", "minItems", "properties",
              "required", "additionalProperties", "anyOf", "oneOf", "allOf")
    result = {k: schema[k] for k in fields if schema.get(k) is not None}
    if "properties" in result:
        result["properties"] = {k: _lower_schema(v) for k, v in sorted(result["properties"].items())}
    for key in ("items", "additionalProperties"):
        if key in result and not (key == "additionalProperties" and isinstance(result[key], bool)):
            result[key] = _lower_schema(result[key])
    for key in ("anyOf", "oneOf", "allOf"):
        if key in result:
            result[key] = [_lower_schema(v) for v in result[key]]
    return result


def _compact_schema(schema, pass_name, depth=0):
    if pass_name == "descriptions":
        schema.pop("description", None)
    elif pass_name == "depth" and depth >= 3 and any(k in schema for k in (
        "items", "anyOf", "oneOf", "allOf", "properties", "additionalProperties"
    )):
        schema.clear()
    elif pass_name == "compositions" and any(k in schema for k in ("anyOf", "oneOf", "allOf")):
        schema.clear()
    for child in _schema_children(schema):
        _compact_schema(child, pass_name, depth + 1)


def codex_spec(tool: dict, namespace: str, instructions: str) -> dict:
    source = copy.deepcopy(tool["inputSchema"])
    if not isinstance(source, dict):
        raise ValueError("tool input schema must be an object")
    source.setdefault("properties", {})
    schema = _lower_schema(source)
    if schema.get("type") == "null":
        raise ValueError("tool input schema must not be singleton null")
    before = serialized_bytes(schema)
    # Definition pruning is a no-op for supported, reference-free schemas.
    for pass_name in ("descriptions", "depth", "compositions"):
        if serialized_bytes(schema) <= SCHEMA_LIMIT:
            break
        _compact_schema(schema, pass_name)
    function = {"name": tool["name"], "description": truncate_utf8(tool.get("description") or "", DESCRIPTION_LIMIT),
                "strict": False, "parameters": schema}
    pre_fallback = serialized_bytes(function)  # ResponsesApiTool, without the type tag.
    fallback = pre_fallback > SPEC_LIMIT
    if fallback:
        function["parameters"] = {"type": "object", "properties": {}, "additionalProperties": True}
    function = {"type": "function", **function}
    spec = {"type": "namespace", "name": namespace,
            "description": truncate_utf8(instructions or "", DESCRIPTION_LIMIT).strip(), "tools": [function]}
    size = serialized_bytes(spec)
    return {"name": tool["name"], "namespace": namespace, "spec": spec, "spec_bytes": size,
            "function_bytes": serialized_bytes(function), "namespace_bytes": size - serialized_bytes(function),
            "pre_fallback_function_bytes": pre_fallback, "generic_schema_fallback": fallback,
            "schema_compacted": before > SCHEMA_LIMIT}


def budget(rows, *, deferred=False):
    """One ordered accumulator across ALL qualifying enabled plugins, not per server.

    Rows default to enabled, model-visible agent-plugin tools. Non-plugin tools
    neither consume nor obey this plugin budget. Hidden tools consume no bytes;
    later smaller tools can fit. Deferred search does not bypass admission.
    """
    charged = 0
    tools = []
    for row in rows:
        if not row.get("enabled", True) or not row.get("model_visible", True):
            continue
        fits = True
        if row.get("agent_plugin", True):
            fits = row["spec_bytes"] <= SPEC_LIMIT and charged + row["spec_bytes"] <= TOTAL_LIMIT
            if fits:
                charged += row["spec_bytes"]
        tools.append({**row, "exposure": ("deferred" if deferred else "direct") if fits else "hidden"})
    return {"charged_bytes": charged, "candidate_bytes": sum(r["spec_bytes"] for r in tools), "tools": tools}


def tool_payload(t) -> str:
    d = {"name": t.name, "description": t.description, "input_schema": t.inputSchema}
    if t.outputSchema:
        d["output_schema"] = t.outputSchema
    if t.annotations:
        d["annotations"] = t.annotations.model_dump(exclude_none=True)
    return json.dumps(d)


def app_only(t) -> bool:
    meta = t.get("_meta", {}) if isinstance(t, dict) else t.meta or {}
    visibility = (meta.get("ui") or {}).get("visibility")
    return visibility is not None and "model" not in visibility


def report(label: str, tools) -> None:
    rows = sorted(((len(tool_payload(t)), t.name) for t in tools), reverse=True)
    for n, name in rows:
        print(f"  {n:>6,} chars  (~{n // 4:>5,} tok)  {name}")
    total = sum(n for n, _ in rows)
    print(f"{label} {len(rows)} tools: {total:,} chars (~{total // 4:,} tokens)")


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", nargs="?", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--codex", action="store_true")
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--namespace", default="fulcra")
    parser.add_argument("--deferred", action="store_true")
    parser.add_argument("--environment", choices=("prod", "stdio"),
                        help="Codex discovery defaults to prod; select stdio explicitly for local tools")
    args = parser.parse_args()
    environment = args.environment or ("prod" if args.codex else os.environ.get("FULCRA_ENVIRONMENT", "prod"))
    os.environ["FULCRA_ENVIRONMENT"] = environment
    sys.path.insert(0, args.checkout)
    if args.inventory:
        if not args.codex:
            parser.error("--inventory requires --codex")
        snapshot = json.loads(args.inventory.read_text())
    else:
        from fastmcp import Client
        if args.codex:
            from fulcra_mcp.main import mcp as server
        else:
            from fulcra_mcp.tools import tools_mcp as server
        async with Client(server) as client:
            tools = await client.list_tools()
            instructions = client.initialize_result.instructions
        snapshot = {"tools": [t.model_dump(by_alias=True, exclude_none=True) for t in tools],
                    "instructions": instructions,
                    "revision": subprocess.check_output(["git", "-C", args.checkout, "rev-parse", "HEAD"], text=True).strip(),
                    "working_tree_dirty": bool(subprocess.check_output(
                        ["git", "-C", args.checkout, "status", "--porcelain", "--untracked-files=no"], text=True))}
    if args.codex:
        excluded_local = [] if not args.inventory else snapshot.get("excluded_local_only")
        if not args.inventory and environment == "prod":
            local = json.loads(subprocess.check_output(
                [sys.executable, __file__, args.checkout, "--codex", "--json", "--environment", "stdio"],
                text=True))
            local_names = {r["name"] for r in local["tools"]} | set(local["excluded_app_only"])
            excluded_local = sorted(local_names - {t["name"] for t in snapshot["tools"]})
        rows = [codex_spec(t, args.namespace, snapshot["instructions"]) for t in snapshot["tools"] if not app_only(t)]
        result = {"codex_revision": CODEX_REVISION, "server_revision": snapshot.get("revision"),
                  "environment": snapshot.get("environment", "unknown") if args.inventory else environment,
                  "excluded_app_only": sorted(t["name"] for t in snapshot["tools"] if app_only(t)),
                  "excluded_local_only": excluded_local,
                  "raw_mcp_tools_json_bytes": len(json.dumps(snapshot["tools"], ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")),
                  "raw_mcp_size_basis": "compact Python JSON tools array including app-only tools; not wire framing or Codex specs",
                  "instructions_truncated": len((snapshot["instructions"] or "").encode()) > DESCRIPTION_LIMIT,
                  "descriptions_truncated": [t["name"] for t in snapshot["tools"] if not app_only(t)
                      and len((t.get("description") or "").encode()) > DESCRIPTION_LIMIT],
                  "server_working_tree_dirty": snapshot.get("working_tree_dirty"),
                  "namespace": args.namespace, "instructions_bytes": len((snapshot["instructions"] or "").encode()),
                  "serialization": "compact JSON, ensure_ascii=False, UTF-8; output schemas skipped",
                  "limitations": "Local regular-MCP agent-plugin simulation, not native acceptance; bounded reference-free schemas, no retained floats, i64/u64 integers and portable 32-bit minItems only. Host order/config and other plugins not discovered; headroom is not reserved. Snapshot local-only exclusions are unknown unless supplied.",
                  **budget(rows, deferred=args.deferred)}
        result["remaining_shared_bytes"] = TOTAL_LIMIT - result["charged_bytes"]
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f'Environment: {result["environment"]}; raw MCP tools JSON: {result["raw_mcp_tools_json_bytes"]} bytes')
            print(f'Excluded app-only: {result["excluded_app_only"]}; local-only: {result["excluded_local_only"]}')
            print(f'Truncated instructions: {result["instructions_truncated"]}; descriptions: {result["descriptions_truncated"]}')
            for row in result["tools"]:
                print(f'{row["spec_bytes"]:6} bytes ({row["namespace_bytes"]} namespace) {row["exposure"]:8} fallback={row["generic_schema_fallback"]} {row["name"]}')
            print(f'Candidate {result["candidate_bytes"]} bytes; admitted {result["charged_bytes"]}/{TOTAL_LIMIT}; remaining shared headroom {result["remaining_shared_bytes"]}.')
            print(result["limitations"])
        return
    visible = [t for t in tools if not app_only(t)]
    if args.json:
        print(json.dumps({t.name: len(tool_payload(t)) for t in visible}))
        return
    print(f"Legacy character estimate (FULCRA_ENVIRONMENT={environment}); use --codex for plugin budget.")
    report("TOTAL", visible)
    report("APP-ONLY", [t for t in tools if app_only(t)])
    if environment != "stdio":
        out = subprocess.run([sys.executable, __file__, args.checkout, "--json"],
                             env={**os.environ, "FULCRA_ENVIRONMENT": "stdio"}, capture_output=True, text=True, check=True)
        hosted = {t.name for t in visible}
        for name, size in json.loads(out.stdout).items():
            if name not in hosted:
                print(f"STDIO-ONLY {size:,} chars {name}")


if __name__ == "__main__":
    asyncio.run(main())
