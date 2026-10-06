"""Skill migration contracts, including explicit known compatibility gaps."""

import json

import pytest
from fulcra_api.core import FulcraAPI

from conftest import FAKE_USER_ID, http_error

TYPE_UUID = "33333333-1111-4444-8888-123456789012"
PEER = "22222222-1111-4444-8888-123456789012"
START = "2026-10-05T12:00:00-07:00"
END = "2026-10-05T13:00:00-07:00"


def configure_schema(fake, base, version, fields):
    type_id = f"{base}/{TYPE_UUID}"
    fake.v1_catalog.return_value = [{
        "id": type_id, "api_version": version, "recordable": True,
        "fulcra_userid": FAKE_USER_ID,
    }]
    schema = {"type": "object", "properties": {
        "sources": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string", "format": "uuid"}},
        **fields,
    }}
    fake.v1_catalog_schema.return_value = schema
    fake.validate_records.side_effect = lambda *a, **kw: FulcraAPI.validate_records(fake, *a, **kw)
    fake.record_data_type.return_value = {"upload_id": "audit"}
    fake.create_tags.return_value = [{"id": TYPE_UUID}]
    return type_id


TIME = {"type": "string", "format": "date-time"}
NOTE = {"type": "string"}


@pytest.mark.parametrize("base,value,time", [
    ("MomentAnnotation", None, TIME),
    ("DurationAnnotation", None, {"type": "object", "required": ["start_time", "end_time"],
                                 "properties": {"start_time": TIME, "end_time": TIME}}),
    ("NumericAnnotation", "2.5", TIME),
    ("ScaleAnnotation", "3", TIME),
])
async def test_legacy_annotation_records_with_real_sdk_validation(call, fake_fulcra, base, value, time):
    fields = {"note": NOTE, "recorded_at": time}
    if value:
        fields["value"] = {"type": "number"}
    type_id = configure_schema(fake_fulcra, base, "v1alpha1", fields)
    args = {"data_type": type_id, "note": '{"body":"message"}',
            "start_time": START, "tags": ["audit"]}
    if base == "DurationAnnotation":
        args["end_time"] = END
    if value:
        args["value"] = value
    text = await call("record_data", args)
    assert text.startswith("Recorded 1 "), text
    target, rows, version = fake_fulcra.record_data_type.call_args.args
    assert (target, version) == (base, "v1alpha1")
    assert rows[0]["sources"] == ["com.fulcradynamics.mcp", f"com.fulcradynamics.annotation.{TYPE_UUID}"]
    assert rows[0]["tags"] == [TYPE_UUID]
    assert rows[0]["note"] == args["note"]


@pytest.mark.parametrize("base,value,extra", [
    ("Event", None, {"note": NOTE}),
    ("Event", None, {"coord": {"type": "object", "required": ["body"],
                                "properties": {"body": NOTE}}}),
    ("Metric", "0", {"value": {"type": "number"}, "note": NOTE}),
    ("Metric", "4.5", {"value": {"type": "number"}, "note": NOTE}),
    ("Metric", "3", {"value": {"type": "number"}, "note": NOTE}),
])
async def test_v1_replacements_preserve_message_duration_and_metric_values(call, fake_fulcra, base, value, extra):
    type_id = configure_schema(fake_fulcra, base, "v1", {"start_time": TIME, "end_time": TIME, **extra})
    args = {"data_type": type_id, "start_time": START, "end_time": END, "tags": ["audit"]}
    if "coord" in extra:
        args["fields"] = {"coord": {"body": "message"}}
    else:
        args["note"] = "message"
    if value:
        args["value"] = value
    text = await call("record_data", args)
    assert text.startswith("Recorded 1 "), text
    target, rows, version = fake_fulcra.record_data_type.call_args.args
    assert (target, version) == (type_id, "v1")
    assert "recorded_at" not in rows[0]
    assert rows[0]["start_time"] == START
    assert rows[0]["sources"] == ["com.fulcradynamics.mcp"]


@pytest.mark.parametrize("base", ["Event", "Metric"])
async def test_v1_peer_records_use_full_id_and_owner(call, fake_fulcra, base):
    type_id = f"{base}/{TYPE_UUID}"
    fake_fulcra.resolve_data_type.return_value = [{
        "id": type_id, "api_version": "v1", "record_spec": {"type": base.lower()},
        "fulcra_userid": PEER,
    }]
    fake_fulcra.fulcra_v1_records.return_value = b'{"note":"hello"}\n'
    text = await call("get_records", {"data_type": type_id, "start_time": START,
                                      "end_time": END, "fulcra_userid": PEER})
    assert '"hello"' in text
    fake_fulcra.resolve_data_type.assert_called_once_with(type_id, fulcra_userid=PEER)
    query, = fake_fulcra.fulcra_v1_records.call_args.args
    assert f'{{__name__="{type_id}"}}[3600s]' in query
    assert fake_fulcra.fulcra_v1_records.call_args.kwargs["fulcra_userid"] == PEER


@pytest.mark.parametrize("tool", ["archive_data_type", "restore_data_type"])
async def test_legacy_bare_uuid_lifecycle_still_supported(call, fake_fulcra, tool):
    fake_fulcra.restore_annotation.return_value = {"id": TYPE_UUID}
    text = await call(tool, {"data_type": TYPE_UUID})
    assert text.startswith("Archived" if tool.startswith("archive") else "Restored")
    method = fake_fulcra.delete_annotation if tool.startswith("archive") else fake_fulcra.restore_annotation
    method.assert_called_once_with(TYPE_UUID)


@pytest.mark.xfail(strict=True, reason="BooleanAnnotation's live base schema is numeric; JSON booleans are rejected before upload")
@pytest.mark.parametrize("value", ["true", "false"])
async def test_legacy_boolean_values_remain_recordable(call, fake_fulcra, value):
    type_id = configure_schema(fake_fulcra, "BooleanAnnotation", "v1alpha1", {
        "value": {"type": "number"}, "recorded_at": TIME,
    })
    text = await call("record_data", {"data_type": type_id, "value": value, "start_time": START})
    assert text.startswith("Recorded 1 "), text


@pytest.mark.parametrize("base", ["Event", "Metric"])
async def test_shared_v1_catalog_schema_uses_owner(call, fake_fulcra, base):
    type_id = f"{base}/{TYPE_UUID}"
    fake_fulcra.v1_catalog.return_value = [{
        "id": type_id, "api_version": "v1", "class": base.lower(),
        "fulcra_userid": PEER, "categories": ["shared_type"], "recordable": False,
    }]
    def schema(data_type, version, fulcra_userid=None):
        if fulcra_userid != PEER:
            raise http_error(404)
        return {"properties": {"note": NOTE}}
    fake_fulcra.v1_catalog_schema.side_effect = schema
    text = await call("get_data_catalog", {"data_type": type_id})
    assert text.startswith("Available data types"), text
    entries = [e for g in json.loads(text[text.index("{"):]).values() for e in g]
    assert entries[0]["fields"] == {"note": "string"}
    assert entries[0]["recordable"] is False
    fake_fulcra.v1_catalog_schema.assert_called_once_with(type_id, "v1", fulcra_userid=PEER)


async def test_shared_catalog_preserves_owner(call, fake_fulcra):
    fake_fulcra.v1_catalog.return_value = [{
        "id": f"Event/{TYPE_UUID}", "api_version": "v1", "class": "event",
        "fulcra_userid": PEER, "categories": ["shared_type"], "recordable": False,
    }]
    text = await call("get_data_catalog")
    entries = [e for g in json.loads(text[text.index("{"):]).values() for e in g]
    assert entries[0]["fulcra_userid"] == PEER


async def test_catalog_exposes_nested_message_schema(call, fake_fulcra):
    type_id = f"Event/{TYPE_UUID}"
    fake_fulcra.v1_catalog.return_value = [{"id": type_id, "api_version": "v1", "class": "event"}]
    fake_fulcra.v1_catalog_schema.return_value = {
        "properties": {"coord": {"type": "object", "required": ["body"],
                                   "properties": {"body": NOTE}}}, "required": ["coord"],
    }
    text = await call("get_data_catalog", {"data_type": type_id})
    assert '"body"' in text and '"required"' in text


@pytest.mark.parametrize("tool", ["archive_data_type", "restore_data_type"])
@pytest.mark.parametrize("data_type", [
    f"Event/{TYPE_UUID}/unexpected",
    f"Metric/{TYPE_UUID}x",
    f"MomentAnnotation/{TYPE_UUID}/unexpected",
    f"BooleanAnnotation/{TYPE_UUID}x",
    f"NotAType/{TYPE_UUID}",
    f"/{TYPE_UUID}",
])
async def test_malformed_lifecycle_ids_do_not_mutate_types(call, fake_fulcra, tool, data_type):
    fake_fulcra.update_data_type.return_value = {"id": f"Event/{TYPE_UUID}"}
    text = await call(tool, {"data_type": data_type})
    assert "not a valid ID" in text or "not a user-defined data type ID" in text, text
    fake_fulcra.update_data_type.assert_not_called()
    fake_fulcra.delete_annotation.assert_not_called()
    fake_fulcra.restore_annotation.assert_not_called()


@pytest.mark.parametrize("tool", ["archive_data_type", "restore_data_type"])
async def test_annotation_lifecycle_uses_its_uuid(call, fake_fulcra, tool):
    fake_fulcra.restore_annotation.return_value = {"id": TYPE_UUID}
    text = await call(tool, {"data_type": f"MomentAnnotation/{TYPE_UUID}"})
    assert text.startswith("Archived" if tool.startswith("archive") else "Restored"), text
    method = fake_fulcra.delete_annotation if tool.startswith("archive") else fake_fulcra.restore_annotation
    method.assert_called_once_with(TYPE_UUID)
