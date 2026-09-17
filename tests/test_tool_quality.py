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
