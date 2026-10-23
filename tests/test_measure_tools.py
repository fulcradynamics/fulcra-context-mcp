"""Pinned public Codex budgeting, not native-host acceptance."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("measure_tools", Path(__file__).parents[1] / "scripts/measure_tools.py")
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)


def tool(description="", schema=None):
    return {"name": "send", "description": description,
            "inputSchema": schema or {"type": "object", "properties": {}}}


def test_repeated_namespace_is_charged_per_tool():
    row = measure.codex_spec(tool(), "fulcra", "instructions")
    report = measure.budget([row, row])
    assert report["charged_bytes"] == 2 * row["spec_bytes"]
    assert row["namespace_bytes"] == row["spec_bytes"] - row["function_bytes"]
    assert row["namespace_bytes"] > len("instructions")


def test_utf8_escaping_truncation_and_skipped_output():
    text = 'é"\\\n' * 300
    row = measure.codex_spec({**tool(text), "outputSchema": {"description": "x" * 9000}}, "fulcra", "é" * 501)
    function = row["spec"]["tools"][0]
    assert function["description"] == text.encode()[:1000].decode("utf-8", errors="ignore")
    assert row["spec"]["description"] == "é" * 500
    assert measure.serialized_bytes({"x": 'é"\\\n'}) == len(b'{"x":"\xc3\xa9\\"\\\\\\n"}')
    assert row == measure.codex_spec(tool(text), "fulcra", "é" * 501)
    assert measure.truncate_utf8("a" * 999 + "é", 1000) == "a" * 999


@pytest.mark.parametrize("size,visible", [(7999, True), (8000, True), (8001, False)])
def test_per_spec_boundary(size, visible):
    report = measure.budget([{"spec_bytes": size, "name": "a", "namespace": "one"}])
    assert (report["tools"][0]["exposure"] == "direct") is visible


@pytest.mark.parametrize("size", [7999, 8000, 8001])
def test_serialized_spec_boundary(size):
    schema = {"type": "object", "properties": {"v": {"type": "string", "enum": [""]}}}
    empty = measure.codex_spec(tool(schema=schema), "plugin", "instructions")
    schema["properties"]["v"]["enum"] = ["x" * (size - empty["spec_bytes"])]
    row = measure.codex_spec(tool(schema=schema), "plugin", "instructions")
    assert row["spec_bytes"] == size
    assert not row["generic_schema_fallback"]
    assert (measure.budget([row])["tools"][0]["exposure"] == "direct") == (size <= 8000)


def test_schema_compaction_depth_and_composition_passes():
    leaf = {"type": "string", "enum": ["x" * 6000]}
    nested = {"type": "object", "properties": {"a": {"type": "array", "items": {
        "type": "object", "properties": {"b": {"type": "array", "items": leaf}}}}}}
    row = measure.codex_spec(tool(schema=nested), "plugin", "")
    assert row["spec"]["tools"][0]["parameters"]["properties"]["a"]["items"]["properties"]["b"] == {}
    composition = {"type": "object", "properties": {"v": {"anyOf": [leaf, {"type": "null"}]}}}
    row = measure.codex_spec(tool(schema=composition), "plugin", "")
    assert row["spec"]["tools"][0]["parameters"]["properties"]["v"] == {}
    assert not row["generic_schema_fallback"]


def test_shared_accumulator_order_hidden_then_smaller_and_deferred():
    rows = [{"spec_bytes": 8000, "name": str(i), "namespace": "first"} for i in range(7)]
    rows += [{"spec_bytes": 8001, "name": "oversize", "namespace": "second"},
             {"spec_bytes": 7999, "name": "fit", "namespace": "second"},
             {"spec_bytes": 2, "name": "over-total", "namespace": "third"},
             {"spec_bytes": 1, "name": "last-fit", "namespace": "third"}]
    result = measure.budget(rows, deferred=True)
    assert result["charged_bytes"] == 64000
    assert [r["exposure"] for r in result["tools"]][-4:] == ["hidden", "deferred", "hidden", "deferred"]
    reordered = measure.budget([rows[-2], *rows[:-2], rows[-1]])
    assert next(r for r in reordered["tools"] if r["name"] == "fit")["exposure"] == "hidden"
    assert [r["name"] for r in measure.budget(rows)["tools"] if r["exposure"] == "hidden"] == ["oversize", "over-total"]


def test_only_enabled_qualifying_model_tools_share_budget():
    rows = [{"name": "ordinary", "spec_bytes": 90000, "agent_plugin": False},
            {"name": "disabled", "spec_bytes": 8000, "enabled": False},
            {"name": "app", "spec_bytes": 8000, "model_visible": False},
            {"name": "plugin", "spec_bytes": 8000}]
    result = measure.budget(rows)
    assert result["charged_bytes"] == 8000
    assert [r["name"] for r in result["tools"]] == ["ordinary", "plugin"]
    assert all(r["exposure"] == "direct" for r in result["tools"])


def test_generic_fallback_is_separate_from_exposure():
    schema = {"type": "object", "properties": {"value": {"type": "string", "enum": ["x" * 8100]}}}
    row = measure.codex_spec(tool(schema=schema), "fulcra", "instructions")
    assert row["generic_schema_fallback"]
    assert row["pre_fallback_function_bytes"] > 8000
    assert row["spec"]["tools"][0]["parameters"] == {"type": "object", "properties": {}, "additionalProperties": True}
    assert measure.budget([row])["tools"][0]["exposure"] == "direct"


def test_fallback_boundary_and_wrapper_can_hide_without_fallback():
    schema = {"type": "object", "properties": {"v": {"type": "string", "enum": [""]}}}
    empty = measure.codex_spec(tool(schema=schema), "fulcra", "n" * 1000)
    schema["properties"]["v"]["enum"] = ["x" * (8000 - empty["pre_fallback_function_bytes"])]
    exact = measure.codex_spec(tool(schema=schema), "fulcra", "n" * 1000)
    assert exact["pre_fallback_function_bytes"] == 8000
    assert not exact["generic_schema_fallback"]
    assert measure.budget([exact])["tools"][0]["exposure"] == "hidden"
    schema["properties"]["v"]["enum"][0] += "x"
    assert measure.codex_spec(tool(schema=schema), "fulcra", "n" * 1000)["generic_schema_fallback"]


def test_schema_lowering_and_description_compaction():
    schema = {"type": "object", "title": "unused", "properties": {
        "a": {"type": "string", "default": "ignored", "description": "x" * 6000},
        "b": {"const": "yes"}, "c": {"type": "array"}}}
    row = measure.codex_spec(tool(schema=schema), "fulcra", "")
    assert row["schema_compacted"]
    assert row["spec"]["tools"][0]["parameters"]["properties"] == {
        "a": {"type": "string"}, "b": {"type": "string", "enum": ["yes"]},
        "c": {"type": "array", "items": {"type": "string"}}}
    assert schema["properties"]["a"]["description"] == "x" * 6000


async def test_in_process_budget_and_essential_instructions():
    from fastmcp import Client
    from fulcra_mcp.main import mcp
    async with Client(mcp) as client:
        tools = await client.list_tools()
        instructions = client.initialize_result.instructions
    assert len(instructions.encode()) <= measure.DESCRIPTION_LIMIT
    rows = [measure.codex_spec(t.model_dump(by_alias=True, exclude_none=True), "fulcra", instructions)
            for t in tools if not measure.app_only(t) and t.name != "debug_token_info"]
    result = measure.budget(rows)
    assert result["candidate_bytes"] <= measure.TOTAL_LIMIT
    assert not any(r["generic_schema_fallback"] or r["schema_compacted"] for r in rows)
    for text in ("time zone", "open_agent_contacts",
                 "explicit", "untrusted", "mesh_identifier", "converted_from_mesh", "Do not migrate"):
        assert text in instructions
    contact = next(t for t in tools if t.name == "open_agent_contacts")
    assert "contacts://threads/id-" in contact.description
    assert "exact peer_fulcra_userid" in contact.description
    assert "multiparty thread_id" in contact.description


@pytest.mark.parametrize("value", [[], ["bogus"], ["string", "bogus"], ["string", 1], None, 1, "bogus"])
def test_invalid_types_fail_closed(value):
    with pytest.raises(ValueError):
        measure.codex_spec(tool(schema={"type": value}), "fulcra", "")


def test_singleton_type_normalizes_before_admission():
    schema = {"type": "object", "properties": {"x": {"type": ["string"], "enum": [""]}}}
    row = measure.codex_spec(tool(schema=schema), "fulcra", "")
    assert row["spec"]["tools"][0]["parameters"]["properties"]["x"]["type"] == "string"
    schema["properties"]["x"]["enum"] = ["x" * (7999 - row["spec_bytes"])]
    union = measure.codex_spec(tool(schema=schema), "fulcra", "")
    schema["properties"]["x"]["type"] = "string"
    assert union == measure.codex_spec(tool(schema=schema), "fulcra", "")
    assert measure.budget([union])["tools"][0]["exposure"] == "direct"


@pytest.mark.parametrize("schema", [None, {"type": "null"}, {"type": ["null"]}])
def test_null_root_rejected(schema):
    with pytest.raises(ValueError):
        measure.codex_spec({"name": "probe", "inputSchema": schema}, "fulcra", "")


@pytest.mark.parametrize("field,value", [
    ("minItems", -1), ("minItems", True), ("minItems", 1.0), ("minItems", 2**64),
    ("minItems", "1"), ("description", 1), ("encrypted", "true"),
    ("enum", "x"), ("properties", []), ("required", [1]), ("required", "x"),
    ("items", []), ("additionalProperties", 1), ("anyOf", {}), ("oneOf", [1]),
    ("allOf", [None]),
])
def test_invalid_retained_fields_fail_closed(field, value):
    with pytest.raises(ValueError):
        measure.codex_spec(tool(schema={"type": "object", "properties": {
            "x": {"type": "array", field: value}}}), "fulcra", "")


@pytest.mark.parametrize("value", [1e-7, 1.0, -0.0, float("inf"), float("nan"), 2**64, -(2**63)-1])
def test_unsupported_retained_numbers_fail_closed(value):
    with pytest.raises(ValueError):
        measure.codex_spec(tool(schema={"type": "object", "properties": {
            "x": {"enum": [{"nested": [value]}]}}}), "fulcra", "")


def test_supported_retained_values():
    schema = {"type": "object", "properties": {"x": {
        "type": ["array", "null"], "minItems": 0, "encrypted": False,
        "items": {"type": "string", "enum": [None, True, -(2**63), 2**64-1]}, "description": "ok"}},
        "required": ["x"], "additionalProperties": False}
    assert measure.codex_spec(tool(schema=schema), "fulcra", "")["spec"]["tools"][0]["parameters"] == schema


def test_prod_subprocess_report_and_explicit_stdio():
    import json
    import os
    import subprocess
    import sys

    command = [sys.executable, str(Path(__file__).parents[1] / "scripts/measure_tools.py"), "--codex", "--json"]
    env = {**os.environ, "FULCRA_ENVIRONMENT": "stdio"}
    prod = json.loads(subprocess.check_output(command, env=env, text=True))
    stdio = json.loads(subprocess.check_output(command + ["--environment", "stdio"], env=env, text=True))
    assert prod["environment"] == "prod"
    assert stdio["environment"] == "stdio"
    assert "debug_token_info" not in {r["name"] for r in prod["tools"]}
    assert "debug_token_info" in {r["name"] for r in stdio["tools"]}
    assert prod["excluded_local_only"] == ["debug_token_info"]
    assert "start_file_upload" in prod["excluded_app_only"]
    assert prod["raw_mcp_tools_json_bytes"] > 0
    assert prod["remaining_shared_bytes"] == measure.TOTAL_LIMIT - prod["charged_bytes"]
    assert prod["candidate_bytes"] <= measure.TOTAL_LIMIT
    assert prod["instructions_truncated"] is False
    assert prod["descriptions_truncated"] == []


def test_unmodeled_reference_schemas_fail_explicitly():
    with pytest.raises(ValueError, match="reference"):
        measure.codex_spec(tool(schema={"$ref": "#/$defs/A", "$defs": {"A": {"type": "string"}}}), "fulcra", "")
