import asyncio
import json
from collections.abc import Iterable
from datetime import datetime, timezone

import pytest


BOOLEAN_VALUES = (True, False)
NUMERIC_DELTAS = (1, 2, -1, -2, 3)
STRING_BOOLEAN_VALUES = ("true", "false", "1", "0")
STRING_NUMERIC_VALUES = ("900", "60.5")
STRING_LIST_STR_VALUES = ('["max", "min"]', '["delta"]')
STRING_LIST_INT_VALUES = ("[2,4]", "[1,3,5]")


def _schema_declares_boolean(schema: dict) -> bool:
    if not isinstance(schema, dict):
        return False

    schema_type = schema.get("type")
    if isinstance(schema_type, str):
        if schema_type == "boolean":
            return True
    elif isinstance(schema_type, Iterable):
        if "boolean" in schema_type:
            return True

    const_value = schema.get("const")
    if type(const_value) is bool:  # noqa: E721 - we care about exact bool
        return True

    enum_values = schema.get("enum") or []
    if any(type(value) is bool for value in enum_values):
        return True

    for key in ("anyOf", "oneOf", "allOf"):
        if any(_schema_declares_boolean(subschema) for subschema in schema.get(key, [])):
            return True

    return False


def _schema_declares_numeric(schema: dict) -> set[str]:
    kinds: set[str] = set()
    if not isinstance(schema, dict):
        return kinds

    schema_type = schema.get("type")
    if isinstance(schema_type, str):
        kinds.update(_type_to_numeric_kind(schema_type))
    elif isinstance(schema_type, Iterable):
        for item in schema_type:
            kinds.update(_type_to_numeric_kind(item))

    const_value = schema.get("const")
    if isinstance(const_value, (int, float)) and not isinstance(const_value, bool):
        if isinstance(const_value, int):
            kinds.add("integer")
        else:
            kinds.add("number")

    enum_values = schema.get("enum") or []
    for value in enum_values:
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            kinds.add("integer")
        elif isinstance(value, float):
            kinds.add("number")

    for key in ("anyOf", "oneOf", "allOf"):
        for subschema in schema.get(key, []):
            kinds.update(_schema_declares_numeric(subschema))

    return kinds


def _type_to_numeric_kind(schema_type: str) -> set[str]:
    if schema_type in {"integer", "number"}:
        return {schema_type}
    return set()


def _validate_values(schema: dict, values: Iterable, *, jsonschema_module) -> tuple[list, list[str]]:
    validator = jsonschema_module.Draft202012Validator(schema)
    accepted: list = []
    rejected: list[str] = []
    for value in values:
        try:
            validator.validate(value)
        except jsonschema_module.ValidationError as exc:
            rejected.append(f"{value!r}: {exc.message}")
        else:
            accepted.append(value)
    return accepted, rejected


def _numeric_test_values(schema: dict, *, expect_integer: bool) -> list:
    default = schema.get("default")
    candidates: list = []

    if isinstance(default, (int, float)) and not isinstance(default, bool):
        for delta in NUMERIC_DELTAS:
            candidate = default + delta
            if expect_integer:
                candidate = int(round(candidate))
            else:
                candidate = float(candidate)
            if candidate == default:
                continue
            candidates.append(candidate)

    if not candidates:
        start = 1
        while len(candidates) < 5:
            candidate = start if expect_integer else float(start)
            candidates.append(candidate)
            start += 1

    unique_candidates: list = []
    seen: set = set()
    for value in candidates:
        if value in seen:
            continue
        seen.add(value)
        unique_candidates.append(value)

    return unique_candidates


def test_tool_input_schemas_accept_multiple_values():
    jsonschema_module = pytest.importorskip("jsonschema")
    pytest.importorskip("structlog")
    from fulcra_mcp import main as fulcra_main

    tools = asyncio.run(fulcra_main.mcp._list_tools())

    failures: list[str] = []

    for tool in tools:
        parameters = tool.parameters or {}
        properties = parameters.get("properties", {})
        for property_name, property_schema in properties.items():
            if _schema_declares_boolean(property_schema):
                accepted, rejected = _validate_values(
                    property_schema, BOOLEAN_VALUES, jsonschema_module=jsonschema_module
                )
                if len(set(accepted)) < len(BOOLEAN_VALUES):
                    failures.append(
                        "Boolean parameter validation failed for "
                        f"{tool.name}.{property_name}: accepted {accepted} but rejected {json.dumps(rejected)}"
                    )

            numeric_kinds = _schema_declares_numeric(property_schema)
            if numeric_kinds:
                expect_integer = "integer" in numeric_kinds and "number" not in numeric_kinds
                values_to_try = _numeric_test_values(property_schema, expect_integer=expect_integer)
                accepted, rejected = _validate_values(
                    property_schema, values_to_try, jsonschema_module=jsonschema_module
                )
                if len(set(accepted)) < 2:
                    failures.append(
                        "Numeric parameter validation failed for "
                        f"{tool.name}.{property_name}: accepted {accepted} but rejected {json.dumps(rejected)}"
                    )

    if failures:
        pytest.fail("\n".join(failures))


def test_tool_input_schemas_accept_string_forms():
    jsonschema_module = pytest.importorskip("jsonschema")
    pytest.importorskip("structlog")
    from fulcra_mcp import main as fulcra_main

    tools = asyncio.run(fulcra_main.mcp._list_tools())
    tool_schemas = {
        tool.name: (tool.parameters or {}).get("properties", {}) for tool in tools
    }

    boolean_targets = [
        ("get_metric_time_series", "replace_nulls"),
        ("get_sleep_cycles", "clip_to_range"),
        ("get_location_at_time", "reverse_geocode"),
        ("get_location_time_series", "reverse_geocode"),
    ]
    for tool_name, property_name in boolean_targets:
        schema = tool_schemas[tool_name][property_name]
        accepted, rejected = _validate_values(
            schema, STRING_BOOLEAN_VALUES, jsonschema_module=jsonschema_module
        )
        assert set(STRING_BOOLEAN_VALUES).issubset(set(accepted)), (
            f"Boolean string validation failed for {tool_name}.{property_name}: "
            f"accepted={accepted}, rejected={json.dumps(rejected)}"
        )

    numeric_targets = [
        ("get_metric_time_series", "sample_rate"),
        ("get_location_time_series", "sample_rate"),
        ("get_location_time_series", "change_meters"),
    ]
    for tool_name, property_name in numeric_targets:
        schema = tool_schemas[tool_name][property_name]
        accepted, rejected = _validate_values(
            schema, STRING_NUMERIC_VALUES, jsonschema_module=jsonschema_module
        )
        assert set(STRING_NUMERIC_VALUES).issubset(set(accepted)), (
            f"Numeric string validation failed for {tool_name}.{property_name}: "
            f"accepted={accepted}, rejected={json.dumps(rejected)}"
        )

    list_targets = [
        ("get_metric_time_series", "calculations", STRING_LIST_STR_VALUES),
        ("get_sleep_cycles", "stages", STRING_LIST_INT_VALUES),
        ("get_sleep_cycles", "gap_stages", STRING_LIST_INT_VALUES),
    ]
    for tool_name, property_name, values in list_targets:
        schema = tool_schemas[tool_name][property_name]
        accepted, rejected = _validate_values(
            schema, values, jsonschema_module=jsonschema_module
        )
        assert set(values).issubset(set(accepted)), (
            f"List string validation failed for {tool_name}.{property_name}: "
            f"accepted={accepted}, rejected={json.dumps(rejected)}"
        )


def test_tools_normalize_string_arguments(monkeypatch):
    pytest.importorskip("structlog")
    from fulcra_mcp import main as fulcra_main

    class DummyFrame:
        def to_json(self, **kwargs):
            return "{}"

    class DummyFulcra:
        def __init__(self):
            self.metric_kwargs = None
            self.sleep_kwargs = None
            self.location_kwargs = None
            self.location_series_kwargs = None

        def metric_time_series(self, *, metric, start_time, end_time, **kwargs):
            self.metric_kwargs = kwargs
            return DummyFrame()

        def sleep_cycles(self, *, start_time, end_time, **kwargs):
            self.sleep_kwargs = kwargs
            return DummyFrame()

        def location_at_time(self, *, time, **kwargs):
            self.location_kwargs = kwargs
            return {"location": "here"}

        def location_time_series(self, *, start_time, end_time, **kwargs):
            self.location_series_kwargs = kwargs
            return [{"location": "there"}]

    dummy_fulcra = DummyFulcra()
    monkeypatch.setattr(fulcra_main, "get_fulcra_object", lambda: dummy_fulcra)

    now = datetime.now(timezone.utc)

    async def invoke_tools():
        await fulcra_main.get_metric_time_series.fn(
            metric_name="steps",
            start_time=now,
            end_time=now,
            sample_rate="120",
            replace_nulls="true",
            calculations='["max", "min"]',
        )
        await fulcra_main.get_sleep_cycles.fn(
            start_time=now,
            end_time=now,
            clip_to_range="0",
            stages="[2,4]",
            gap_stages="[1,3]",
        )
        await fulcra_main.get_location_at_time.fn(
            time=now,
            reverse_geocode="1",
        )
        await fulcra_main.get_location_time_series.fn(
            start_time=now,
            end_time=now,
            change_meters="5.5",
            sample_rate="600",
            reverse_geocode="false",
        )

    asyncio.run(invoke_tools())

    assert dummy_fulcra.metric_kwargs is not None
    assert dummy_fulcra.metric_kwargs["sample_rate"] == pytest.approx(120.0)
    assert dummy_fulcra.metric_kwargs["replace_nulls"] is True
    assert dummy_fulcra.metric_kwargs["calculations"] == ["max", "min"]

    assert dummy_fulcra.sleep_kwargs["clip_to_range"] is False
    assert dummy_fulcra.sleep_kwargs["stages"] == [2, 4]
    assert dummy_fulcra.sleep_kwargs["gap_stages"] == [1, 3]

    assert dummy_fulcra.location_kwargs["reverse_geocode"] is True
    assert dummy_fulcra.location_kwargs["window_size"] == 14400

    assert dummy_fulcra.location_series_kwargs is not None
    assert dummy_fulcra.location_series_kwargs["change_meters"] == pytest.approx(5.5)
    assert dummy_fulcra.location_series_kwargs["sample_rate"] == 600
    assert dummy_fulcra.location_series_kwargs["look_back"] == 14400
    assert dummy_fulcra.location_series_kwargs["reverse_geocode"] is False
