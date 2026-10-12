"""Tools an agent needs to run a private channel with another user's agent
(PLAT-668): record ids from record_data, delete_records, leave_share, and
telling an ended share apart from a wrong data type ID."""

from uuid import UUID

import pytest

from conftest import FAKE_USER_ID, http_error

PARTNER = "11111111-2222-3333-4444-555555555555"
CHANNEL = "Event/df10403a-2115-4254-9e49-e48ca0af6f5d"
THEIR_CHANNEL = "Event/7b0c5a51-3e6b-4f6e-9a7e-2f1d0f0c9a11"
START = "2026-08-01T00:00:00-07:00"
END = "2026-08-02T00:00:00-07:00"
ID_A = "8d3b1c2e-1111-4a5b-9c6d-7e8f9a0b1c2d"
ID_B = "8d3b1c2e-2222-4a5b-9c6d-7e8f9a0b1c2d"

CHANNEL_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"anyOf": [{"type": "string", "format": "uuid"}, {"type": "null"}]},
        "sources": {"anyOf": [{"type": "array"}, {"type": "null"}]},
        "start_time": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "sender": {"type": "string"},
        "kind": {"type": "string"},
        "body": {"type": "string"},
    },
}
MESSAGE = {"sender": "alice-claude", "kind": "message", "body": "hi"}


def _own_channel(fake_fulcra, type_id=CHANNEL, owner=FAKE_USER_ID, api_version="v1"):
    fake_fulcra.v1_catalog.return_value = [
        {"id": type_id, "api_version": api_version, "recordable": True, "fulcra_userid": owner}
    ]
    fake_fulcra.v1_catalog_schema.return_value = CHANNEL_SCHEMA
    fake_fulcra.validate_records.return_value = []
    fake_fulcra.record_data_type.return_value = {"upload_id": "up-1"}


def _uploaded(fake_fulcra) -> tuple[str, list[dict], str]:
    (target, records, version), _ = fake_fulcra.record_data_type.call_args
    return target, records, version


# --- record_data returns the record's id ------------------------------------


async def test_record_data_gives_a_v1_record_an_id_and_reports_it(call, fake_fulcra):
    _own_channel(fake_fulcra)

    text = await call("record_data", {"data_type": CHANNEL, "fields": MESSAGE})

    _, [record], _ = _uploaded(fake_fulcra)
    record_id = record["id"]
    assert str(UUID(record_id)) == record_id
    assert f"record with id {record_id}" in text


async def test_record_data_ids_differ_between_sends(call, fake_fulcra):
    _own_channel(fake_fulcra)

    await call("record_data", {"data_type": CHANNEL, "fields": MESSAGE})
    first = _uploaded(fake_fulcra)[1][0]["id"]
    await call("record_data", {"data_type": CHANNEL, "fields": MESSAGE})
    second = _uploaded(fake_fulcra)[1][0]["id"]

    assert first != second


async def test_record_data_uses_a_given_record_id(call, fake_fulcra):
    _own_channel(fake_fulcra)

    text = await call(
        "record_data",
        {"data_type": CHANNEL, "fields": MESSAGE, "record_id": ID_A.upper()},
    )

    _, [record], _ = _uploaded(fake_fulcra)
    assert record["id"] == ID_A
    assert f"with id {ID_A}" in text


async def test_record_data_refuses_a_malformed_record_id(call, fake_fulcra):
    _own_channel(fake_fulcra)

    text = await call(
        "record_data", {"data_type": CHANNEL, "fields": MESSAGE, "record_id": "msg-1"}
    )

    assert text.startswith("record_id must be a UUID")
    fake_fulcra.record_data_type.assert_not_called()


async def test_record_id_is_only_for_v1_types(call, fake_fulcra):
    _own_channel(fake_fulcra, type_id="MomentAnnotation/" + ID_B, api_version="v1alpha1")

    text = await call(
        "record_data",
        {"data_type": "MomentAnnotation/" + ID_B, "note": "x", "record_id": ID_A},
    )

    assert text.startswith("record_id applies only to v1 data types")
    fake_fulcra.record_data_type.assert_not_called()


async def test_fields_point_to_record_id_for_the_id(call, fake_fulcra):
    _own_channel(fake_fulcra)

    text = await call("record_data", {"data_type": CHANNEL, "fields": {**MESSAGE, "id": ID_A}})

    assert text.startswith("fields can't set id;")
    assert "record_id" in text


# --- delete_records -----------------------------------------------------------


async def test_delete_records_sends_a_deletion_for_each_record(call, fake_fulcra):
    _own_channel(fake_fulcra)

    text = await call(
        "delete_records", {"data_type": CHANNEL, "record_ids": [ID_A, ID_B.upper(), ID_A]}
    )

    target, deletions, version = _uploaded(fake_fulcra)
    assert (target, version) == ("DeletedRecord", "v1")
    # one per distinct id, naming the base type, as `fulcra delete` does
    assert deletions == [
        {"record_id": ID_A, "data_type": "Event"},
        {"record_id": ID_B, "data_type": "Event"},
    ]
    fake_fulcra.validate_records.assert_called_once_with("DeletedRecord", deletions, "v1")
    assert text.startswith(f"Deleting 2 records from {CHANNEL} (upload ID up-1)")


@pytest.mark.parametrize(
    "record_ids,expected",
    [
        ([], "record_ids is empty"),
        (["not-an-id"], "Record ids are UUIDs"),
        ([ID_A] * 501, "At most 500 records"),
    ],
)
async def test_delete_records_refuses_bad_ids(call, fake_fulcra, record_ids, expected):
    _own_channel(fake_fulcra)

    text = await call("delete_records", {"data_type": CHANNEL, "record_ids": record_ids})

    assert text.startswith(expected)
    fake_fulcra.record_data_type.assert_not_called()


async def test_delete_records_refuses_another_users_type(call, fake_fulcra):
    # their channel, as shared with this user, is in their account
    _own_channel(fake_fulcra, type_id=THEIR_CHANNEL, owner=PARTNER)

    text = await call("delete_records", {"data_type": THEIR_CHANNEL, "record_ids": [ID_A]})

    assert "records can only be deleted from your own types" in text
    fake_fulcra.record_data_type.assert_not_called()


async def test_delete_records_is_for_v1_types(call, fake_fulcra):
    _own_channel(fake_fulcra, type_id="MomentAnnotation/" + ID_B, api_version="v1alpha1")

    text = await call(
        "delete_records", {"data_type": "MomentAnnotation/" + ID_B, "record_ids": [ID_A]}
    )

    assert text.startswith("delete_records works on recordable v1 data types")
    fake_fulcra.record_data_type.assert_not_called()


async def test_delete_records_unknown_type(call, fake_fulcra):
    fake_fulcra.v1_catalog.side_effect = http_error(404, b'{"detail": "Type not found"}')

    text = await call("delete_records", {"data_type": CHANNEL, "record_ids": [ID_A]})

    assert text.startswith(f"No data type found with ID {CHANNEL!r}")


# --- leave_share --------------------------------------------------------------

GRANT = "c0ffee00-0000-4000-8000-000000000001"


def _incoming(fake_fulcra, grant_type="user", **extra):
    fake_fulcra.get_shared_datasets.return_value = [
        {"grant_type": "self", "grant_id": None, "sharing_fulcra_userid": FAKE_USER_ID},
        {
            "grant_type": grant_type,
            "grant_id": GRANT,
            "datashare_name": "connect-agents-with-anyone: Bob with Alice",
            "sharing_fulcra_userid": PARTNER,
            "sharing_fulcra_user_name": "Bob",
            "fulcra_data_types": [THEIR_CHANNEL],
            **extra,
        },
    ]


async def test_leave_share_removes_a_direct_share(call, fake_fulcra):
    _incoming(fake_fulcra)

    text = await call("leave_share", {"grant_id": GRANT.upper()})

    fake_fulcra.delete_dataset_permission.assert_called_once_with(GRANT)
    assert "from Bob" in text and "no longer has access" in text


async def test_leave_share_refuses_a_group_share(call, fake_fulcra):
    _incoming(fake_fulcra, grant_type="group", group_id="g-1")

    text = await call("leave_share", {"grant_id": GRANT})

    assert "group g-1" in text and "leave_group" in text
    fake_fulcra.delete_dataset_permission.assert_not_called()


@pytest.mark.parametrize(
    "grant_id,expected",
    [("not-a-grant", "grant_id must be a UUID"), (ID_A, "No incoming share with grant_id")],
)
async def test_leave_share_refuses_unknown_grants(call, fake_fulcra, grant_id, expected):
    _incoming(fake_fulcra)

    text = await call("leave_share", {"grant_id": grant_id})

    assert text.startswith(expected)
    fake_fulcra.delete_dataset_permission.assert_not_called()


# --- an ended share reads differently from a wrong ID ------------------------


def _not_found(fake_fulcra):
    fake_fulcra.resolve_data_type.side_effect = ValueError("Type not found")


async def test_get_records_when_they_no_longer_share_anything(call, fake_fulcra):
    _not_found(fake_fulcra)
    fake_fulcra.get_shared_datasets.return_value = []

    text = await call(
        "get_records",
        {"data_type": THEIR_CHANNEL, "start_time": START, "end_time": END, "fulcra_userid": PARTNER},
    )

    assert text.startswith(f"User {PARTNER} doesn't share any data with this user, or no longer does")


async def test_get_records_when_they_share_other_things(call, fake_fulcra):
    _not_found(fake_fulcra)
    _incoming(fake_fulcra, fulcra_data_types=["StepCount"])

    text = await call(
        "get_records",
        {"data_type": THEIR_CHANNEL, "start_time": START, "end_time": END, "fulcra_userid": PARTNER},
    )

    assert text.startswith(f"User {PARTNER} shares data with this user, but not {THEIR_CHANNEL!r}")


@pytest.mark.parametrize("shared", [[THEIR_CHANNEL], ["Event"]])
async def test_get_records_when_it_is_shared_but_not_found(call, fake_fulcra, shared):
    # shared by its exact ID or through its base type: a different problem
    _not_found(fake_fulcra)
    _incoming(fake_fulcra, fulcra_data_types=shared)

    text = await call(
        "get_records",
        {"data_type": THEIR_CHANNEL, "start_time": START, "end_time": END, "fulcra_userid": PARTNER},
    )

    assert text.startswith(f"No data type found with ID {THEIR_CHANNEL!r}")


async def test_get_records_own_data_keeps_the_plain_message(call, fake_fulcra):
    _not_found(fake_fulcra)

    text = await call("get_records", {"data_type": "NotAThing", "start_time": START, "end_time": END})

    assert text.startswith("No data type found with ID 'NotAThing'")
    fake_fulcra.get_shared_datasets.assert_not_called()


async def test_catalog_lookup_after_the_share_ended(call, fake_fulcra):
    fake_fulcra.v1_catalog.side_effect = http_error(404, b'{"detail": "Type not found"}')
    fake_fulcra.get_shared_datasets.return_value = []

    text = await call("get_data_catalog", {"data_type": THEIR_CHANNEL, "fulcra_userid": PARTNER})

    assert text.startswith(f"User {PARTNER} doesn't share any data with this user")
