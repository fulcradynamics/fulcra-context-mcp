"""Group tools: listing, joining, creating, and deleting groups of users."""

import pytest
from fastmcp.exceptions import ToolError

from conftest import http_error

GROUP = "0c47fa97-ac33-4dd8-a229-721ed66e1377"
START = "2026-08-01T00:00:00-07:00"
END = "2026-08-02T00:00:00-07:00"


async def test_get_groups_slims_long_form_fields(call, fake_fulcra):
    fake_fulcra.get_groups.return_value = [
        {
            "id": GROUP,
            "title": "Trip",
            "detail_markdown": "# long",
            "agreement_markdown": "x",
            "annotations": [],
            "header_image_url": None,
            "fulcra_data_types": [],
        }
    ]
    text = await call("get_groups")
    fake_fulcra.get_groups.assert_called_once_with(subscribed_only=False)
    assert "Public and owned groups (1)" in text
    assert "detail_markdown" not in text and "header_image_url" not in text
    assert '"title": "Trip"' in text


async def test_get_groups_subscribed_only_passes_through(call, fake_fulcra):
    fake_fulcra.get_groups.return_value = []
    text = await call("get_groups", {"subscribed_only": True})
    fake_fulcra.get_groups.assert_called_once_with(subscribed_only=True)
    assert "joined" in text


async def test_get_groups_single_group_is_full_record(call, fake_fulcra):
    fake_fulcra.get_group.return_value = {"id": GROUP, "detail_markdown": "# long"}
    text = await call("get_groups", {"group_id": GROUP})
    fake_fulcra.get_group.assert_called_once_with(GROUP)
    fake_fulcra.get_groups.assert_not_called()
    assert "detail_markdown" in text


async def test_get_groups_unknown_id(call, fake_fulcra):
    fake_fulcra.get_group.side_effect = http_error(404)
    text = await call("get_groups", {"group_id": "nope"})
    assert "No group found" in text and "get_groups" in text


async def test_join_group_calls_through_and_maps_404(call, fake_fulcra):
    fake_fulcra.join_group.return_value = {"participant_id": "p1"}
    text = await call("join_group", {"group_id": GROUP})
    fake_fulcra.join_group.assert_called_once_with(GROUP)
    assert "Joined group" in text and "p1" in text
    fake_fulcra.join_group.side_effect = http_error(404)
    assert "No group found" in await call("join_group", {"group_id": "nope"})


async def test_create_group_defaults_to_audience_group(call, fake_fulcra):
    fake_fulcra.create_group.return_value = {"id": GROUP, "title": "Trip", "annotations": []}
    text = await call(
        "create_group",
        {"title": "Trip", "description": "Planning", "responsible_entity": "Me"},
    )
    kwargs = fake_fulcra.create_group.call_args.kwargs
    assert kwargs["fulcra_data_types"] is None
    assert kwargs["time_start"] is None and kwargs["friendly_id"] is None
    fake_fulcra.v1_catalog.assert_not_called()
    assert "Created group" in text and GROUP in text and "annotations" not in text


async def test_create_group_validates_data_types_against_catalog(call, fake_fulcra):
    fake_fulcra.v1_catalog.return_value = [{"id": "StepCount"}]
    text = await call(
        "create_group",
        {
            "title": "Steps",
            "description": "d",
            "responsible_entity": "Me",
            "data_types": ["StepCount", "apple_workouts", "Bogus"],
        },
    )
    assert "not group-shareable" in text and "'Bogus'" in text
    fake_fulcra.create_group.assert_not_called()


async def test_create_group_collecting_group_passes_types_and_range(call, fake_fulcra):
    fake_fulcra.v1_catalog.return_value = [{"id": "StepCount"}]
    fake_fulcra.create_group.return_value = {"id": GROUP}
    await call(
        "create_group",
        {
            "title": "Steps",
            "description": "d",
            "responsible_entity": "Me",
            "data_types": ["StepCount"],
            "time_start": START,
            "time_end": END,
            "friendly_id": "steps-2026",
        },
    )
    kwargs = fake_fulcra.create_group.call_args.kwargs
    assert kwargs["fulcra_data_types"] == ["StepCount"]
    assert kwargs["time_start"].isoformat() == START
    assert kwargs["friendly_id"] == "steps-2026"


async def test_create_group_time_range_requires_data_types(call, fake_fulcra):
    text = await call(
        "create_group",
        {"title": "T", "description": "d", "responsible_entity": "Me", "time_start": START},
    )
    assert "only apply" in text
    fake_fulcra.create_group.assert_not_called()


async def test_create_group_rejects_naive_and_inverted_times(client, call, fake_fulcra):
    base = {"title": "T", "description": "d", "responsible_entity": "Me", "data_types": ["StepCount"]}
    with pytest.raises(ToolError, match="time zone"):
        await client.call_tool("create_group", {**base, "time_start": "2026-08-01T00:00:00"})
    text = await call("create_group", {**base, "time_start": END, "time_end": START})
    assert "must be after" in text
    fake_fulcra.create_group.assert_not_called()


async def test_delete_group_calls_through_and_maps_errors(call, fake_fulcra):
    text = await call("delete_group", {"group_id": GROUP})
    fake_fulcra.delete_group.assert_called_once_with(GROUP)
    assert "Deleted group" in text
    fake_fulcra.delete_group.side_effect = http_error(403)
    assert "owner can delete" in await call("delete_group", {"group_id": GROUP})
    fake_fulcra.delete_group.side_effect = http_error(401)
    text = await call("delete_group", {"group_id": GROUP})
    assert "re-authenticate" in text and "owner" not in text
    fake_fulcra.delete_group.side_effect = http_error(404)
    assert "No group found" in await call("delete_group", {"group_id": "nope"})


async def test_get_group_auth_failure_is_not_reported_as_ownership(call, fake_fulcra):
    fake_fulcra.get_group.side_effect = http_error(401)
    text = await call("get_groups", {"group_id": GROUP})
    assert "re-authenticate" in text and "owner" not in text
