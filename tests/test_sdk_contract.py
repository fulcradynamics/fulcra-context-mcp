"""Happy-path contract tests: every tool reaches the SDK method it depends on.

The `fake_fulcra` fixture is autospec'd against `fulcra_api.core.FulcraAPI`, so
each case here fails if a future SDK release renames a method or changes its
signature. That is the gap that let MCP 0.3.0 ship calling a method fulcra-api
0.1.42 no longer had. Behavioural detail belongs in test_tool_quality.py; these
only pin the tool -> SDK wiring.
"""

import json

import pandas as pd
import pytest
from conftest import FAKE_USER_ID

START = "2026-08-01T00:00:00-07:00"
END = "2026-08-02T00:00:00-07:00"
ANN_UUID = "6a0d0d5e-2b7a-4f5c-9c0e-3a3f1b2c4d5e"
FILE_RECORD = {"id": "v1", "name": "a.txt", "path": "/", "size": 5}


async def test_annotations_catalog(call, fake_fulcra):
    fake_fulcra.annotations_catalog.return_value = [{"id": ANN_UUID, "name": "mood"}]
    text = await call("annotations_catalog")
    fake_fulcra.annotations_catalog.assert_called_once_with()
    assert "mood" in text


async def test_create_data_type(call, fake_fulcra):
    fake_fulcra.create_annotation.return_value = {"id": ANN_UUID, "name": "weight"}
    text = await call(
        "create_data_type",
        {
            "base_type": "numeric",
            "name": "weight",
            "unit": "kg",
            "default_value": "1.5",
        },
    )
    kwargs = fake_fulcra.create_annotation.call_args.kwargs
    assert kwargs["annotation_type"] == "numeric"
    assert kwargs["unit"] == "kg"
    assert kwargs["value"] == 1.5
    assert text.startswith(f"Created data type NumericAnnotation/{ANN_UUID}")


async def test_restore_data_type(call, fake_fulcra):
    fake_fulcra.restore_annotation.return_value = {"id": ANN_UUID}
    text = await call(
        "restore_data_type", {"data_type": f"MomentAnnotation/{ANN_UUID}"}
    )
    fake_fulcra.restore_annotation.assert_called_once_with(ANN_UUID)
    assert text.startswith("Restored data type")


async def test_record_data_write_path(call, fake_fulcra):
    type_id = f"MomentAnnotation/{ANN_UUID}"
    fake_fulcra.v1_catalog.return_value = [
        {"id": type_id, "api_version": "v1alpha1", "recordable": True}
    ]
    fake_fulcra.create_tags.return_value = [{"id": "tag-1", "name": "work"}]
    fake_fulcra.validate_records.return_value = []
    fake_fulcra.record_data_type.return_value = {"upload_id": "up-1"}

    text = await call(
        "record_data",
        {"data_type": type_id, "note": "hi", "start_time": START, "tags": ["work"]},
    )

    fake_fulcra.create_tags.assert_called_once_with(["work"])
    (base, records, version), _ = fake_fulcra.validate_records.call_args
    assert (base, version) == ("MomentAnnotation", "v1alpha1")
    fake_fulcra.record_data_type.assert_called_once_with(base, records, version)
    record = records[0]
    assert record["note"] == "hi"
    assert record["tags"] == ["tag-1"]
    assert f"com.fulcradynamics.annotation.{ANN_UUID}" in record["sources"]
    assert "recorded_at" in record
    assert "upload ID up-1" in text


async def test_get_data_catalog(call, fake_fulcra):
    fake_fulcra.v1_catalog.return_value = [
        {
            "id": "heart_rate",
            "name": "Heart Rate",
            "api_version": "v0",
            "class": "metric",
            "queryable": True,
        }
    ]
    text = await call("get_data_catalog")
    fake_fulcra.v1_catalog.assert_called_once_with(data_type=None, category=None)
    assert "heart_rate" in text


@pytest.mark.parametrize(
    "level,method",
    [
        ("cycles", "sleep_cycles"),
        ("stages", "sleep_stages"),
        ("aggregate", "sleep_agg"),
    ],
)
async def test_get_sleep_levels(call, fake_fulcra, level, method):
    getattr(fake_fulcra, method).return_value = pd.DataFrame([{"minutes": 420}])
    text = await call(
        "get_sleep", {"start_time": START, "end_time": END, "level": level}
    )
    assert getattr(fake_fulcra, method).call_count == 1
    assert text.startswith(f"Sleep {level} ")
    assert json.loads(text[text.index("[") :]) == [{"minutes": 420}]


async def test_get_location_time_series(call, fake_fulcra):
    fake_fulcra.location_time_series.return_value = [{"lat": 1.0, "lon": 2.0}]
    text = await call(
        "get_location_time_series", {"start_time": START, "end_time": END}
    )
    kwargs = fake_fulcra.location_time_series.call_args.kwargs
    assert kwargs["look_back"] == 14400
    assert kwargs["sample_rate"] == 900
    assert '"lat": 1.0' in text


CALENDARS = [
    {"calendar_id": "c1", "calendar_name": "Work", "calendar_source_name": "iCloud"}
]


async def test_get_calendars(call, fake_fulcra):
    fake_fulcra.calendars.return_value = CALENDARS
    text = await call("get_calendars")
    fake_fulcra.calendars.assert_called_once_with(fulcra_userid=None)
    assert "iCloud" in text and "Work" in text


async def test_get_calendar_events_by_calendar_name(call, fake_fulcra):
    fake_fulcra.calendars.return_value = CALENDARS
    fake_fulcra.calendar_events.return_value = [
        {"calendar_id": "c1", "title": "Standup"}
    ]
    text = await call(
        "get_calendar_events",
        {"start_time": START, "end_time": END, "calendars": ["work"]},
    )
    assert fake_fulcra.calendar_events.call_args.kwargs["calendar_ids"] == ["c1"]
    assert "Standup" in text and '"calendar_name": "Work"' in text


async def test_list_files_versions(call, fake_fulcra):
    fake_fulcra.resolve_filepath.return_value = [FILE_RECORD]
    text = await call("list_files", {"path": "a.txt", "include_versions": True})
    fake_fulcra.resolve_filepath.assert_called_once_with(
        "/a.txt", all_versions=True, fulcra_userid=None
    )
    assert text.startswith("Versions of /a.txt")


async def test_list_files_falls_back_to_single_file(call, fake_fulcra):
    fake_fulcra.list_files.return_value = {"folders": [], "files": []}
    fake_fulcra.resolve_filepath.return_value = [FILE_RECORD]
    text = await call("list_files", {"path": "a.txt"})
    fake_fulcra.resolve_filepath.assert_called_once_with("/a.txt", fulcra_userid=None)
    assert '"name": "a.txt"' in text


async def test_write_file(call, fake_fulcra):
    fake_fulcra.upload_file.return_value = {"file": FILE_RECORD}
    text = await call("write_file", {"path": "a.txt", "content": "hello"})
    fake_fulcra.upload_file.assert_called_once_with(b"hello", "text/plain", 5, "/a.txt")
    assert text.startswith("Wrote /a.txt")


async def test_delete_file(call, fake_fulcra):
    fake_fulcra.resolve_filepath.return_value = [FILE_RECORD]
    text = await call("delete_file", {"path": "a.txt"})
    fake_fulcra.delete_file.assert_called_once_with("v1")
    assert text == "Deleted /a.txt (version v1)."


async def test_restore_file(call, fake_fulcra):
    fake_fulcra.get_file_by_version.return_value = FILE_RECORD
    fake_fulcra.restore_file.return_value = {**FILE_RECORD, "id": "v2"}
    text = await call("restore_file", {"version_id": "v1"})
    fake_fulcra.get_file_by_version.assert_called_once_with("v1")
    fake_fulcra.restore_file.assert_called_once_with("v1")
    assert text.startswith("Restored /a.txt")


async def test_list_shares_incoming(call, fake_fulcra):
    fake_fulcra.get_shared_datasets.return_value = [
        {"datashare_id": "d1", "grant_type": "user", "sharing_fulcra_userid": "u2"},
        {"datashare_id": "self", "grant_type": "self"},
    ]
    text = await call("list_shares", {"direction": "incoming"})
    fake_fulcra.get_shared_datasets.assert_called_once_with()
    fake_fulcra.get_datashares.assert_not_called()
    payload = json.loads(text[len("Shares: ") :])
    assert payload["own_fulcra_userid"] == FAKE_USER_ID
    assert [s["datashare_id"] for s in payload["incoming"]] == ["d1"]
