"""Behavioral checks for the review criteria that need a live-looking server:
actionable error messages, input validation, and response-size guardrails."""

import io
import json

import pytest
from fastmcp.exceptions import ToolError

from conftest import FAKE_USER_ID, http_error

START = "2026-08-01T00:00:00-07:00"
END = "2026-08-02T00:00:00-07:00"


async def test_naive_datetime_rejected_with_guidance(client, fake_fulcra):
    with pytest.raises(ToolError, match="time zone"):
        await client.call_tool(
            "get_workouts",
            {"start_time": "2026-08-01T00:00:00", "end_time": END},
        )
    fake_fulcra.apple_workouts.assert_not_called()


async def test_inverted_range_rejected(call, fake_fulcra):
    text = await call("get_workouts", {"start_time": END, "end_time": START})
    assert "must be after" in text
    fake_fulcra.apple_workouts.assert_not_called()


async def test_server_error_is_actionable(call, fake_fulcra):
    fake_fulcra.apple_workouts.side_effect = http_error(500, b"upstream exploded")
    text = await call("get_workouts", {"start_time": START, "end_time": END})
    assert "HTTP 500" in text
    assert "upstream exploded" in text
    assert "support@fulcradynamics.com" in text


async def test_auth_error_suggests_reauthentication(call, fake_fulcra):
    fake_fulcra.get_user_info.side_effect = http_error(401)
    text = await call("get_user_info")
    assert "HTTP 401" in text
    assert "re-authenticate" in text


async def test_time_series_sample_guard(call, fake_fulcra):
    # A year at the default 60s sample rate would be ~525k samples.
    text = await call(
        "get_time_series",
        {
            "data_type": "heart_rate",
            "start_time": "2025-08-01T00:00:00-07:00",
            "end_time": END,
        },
    )
    assert "sample_rate" in text
    fake_fulcra.metric_time_series.assert_not_called()


async def test_time_series_unsupported_type_points_to_get_records(call, fake_fulcra):
    fake_fulcra.metric_time_series.side_effect = http_error(422)
    text = await call(
        "get_time_series",
        {"data_type": "not_a_metric", "start_time": START, "end_time": END},
    )
    assert "get_records" in text


async def test_records_are_truncated_with_notice(call, fake_fulcra):
    fake_fulcra.resolve_data_type.return_value = [
        {
            "id": "heart_rate",
            "api_version": "v0",
            "record_spec": {"type": "metric"},
            "fulcra_userid": FAKE_USER_ID,
        }
    ]
    fake_fulcra.metric_samples.return_value = [{"n": i} for i in range(2500)]
    text = await call(
        "get_records",
        {"data_type": "heart_rate", "start_time": START, "end_time": END},
    )
    assert "first 2000 of 2500" in text
    payload = json.loads(text[text.index("["):])
    assert len(payload) == 2000


async def test_record_data_rejects_malformed_user_type_id(call, fake_fulcra):
    text = await call(
        "record_data",
        {"data_type": "MomentAnnotation/not-a-uuid", "value": "1"},
    )
    assert "<BaseType>/<UUID>" in text
    fake_fulcra.record_data_type.assert_not_called()


async def test_record_data_rejects_non_recordable_type(call, fake_fulcra):
    fake_fulcra.v1_catalog.return_value = [
        {"id": "heart_rate", "api_version": "v0", "recordable": False}
    ]
    text = await call("record_data", {"data_type": "heart_rate", "value": "60"})
    assert "not recordable" in text
    fake_fulcra.record_data_type.assert_not_called()


async def test_archive_rejects_malformed_id(call, fake_fulcra):
    text = await call("archive_data_type", {"data_type": "garbage"})
    assert "get_data_catalog" in text
    fake_fulcra.delete_annotation.assert_not_called()


async def test_archive_unknown_id_is_actionable(call, fake_fulcra):
    fake_fulcra.delete_annotation.side_effect = http_error(403)
    text = await call(
        "archive_data_type",
        {"data_type": "MomentAnnotation/00000000-0000-0000-0000-000000000000"},
    )
    assert "No user-defined data type" in text


async def test_calendar_events_unknown_calendar_is_actionable(call, fake_fulcra):
    fake_fulcra.calendars.return_value = [
        {"calendar_id": "c1", "calendar_name": "Work"}
    ]
    text = await call(
        "get_calendar_events",
        {"start_time": START, "end_time": END, "calendars": ["Home"]},
    )
    assert "No calendar named 'Home'" in text
    assert "get_calendars" in text
    fake_fulcra.calendar_events.assert_not_called()


async def test_read_file_gates_binary_content(call, fake_fulcra):
    fake_fulcra.resolve_filepath.return_value = [{"id": "f1"}]
    fake_fulcra.download_file.return_value = io.BytesIO(b"\xff\xfe\x00binary")
    text = await call("read_file", {"path": "/img.bin"})
    assert "binary file" in text
    assert "include_binary" in text


async def test_read_file_truncates_large_text(call, fake_fulcra):
    fake_fulcra.resolve_filepath.return_value = [{"id": "f1"}]
    fake_fulcra.download_file.return_value = io.BytesIO(b"x" * 200_000)
    text = await call("read_file", {"path": "/big.txt"})
    assert "truncated to the first 100000" in text


async def test_read_file_missing_is_actionable(call, fake_fulcra):
    fake_fulcra.resolve_filepath.side_effect = Exception("nope")
    text = await call("read_file", {"path": "/missing.txt"})
    assert "No file found" in text
    assert "list_files" in text


async def test_get_user_info_strips_intercom_token(call, fake_fulcra):
    fake_fulcra.get_user_info.return_value = {
        "name": "Test User",
        "intercom_token": "sekrit",
    }
    text = await call("get_user_info")
    assert "sekrit" not in text
    assert "Test User" in text


async def test_location_at_time_honors_reverse_geocode(call, fake_fulcra):
    fake_fulcra.location_at_time.return_value = {"lat": 1, "lon": 2}
    await call("get_location_at_time", {"time": START, "reverse_geocode": False})
    kwargs = fake_fulcra.location_at_time.call_args.kwargs
    assert kwargs["reverse_geocode"] is False
    assert kwargs["include_after"] is True


async def test_location_series_sample_guard(call, fake_fulcra):
    text = await call(
        "get_location_time_series",
        {
            "start_time": "2024-08-01T00:00:00-07:00",
            "end_time": END,
            "sample_rate": 60,
        },
    )
    assert "sample_rate" in text
    fake_fulcra.location_time_series.assert_not_called()


async def test_create_data_type_validates_scale_labels(call, fake_fulcra):
    text = await call(
        "create_data_type",
        {"base_type": "scale", "name": "Mood", "scale_labels": ["low", "high"]},
    )
    assert "exactly 5" in text
    fake_fulcra.create_annotation.assert_not_called()


# --- get_records for user-defined (v1alpha1) annotation types -----------------
#
# These drive the real SDK dispatcher (fulcra_api.records.get_records) against
# the autospec'd client, so a rename of the underlying SDK transport method
# (which broke MCP 0.3.0 on fulcra-api 0.1.42) fails here.

USER_TYPE_UUID = "6a0d0d5e-2b7a-4f5c-9c0e-3a3f1b2c4d5e"


@pytest.mark.parametrize(
    "base_type,record_type",
    [("MomentAnnotation", "event"), ("NumericAnnotation", "metric")],
)
async def test_get_records_reads_user_defined_annotation(
    call, fake_fulcra, base_type, record_type
):
    type_id = f"{base_type}/{USER_TYPE_UUID}"
    fake_fulcra.resolve_data_type.return_value = [
        {
            "id": type_id,
            "api_version": "v1alpha1",
            "record_spec": {"type": record_type},
            "fulcra_userid": FAKE_USER_ID,
        }
    ]
    fake_fulcra.fulcra_v1alpha1_api_path.return_value = (
        b'[{"value": 1, "note": "hello"}]'
    )
    text = await call(
        "get_records",
        {"data_type": type_id, "start_time": START, "end_time": END},
    )
    payload = json.loads(text[text.index("["):])
    assert payload == [{"value": 1, "note": "hello"}]

    fake_fulcra.resolve_data_type.assert_called_once_with(type_id, fulcra_userid=None)
    (path, params), _ = fake_fulcra.fulcra_v1alpha1_api_path.call_args
    assert path == f"{record_type}/{base_type}/{USER_TYPE_UUID}"
    assert set(params) == {"start_time", "end_time"}


async def test_get_records_unknown_type_is_friendly(call, fake_fulcra):
    fake_fulcra.resolve_data_type.side_effect = ValueError("Type not found")
    text = await call(
        "get_records",
        {"data_type": "NotAThing", "start_time": START, "end_time": END},
    )
    assert "No data type found" in text
    assert "get_data_catalog" in text


# --- record_data for v1 types -------------------------------------------------

V1_UUID = "df10403a-2115-4254-9e49-e48ca0af6f5d"
TS = {"type": "string", "format": "date-time"}


def _nullable(prop: dict) -> dict:
    """a property as Pydantic writes optional fields"""
    return {"anyOf": [prop, {"type": "null"}], "default": None}


def _v1_schema(**custom) -> dict:
    """a v1 record schema: the base fields plus `custom`"""
    return {
        "type": "object",
        "properties": {
            "id": _nullable({"type": "string", "format": "uuid"}),
            "sources": _nullable({"type": "array", "items": {"type": "string"}}),
            "tags": _nullable({"type": "array", "items": {"type": "string"}}),
            "start_time": _nullable(TS),
            "end_time": _nullable(TS),
            **custom,
        },
    }


CHECK_IN_SCHEMA = _v1_schema(
    mood={"type": "string"}, energy={"type": "number"}, rested={"type": "boolean"}
)
METRIC_SCHEMA = _v1_schema(value={"type": "number"}, unit=_nullable({"type": "string"}))


def _v1_type(fake_fulcra, type_id: str, schema: dict) -> None:
    fake_fulcra.v1_catalog.return_value = [
        {"id": type_id, "api_version": "v1", "recordable": True}
    ]
    fake_fulcra.v1_catalog_schema.return_value = schema
    fake_fulcra.validate_records.return_value = []
    fake_fulcra.record_data_type.return_value = {"upload_id": "up-1"}
    fake_fulcra.create_tags.return_value = [{"id": "tag-1", "name": "work"}]


def _recorded(fake_fulcra) -> tuple[str, dict, str]:
    """(target type, the record, api version) of the one upload"""
    (target, records, version), _ = fake_fulcra.record_data_type.call_args
    assert len(records) == 1
    return target, records[0], version


@pytest.mark.parametrize("base_type", ["Event", "Metric"])
async def test_record_data_sends_v1_user_defined_types_to_their_own_id(
    call, fake_fulcra, base_type
):
    type_id = f"{base_type}/{V1_UUID}"
    _v1_type(fake_fulcra, type_id, CHECK_IN_SCHEMA)

    text = await call(
        "record_data",
        {
            "data_type": type_id,
            "start_time": START,
            "end_time": END,
            "tags": ["work"],
            "fields": {"mood": "calm", "energy": 7, "rested": True},
        },
    )

    target, record, version = _recorded(fake_fulcra)
    # not the base type, which would store it as a plain Event/Metric record
    assert (target, version) == (type_id, "v1")
    fake_fulcra.validate_records.assert_called_once_with(type_id, [record], "v1")
    fake_fulcra.v1_catalog_schema.assert_called_once_with(type_id, "v1")
    assert record == {
        # v1 records aren't linked to their type by an annotation source
        "sources": ["com.fulcradynamics.mcp"],
        "mood": "calm",
        "energy": 7,
        "rested": True,
        "start_time": "2026-08-01T00:00:00-07:00",
        "end_time": "2026-08-02T00:00:00-07:00",
        "tags": ["tag-1"],
    }
    assert "upload ID up-1" in text


async def test_record_data_keeps_the_time_of_a_plain_v1_metric(call, fake_fulcra):
    _v1_type(fake_fulcra, "Metric", METRIC_SCHEMA)

    await call("record_data", {"data_type": "Metric", "value": "4.5", "start_time": START})

    target, record, _ = _recorded(fake_fulcra)
    assert target == "Metric"
    # start_time, not v1alpha1's recorded_at, which v1 would drop
    assert record == {
        "sources": ["com.fulcradynamics.mcp"],
        "value": 4.5,
        "start_time": "2026-08-01T00:00:00-07:00",
    }


async def test_record_data_refuses_fields_the_type_does_not_have(call, fake_fulcra):
    type_id = f"Event/{V1_UUID}"
    _v1_type(fake_fulcra, type_id, CHECK_IN_SCHEMA)

    text = await call(
        "record_data",
        {"data_type": type_id, "note": "hi", "fields": {"mod": "calm"}},
    )

    assert text == (
        f"{type_id} has no field 'mod', 'note'; its fields are: end_time, energy, "
        "mood, rested, start_time."
    )
    fake_fulcra.record_data_type.assert_not_called()
    # nothing is created on the way to a refusal
    fake_fulcra.create_tags.assert_not_called()


async def test_record_data_refuses_a_value_on_an_event_type(call, fake_fulcra):
    type_id = f"Event/{V1_UUID}"
    _v1_type(fake_fulcra, type_id, CHECK_IN_SCHEMA)

    text = await call("record_data", {"data_type": type_id, "value": "5"})

    assert text.startswith(f"{type_id} has no field 'value';")
    fake_fulcra.record_data_type.assert_not_called()


@pytest.mark.parametrize("key", ["start_time", "end_time", "sources", "tags", "id"])
async def test_record_data_fields_cannot_set_what_parameters_set(call, fake_fulcra, key):
    type_id = f"Event/{V1_UUID}"
    _v1_type(fake_fulcra, type_id, CHECK_IN_SCHEMA)

    text = await call("record_data", {"data_type": type_id, "fields": {key: "x"}})

    assert text.startswith(f"fields can't set {key};")
    fake_fulcra.record_data_type.assert_not_called()


async def test_record_data_fields_cannot_set_recorded_at_on_v1alpha1(call, fake_fulcra):
    """v1alpha1 annotation records carry their time as recorded_at, which the tool sets"""
    type_id = f"NumericAnnotation/{V1_UUID}"
    fake_fulcra.v1_catalog.return_value = [
        {"id": type_id, "api_version": "v1alpha1", "recordable": True}
    ]

    text = await call(
        "record_data", {"data_type": type_id, "fields": {"recorded_at": START}}
    )

    assert text.startswith("fields can't set recorded_at;")
    fake_fulcra.record_data_type.assert_not_called()


RECORDED_AT_SCHEMA = _v1_schema(recorded_at={"type": "string"}, mood={"type": "string"})
RECORDED_AT_SCHEMA["required"] = ["recorded_at"]


async def test_record_data_v1_type_can_have_its_own_recorded_at_field(call, fake_fulcra):
    """recorded_at is only the tool's on v1alpha1; a v1 type may declare (and
    require) a field of that name, set through `fields`"""
    type_id = f"Event/{V1_UUID}"
    _v1_type(fake_fulcra, type_id, RECORDED_AT_SCHEMA)

    text = await call(
        "record_data",
        {
            "data_type": type_id,
            "start_time": START,
            "fields": {"recorded_at": "by hand", "mood": "calm"},
        },
    )

    assert "upload ID up-1" in text
    _, record, _ = _recorded(fake_fulcra)
    assert record == {
        "sources": ["com.fulcradynamics.mcp"],
        "recorded_at": "by hand",
        "mood": "calm",
        "start_time": "2026-08-01T00:00:00-07:00",
    }


async def test_catalog_lists_a_v1_types_own_recorded_at_field(call, fake_fulcra):
    user_type = f"Event/{V1_UUID}"
    fake_fulcra.v1_catalog.return_value = [
        {"id": user_type, "api_version": "v1", "record_spec": {"type": "event"}}
    ]
    fake_fulcra.v1_catalog_schema.return_value = RECORDED_AT_SCHEMA

    text = await call("get_data_catalog", {"data_type": user_type})

    [entry] = [e for group in json.loads(text[text.index("{"):]).values() for e in group]
    assert entry["fields"] == {"mood": "string", "recorded_at": "string"}


async def test_record_data_value_given_twice_is_refused(call, fake_fulcra):
    _v1_type(fake_fulcra, "Metric", METRIC_SCHEMA)

    text = await call(
        "record_data", {"data_type": "Metric", "value": "1", "fields": {"value": 2}}
    )

    assert text == "value is given both as a parameter and in fields; give it once."
    fake_fulcra.record_data_type.assert_not_called()


async def test_record_data_v1alpha1_annotations_are_unchanged(call, fake_fulcra):
    type_id = f"NumericAnnotation/{V1_UUID}"
    fake_fulcra.v1_catalog.return_value = [
        {"id": type_id, "api_version": "v1alpha1", "recordable": True}
    ]
    fake_fulcra.v1_catalog_schema.return_value = {
        "type": "object",
        "properties": {
            name: {}
            for name in ("id", "sources", "tags", "value", "note", "recorded_at", "unit")
        },
    }
    fake_fulcra.validate_records.return_value = []
    fake_fulcra.record_data_type.return_value = {"upload_id": "up-1"}

    await call("record_data", {"data_type": type_id, "value": "3", "start_time": START})

    target, record, version = _recorded(fake_fulcra)
    assert (target, version) == ("NumericAnnotation", "v1alpha1")
    fake_fulcra.v1_catalog_schema.assert_called_once_with("NumericAnnotation", "v1alpha1")
    assert record == {
        "sources": ["com.fulcradynamics.mcp", f"com.fulcradynamics.annotation.{V1_UUID}"],
        "value": 3,
        "recorded_at": "2026-08-01T00:00:00-07:00",
    }


async def test_catalog_lists_the_fields_of_one_user_defined_v1_type(call, fake_fulcra):
    user_type = f"Event/{V1_UUID}"
    fake_fulcra.v1_catalog.return_value = [
        {
            "id": user_type,
            "name": "Check-in",
            "api_version": "v1",
            "categories": ["user_configured"],
            "record_spec": {"type": "event"},
            "fulcra_userid": FAKE_USER_ID,
        }
    ]
    fake_fulcra.v1_catalog_schema.return_value = CHECK_IN_SCHEMA

    text = await call("get_data_catalog", {"data_type": user_type})

    fake_fulcra.v1_catalog_schema.assert_called_once_with(
        user_type, "v1", fulcra_userid=FAKE_USER_ID
    )
    [entry] = [e for group in json.loads(text[text.index("{"):]).values() for e in group]
    assert entry["fields"] == {"energy": "number", "mood": "string", "rested": "boolean"}


@pytest.mark.parametrize(
    "entries, data_type",
    [
        # a full listing: no schema request per type
        ([{"id": f"Event/{V1_UUID}", "api_version": "v1"}] * 2, None),
        ([{"id": f"Event/{V1_UUID}", "api_version": "v1"}], None),
        # not user-defined v1 types
        ([{"id": "Event", "api_version": "v1"}], "Event"),
        (
            [{"id": f"MomentAnnotation/{V1_UUID}", "api_version": "v1alpha1"}],
            f"MomentAnnotation/{V1_UUID}",
        ),
    ],
    ids=["listing", "filtered-by-category", "base-type", "v1alpha1"],
)
async def test_catalog_fetches_no_schema_otherwise(call, fake_fulcra, entries, data_type):
    fake_fulcra.v1_catalog.return_value = entries

    text = await call("get_data_catalog", {"data_type": data_type} if data_type else {})

    fake_fulcra.v1_catalog_schema.assert_not_called()
    assert '"fields"' not in text


# --- create / archive / restore for v1 (Event / Metric) types -----------------


@pytest.mark.parametrize("base_type", ["event", "metric"])
@pytest.mark.parametrize("description", [None, "  "])
async def test_create_v1_data_type_requires_a_description(
    call, fake_fulcra, base_type, description
):
    args = {"base_type": base_type, "name": "Check-in"}
    if description is not None:
        args["description"] = description
    text = await call("create_data_type", args)
    assert text == f"base_type='{base_type}' requires a description of what the type tracks."
    fake_fulcra.create_data_type.assert_not_called()


@pytest.mark.parametrize(
    "base_type, option, value, message",
    [
        ("event", "unit", "mg", "unit can only be used with base_type 'metric' or 'numeric'."),
        ("event", "metric_kind", "discrete", "metric_kind can only be used with base_type 'metric' or 'boolean' or 'numeric' or 'scale'."),
        ("event", "scale", {"min": 1, "max": 5}, "scale can only be used with base_type 'metric'."),
        ("event", "value_map", {"1": "low"}, "value_map can only be used with base_type 'metric'."),
        ("metric", "tags", ["work"], "tags can only be used with base_type 'moment' or 'duration' or 'boolean' or 'numeric' or 'scale'."),
        ("metric", "default_value", "1", "default_value can only be used with base_type 'boolean' or 'numeric'."),
        ("metric", "scale_labels", ["a"] * 5, "scale_labels can only be used with base_type 'scale'."),
        ("numeric", "fields", {"properties": {"mood": {"type": "string"}}}, "fields can only be used with base_type 'event' or 'metric'."),
        ("moment", "scale", {"min": 1, "max": 5}, "scale can only be used with base_type 'metric'."),
    ],
)
async def test_create_data_type_refuses_options_for_another_base(
    call, fake_fulcra, base_type, option, value, message
):
    text = await call(
        "create_data_type",
        {"base_type": base_type, "name": "X", "description": "d", option: value},
    )
    assert text == message
    fake_fulcra.create_data_type.assert_not_called()
    fake_fulcra.create_annotation.assert_not_called()


@pytest.mark.parametrize(
    "fields",
    [{"mood": {"type": "string"}}, {"properties": {}}, {"properties": "mood"}],
    ids=["no-properties", "empty", "not-an-object"],
)
async def test_create_v1_data_type_refuses_fields_without_properties(call, fake_fulcra, fields):
    text = await call(
        "create_data_type",
        {"base_type": "event", "name": "X", "description": "d", "fields": fields},
    )
    assert 'must define the fields to add under "properties"' in text
    fake_fulcra.create_data_type.assert_not_called()


async def test_create_v1_metric_scale_needs_min_and_max(call, fake_fulcra):
    text = await call(
        "create_data_type",
        {"base_type": "metric", "name": "X", "description": "d", "scale": {"max": 5}},
    )
    assert text.startswith('scale needs "min" and "max"')
    fake_fulcra.create_data_type.assert_not_called()


async def test_create_v1_data_type_surfaces_the_servers_reason(call, fake_fulcra):
    fake_fulcra.create_data_type.side_effect = http_error(
        422, b'{"detail": "record_spec.schema: field \\"value\\" is reserved"}'
    )
    text = await call(
        "create_data_type",
        {
            "base_type": "event",
            "name": "X",
            "description": "d",
            "fields": {"properties": {"value": {"type": "string"}}},
        },
    )
    assert text == (
        'Could not create data type (HTTP 422): record_spec.schema: field "value" is reserved'
    )


async def test_create_annotation_data_type_is_unchanged(call, fake_fulcra):
    fake_fulcra.create_annotation.return_value = {"id": USER_TYPE_UUID}
    text = await call(
        "create_data_type",
        {"base_type": "boolean", "name": "Took meds", "default_value": "yes", "tags": ["health"]},
    )
    fake_fulcra.create_annotation.assert_called_once_with(
        annotation_type="boolean",
        name="Took meds",
        description=None,
        tags=["health"],
        metric_kind=None,
        value=True,
        unit=None,
        scale_labels=None,
    )
    fake_fulcra.create_data_type.assert_not_called()
    assert text.startswith(f"Created data type BooleanAnnotation/{USER_TYPE_UUID}")


@pytest.mark.parametrize("tool", ["archive_data_type", "restore_data_type"])
@pytest.mark.parametrize("data_type", ["Event", "Metric", "HeartRate", "heart_rate"])
async def test_built_in_types_cannot_be_archived_or_restored(call, fake_fulcra, tool, data_type):
    text = await call(tool, {"data_type": data_type})
    assert text.startswith(f"{data_type!r} is not a user-defined data type ID. Built-in types")
    assert "get_data_catalog" in text
    fake_fulcra.update_data_type.assert_not_called()
    fake_fulcra.delete_annotation.assert_not_called()
    fake_fulcra.restore_annotation.assert_not_called()


@pytest.mark.parametrize("tool", ["archive_data_type", "restore_data_type"])
async def test_archive_refuses_a_malformed_v1_id(call, fake_fulcra, tool):
    text = await call(tool, {"data_type": "Event/not-a-uuid"})
    assert "'Event/<uuid>'" in text
    fake_fulcra.update_data_type.assert_not_called()


@pytest.mark.parametrize(
    "tool, message",
    [
        ("archive_data_type", "No user-defined data type"),
        ("restore_data_type", "No archived data type"),
    ],
)
async def test_archive_unknown_v1_id_is_actionable(call, fake_fulcra, tool, message):
    fake_fulcra.update_data_type.side_effect = http_error(404)
    text = await call(tool, {"data_type": f"Metric/{V1_UUID}"})
    assert text.startswith(message)


async def test_record_data_reports_every_error_from_strict_validation(call, fake_fulcra):
    """drive the SDK's own validate_records (strict since fulcra-api 0.1.43)
    against the type's schema"""
    from fulcra_api.core import FulcraAPI

    type_id = f"Event/{V1_UUID}"
    _v1_type(fake_fulcra, type_id, {**CHECK_IN_SCHEMA, "required": ["mood"]})
    fake_fulcra.validate_records.side_effect = (
        lambda *args, **kwargs: FulcraAPI.validate_records(fake_fulcra, *args, **kwargs)
    )

    text = await call(
        "record_data",
        {"data_type": type_id, "start_time": START, "fields": {"energy": "high"}},
    )
    assert text == (
        f"Record is not valid for {type_id}: 'mood' is a required property; "
        "'high' is not of type 'number' (path: energy)."
    )
    fake_fulcra.record_data_type.assert_not_called()

    # a valid record passes strict validation: everything the tool adds is declared
    await call(
        "record_data",
        {
            "data_type": type_id,
            "start_time": START,
            "end_time": END,
            "tags": ["work"],
            "fields": {"mood": "calm"},
        },
    )
    fake_fulcra.record_data_type.assert_called_once()


@pytest.mark.parametrize("record_type", ["event", "metric"])
async def test_catalog_points_v1_types_to_get_records(call, fake_fulcra, record_type):
    fake_fulcra.v1_catalog.return_value = [
        {"id": "Event", "api_version": "v1", "class": record_type},
        {"id": "DeletedRecord", "api_version": "v1", "class": "tombstone", "queryable": False},
    ]
    grouped = json.loads((text := await call("get_data_catalog"))[text.index("{"):])
    assert [e["id"] for e in grouped["data types usable with: get_records"]] == ["Event"]


async def test_catalog_points_types_with_their_own_tools_to_them(call, fake_fulcra):
    """v0 types with dedicated tools are grouped under them, annotations under
    get_records, and only unknown kinds are left as not yet readable"""
    fake_fulcra.v1_catalog.return_value = [
        {"id": "apple_workouts", "api_version": "v0", "class": "event"},
        {"id": "calendars", "api_version": "v0", "class": "event"},
        {"id": "calendar_events", "api_version": "v0", "class": "event"},
        {"id": "MomentAnnotation", "api_version": "v1alpha1", "class": "event"},
        {"id": f"NumericAnnotation/{V1_UUID}", "api_version": "v1alpha1", "class": "metric"},
        {"id": "SomethingNew", "api_version": "v0", "class": "event"},
    ]
    grouped = json.loads((text := await call("get_data_catalog"))[text.index("{"):])
    ids = {group: [e["id"] for e in entries] for group, entries in grouped.items()}
    assert ids == {
        "data types usable with: get_workouts": ["apple_workouts"],
        "data types usable with: get_calendars": ["calendars"],
        "data types usable with: get_calendar_events": ["calendar_events"],
        "data types usable with: get_records": [
            "MomentAnnotation",
            f"NumericAnnotation/{V1_UUID}",
        ],
        "data types not yet readable through this server": ["SomethingNew"],
    }


SHARER_ID = "5a7a9a1e-0000-4000-8000-0000000000a1"


def _shared_check_in(fake_fulcra):
    """the catalog entry for a Check-in type another user shared with the caller"""
    user_type = f"Event/{V1_UUID}"
    fake_fulcra.v1_catalog.return_value = [
        {
            "id": user_type,
            "name": "Check-in",
            "api_version": "v1",
            "class": "event",
            "categories": ["user_configured", "shared_type"],
            "fulcra_userid": SHARER_ID,
        }
    ]
    return user_type


async def test_catalog_reads_a_shared_types_fields_from_its_owner(call, fake_fulcra):
    """a shared type lives in its owner's account, so its schema has to be asked
    for there; asked for in the caller's own account, it isn't found (404)"""
    user_type = _shared_check_in(fake_fulcra)

    def schema(data_type, api_version, fulcra_userid=None):
        if fulcra_userid != SHARER_ID:
            raise http_error(404, b'{"detail": "not found"}')
        return CHECK_IN_SCHEMA

    fake_fulcra.v1_catalog_schema.side_effect = schema

    text = await call("get_data_catalog", {"data_type": user_type})

    [entry] = [e for group in json.loads(text[text.index("{"):]).values() for e in group]
    assert entry["fields"] == {"energy": "number", "mood": "string", "rested": "boolean"}


async def test_catalog_still_lists_a_type_whose_schema_cant_be_fetched(call, fake_fulcra):
    """the field list is extra; failing to fetch it doesn't fail the lookup"""
    user_type = _shared_check_in(fake_fulcra)
    fake_fulcra.v1_catalog_schema.side_effect = http_error(404, b'{"detail": "not found"}')

    text = await call("get_data_catalog", {"data_type": user_type})

    assert text.startswith("Available data types")
    [entry] = [e for group in json.loads(text[text.index("{"):]).values() for e in group]
    assert entry["id"] == user_type
    assert "fields" not in entry


def _catalog_entry(id: str, owner: str, record_type: str, shared: bool) -> dict:
    return {
        "id": id,
        "api_version": "v1",
        "class": record_type,
        "record_spec": {"type": record_type},
        "fulcra_userid": owner,
        "categories": (["shared_type"] if shared else [])
        + (["user_configured"] if "/" in id else []),
        **({"recordable": False} if shared else {}),
    }


def _entries(text: str) -> list[dict]:
    return [e for group in json.loads(text[text.index("{"):]).values() for e in group]


@pytest.mark.parametrize("base_type, record_type", [("Event", "event"), ("Metric", "metric")])
async def test_catalog_listing_names_the_owner_of_shared_types(
    call, fake_fulcra, base_type, record_type
):
    """a shared built-in type has the same ID as the caller's own; only its owner
    tells them apart, and it's the fulcra_userid a read of it needs"""
    user_type = f"{base_type}/{V1_UUID}"
    fake_fulcra.v1_catalog.return_value = [
        _catalog_entry(base_type, FAKE_USER_ID, record_type, shared=False),
        _catalog_entry(base_type, SHARER_ID, record_type, shared=True),
        _catalog_entry(user_type, SHARER_ID, record_type, shared=True),
    ]

    entries = _entries(await call("get_data_catalog"))

    owners = [(e["id"], e.get("fulcra_userid")) for e in entries]
    # own entries stay as they were: no need to repeat the caller's own ID
    assert owners == [(base_type, None), (base_type, SHARER_ID), (user_type, SHARER_ID)]


@pytest.mark.parametrize("base_type, record_type", [("Event", "event"), ("Metric", "metric")])
async def test_catalog_lookup_names_the_owner_of_a_shared_type(
    call, fake_fulcra, base_type, record_type
):
    user_type = f"{base_type}/{V1_UUID}"
    fake_fulcra.v1_catalog.return_value = [
        _catalog_entry(user_type, SHARER_ID, record_type, shared=True)
    ]
    fake_fulcra.v1_catalog_schema.return_value = CHECK_IN_SCHEMA

    [entry] = _entries(await call("get_data_catalog", {"data_type": user_type}))

    assert entry["fulcra_userid"] == SHARER_ID
    assert entry["fields"] == {"energy": "number", "mood": "string", "rested": "boolean"}


OTHER_SHARER_ID = "5a7a9a1e-0000-4000-8000-0000000000b2"


def _scoped_catalog(fake_fulcra):
    """a catalog that, like data-service, narrows to one owner's entries when
    given fulcra_userid: the caller's own types, plus types two users share"""
    entries = [
        _catalog_entry("Event", FAKE_USER_ID, "event", shared=False),
        _catalog_entry("Event", SHARER_ID, "event", shared=True),
        _catalog_entry(f"Event/{V1_UUID}", SHARER_ID, "event", shared=True),
        _catalog_entry("Metric", OTHER_SHARER_ID, "metric", shared=True),
    ]
    entries[2]["name"] = "Check-in"

    def v1_catalog(data_type=None, category=None, fulcra_userid=None):
        found = [
            e
            for e in entries
            if (data_type is None or e["id"] == data_type)
            and (category is None or category in e["categories"])
            and (fulcra_userid is None or e["fulcra_userid"] == fulcra_userid)
        ]
        if data_type and not found:
            raise http_error(404, b'{"detail": "Type not found"}')
        return found

    fake_fulcra.v1_catalog.side_effect = v1_catalog
    fake_fulcra.v1_catalog_schema.return_value = CHECK_IN_SCHEMA


async def test_catalog_can_be_scoped_to_one_sharer(call, fake_fulcra):
    _scoped_catalog(fake_fulcra)

    entries = _entries(await call("get_data_catalog", {"fulcra_userid": SHARER_ID}))

    fake_fulcra.v1_catalog.assert_called_once_with(
        data_type=None, category=None, fulcra_userid=SHARER_ID
    )
    # only that sharer's types: not the caller's own, nor another sharer's
    assert [(e["id"], e["fulcra_userid"]) for e in entries] == [
        ("Event", SHARER_ID),
        (f"Event/{V1_UUID}", SHARER_ID),
    ]


async def test_catalog_unscoped_still_lists_shared_types(call, fake_fulcra):
    _scoped_catalog(fake_fulcra)

    entries = _entries(await call("get_data_catalog"))

    assert len(entries) == 4


@pytest.mark.parametrize(
    "filters, expected",
    [
        ({"category": "user_configured"}, [f"Event/{V1_UUID}"]),
        ({"name": "check"}, [f"Event/{V1_UUID}"]),
        ({"data_type": f"Event/{V1_UUID}"}, [f"Event/{V1_UUID}"]),
    ],
    ids=["category", "name", "data_type"],
)
async def test_catalog_filters_work_within_a_sharers_scope(call, fake_fulcra, filters, expected):
    _scoped_catalog(fake_fulcra)

    entries = _entries(
        await call("get_data_catalog", {**filters, "fulcra_userid": SHARER_ID})
    )

    assert [e["id"] for e in entries] == expected
    if "data_type" in filters:
        # the field list is read from the owner's account
        fake_fulcra.v1_catalog_schema.assert_called_once_with(
            f"Event/{V1_UUID}", "v1", fulcra_userid=SHARER_ID
        )
        assert entries[0]["fields"]


async def test_catalog_lookup_of_a_type_outside_the_scope(call, fake_fulcra):
    """another sharer's type isn't found within this sharer's scope"""
    _scoped_catalog(fake_fulcra)

    text = await call(
        "get_data_catalog", {"data_type": "Metric", "fulcra_userid": SHARER_ID}
    )

    assert text.startswith(f"No data type found with ID 'Metric' for user {SHARER_ID}.")


async def test_catalog_scoped_to_a_user_who_shares_nothing(call, fake_fulcra):
    _scoped_catalog(fake_fulcra)
    stranger = "5a7a9a1e-0000-4000-8000-0000000000c3"

    text = await call("get_data_catalog", {"fulcra_userid": stranger})

    assert text == (
        f"No data types for user {stranger} match. If this is another user, they "
        "share nothing matching with you; list_shares shows who shares what."
    )
