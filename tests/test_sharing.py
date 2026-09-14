"""Sharing tools: datashare creation/updates and reading another user's shared files."""

import json

import pytest
from fastmcp.exceptions import ToolError

from conftest import http_error

PARTNER = "11111111-2222-3333-4444-555555555555"
ME = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
START = "2026-08-01T00:00:00-07:00"
END = "2026-08-02T00:00:00-07:00"


def _payload(text: str) -> dict | list:
    return json.loads(text[text.index(("{" if "{" in text else "[")):])


# --- create_share ---------------------------------------------------------


async def test_create_share_maps_folders_and_files_to_file_prefixes(call, fake_fulcra):
    # The server wraps the created record: {"datashare": {...}}.
    fake_fulcra.create_datashare.return_value = {
        "datashare": {
            "datashare_id": "s1",
            "datashare_name": "trip",
            "fulcra_data_types": ["file:/shared/trip/", "file:/notes.md", "calendar_events"],
            "permissions": [{"allowed_fulcra_userid": PARTNER}],
            "share_all_data": False,
        }
    }
    text = await call(
        "create_share",
        {
            "name": "trip",
            "with_user_ids": [PARTNER],
            "file_paths": ["shared/trip/", "/notes.md"],
            "data_types": ["calendar_events"],
        },
    )
    kwargs = fake_fulcra.create_datashare.call_args.kwargs
    assert kwargs["fulcra_data_types"] == [
        "calendar_events",
        "file:/notes.md",
        "file:/shared/trip/",
    ]
    assert kwargs["allowed_user_ids"] == [PARTNER]
    assert kwargs["allowed_group_ids"] is None
    assert kwargs["share_all_data"] is False
    slim = _payload(text)
    assert slim["datashare_id"] == "s1"
    assert slim["file_paths"] == ["/shared/trip/", "/notes.md"]
    assert slim["data_types"] == ["calendar_events"]
    assert slim["with_user_ids"] == [PARTNER]
    assert "permissions" not in slim


async def test_create_share_file_history_prefix(call, fake_fulcra):
    fake_fulcra.create_datashare.return_value = {}
    await call(
        "create_share",
        {
            "name": "h",
            "with_user_ids": [PARTNER],
            "file_paths": ["/shared/"],
            "include_file_history": True,
        },
    )
    kwargs = fake_fulcra.create_datashare.call_args.kwargs
    assert kwargs["fulcra_data_types"] == ["filehistory:/shared/"]


async def test_create_share_root_folder_is_single_slash(call, fake_fulcra):
    fake_fulcra.create_datashare.return_value = {}
    await call(
        "create_share", {"name": "all files", "with_user_ids": [PARTNER], "file_paths": ["/"]}
    )
    assert fake_fulcra.create_datashare.call_args.kwargs["fulcra_data_types"] == ["file:/"]


@pytest.mark.parametrize("bad", ["", " ", ".", "./", "/./", "/shared/../", "a/../.."])
async def test_create_share_rejects_paths_that_could_widen_to_root(call, fake_fulcra, bad):
    text = await call(
        "create_share", {"name": "x", "with_user_ids": [PARTNER], "file_paths": [bad]}
    )
    assert "Invalid share path" in text
    fake_fulcra.create_datashare.assert_not_called()


async def test_create_share_normalizes_ordinary_paths(call, fake_fulcra):
    fake_fulcra.create_datashare.return_value = {}
    await call(
        "create_share",
        {"name": "x", "with_user_ids": [PARTNER], "file_paths": [" shared//trip/ ", "a/b.txt"]},
    )
    assert fake_fulcra.create_datashare.call_args.kwargs["fulcra_data_types"] == [
        "file:/a/b.txt",
        "file:/shared/trip/",
    ]


@pytest.mark.parametrize(
    "args, expected",
    [
        ({"name": "x", "file_paths": ["/a/"]}, "with_user_ids or with_group_ids"),
        ({"name": "x", "with_user_ids": [PARTNER]}, "Nothing to share"),
        (
            {"name": "x", "with_user_ids": [PARTNER], "share_all_data": True, "file_paths": ["/a/"]},
            "cannot be combined",
        ),
    ],
)
async def test_create_share_argument_guards(call, fake_fulcra, args, expected):
    text = await call("create_share", args)
    assert expected in text
    fake_fulcra.create_datashare.assert_not_called()


@pytest.mark.parametrize("bounds", [{"time_start": START}, {"time_end": END}, {"time_start": START, "time_end": END}])
async def test_create_share_rejects_time_bounds_on_file_shares(call, fake_fulcra, bounds):
    text = await call(
        "create_share",
        {"name": "x", "with_user_ids": [PARTNER], "file_paths": ["/shared/"], **bounds},
    )
    assert "never time-bounded" in text
    fake_fulcra.create_datashare.assert_not_called()


async def test_create_share_rejects_naive_times(client, fake_fulcra):
    with pytest.raises(ToolError, match="time zone"):
        await client.call_tool(
            "create_share",
            {
                "name": "x",
                "with_user_ids": [PARTNER],
                "data_types": ["StepCount"],
                "time_start": "2026-08-01T00:00:00",
            },
        )
    fake_fulcra.create_datashare.assert_not_called()


async def test_create_share_passes_groups_and_time_bounds(call, fake_fulcra):
    fake_fulcra.create_datashare.return_value = {}
    await call(
        "create_share",
        {
            "name": "x",
            "with_group_ids": ["g1"],
            "data_types": ["StepCount"],
            "time_start": START,
            "time_end": END,
        },
    )
    kwargs = fake_fulcra.create_datashare.call_args.kwargs
    assert kwargs["allowed_group_ids"] == ["g1"]
    assert kwargs["allowed_user_ids"] is None
    assert kwargs["time_start"].isoformat() == START
    assert kwargs["time_end"].isoformat() == END


# --- list_shares ----------------------------------------------------------


async def test_list_shares_filters_self_grant_and_flattens(call, fake_fulcra):
    fake_fulcra.get_fulcra_userid.return_value = ME
    fake_fulcra.get_datashares.return_value = [
        {
            "datashare_id": "out1",
            "datashare_name": "trip",
            "sharing_fulcra_user_picture": "http://x/pic.png",
            "fulcra_data_types": ["file:/shared/trip/", "filehistory:/old/"],
            "permissions": [{"allowed_fulcra_userid": PARTNER}],
            "group_permissions": [{"allowed_group_id": "g1"}],
            "share_all_data": False,
        }
    ]
    fake_fulcra.get_shared_datasets.return_value = [
        {"grant_type": "self", "sharing_fulcra_userid": ME, "fulcra_data_types": [], "share_all_data": True},
        {
            "grant_type": "user",
            "grant_id": "grant1",
            "datashare_id": "in1",
            "sharing_fulcra_userid": PARTNER,
            "sharing_fulcra_user_name": "Partner",
            "fulcra_data_types": ["file:/shared/trip/", "calendar_events"],
            "share_all_data": False,
        },
    ]
    result = _payload(await call("list_shares"))
    assert result["own_fulcra_userid"] == ME
    out = result["outgoing"][0]
    assert out["file_paths"] == ["/shared/trip/"]
    assert out["file_history_paths"] == ["/old/"]
    assert out["with_user_ids"] == [PARTNER]
    assert out["with_group_ids"] == ["g1"]
    assert "sharing_fulcra_user_picture" not in out
    assert [g["grant_id"] for g in result["incoming"]] == ["grant1"]
    inc = result["incoming"][0]
    assert inc["sharing_fulcra_userid"] == PARTNER
    assert inc["data_types"] == ["calendar_events"]


async def test_list_shares_direction_limits_calls(call, fake_fulcra):
    fake_fulcra.get_fulcra_userid.return_value = ME
    fake_fulcra.get_datashares.return_value = []
    result = _payload(await call("list_shares", {"direction": "outgoing"}))
    assert "incoming" not in result
    fake_fulcra.get_shared_datasets.assert_not_called()


async def test_list_shares_survives_missing_own_id(call, fake_fulcra):
    fake_fulcra.get_fulcra_userid.side_effect = Exception("no token")
    fake_fulcra.get_datashares.return_value = []
    fake_fulcra.get_shared_datasets.return_value = []
    result = _payload(await call("list_shares"))
    assert "own_fulcra_userid" not in result


# --- delete_share --------------------------------------------------------


async def test_delete_share_unknown_id(call, fake_fulcra):
    fake_fulcra.delete_datashare.side_effect = http_error(403)
    text = await call("delete_share", {"share_id": "nope"})
    assert "No share" in text


async def test_delete_share_calls_through(call, fake_fulcra):
    text = await call("delete_share", {"share_id": "s1"})
    fake_fulcra.delete_datashare.assert_called_once_with("s1")
    assert "Deleted share s1" in text


# --- reading another user's shared data -----------------------------------


async def test_list_files_passes_user_id_and_maps_403(call, fake_fulcra):
    fake_fulcra.list_files.return_value = {"folders": ["a"], "files": []}
    text = await call("list_files", {"path": "/shared/", "fulcra_userid": PARTNER})
    fake_fulcra.list_files.assert_called_once_with("/shared", fulcra_userid=PARTNER)
    assert PARTNER in text
    fake_fulcra.list_files.side_effect = http_error(403)
    text = await call("list_files", {"path": "/private/", "fulcra_userid": PARTNER})
    assert "has not shared" in text and "list_shares" in text


async def test_list_files_without_user_id_keeps_old_error(call, fake_fulcra):
    fake_fulcra.list_files.return_value = {"folders": [], "files": []}
    fake_fulcra.resolve_filepath.side_effect = Exception("nope")
    text = await call("list_files", {"path": "/missing"})
    assert "No folder or file found" in text
    fake_fulcra.list_files.assert_called_once_with("/missing", fulcra_userid=None)


async def test_read_file_passes_user_id_to_resolve_and_download(call, fake_fulcra):
    import io

    fake_fulcra.resolve_filepath.return_value = [{"id": "f1"}]
    fake_fulcra.download_file.return_value = io.BytesIO(b"hello")
    text = await call("read_file", {"path": "/shared/x.txt", "fulcra_userid": PARTNER})
    assert text.endswith("hello")
    fake_fulcra.resolve_filepath.assert_called_once_with("/shared/x.txt", fulcra_userid=PARTNER)
    fake_fulcra.download_file.assert_called_once_with("f1", fulcra_userid=PARTNER)


async def test_read_file_not_shared_message(call, fake_fulcra):
    fake_fulcra.resolve_filepath.side_effect = http_error(403)
    text = await call("read_file", {"path": "/x", "fulcra_userid": PARTNER})
    assert "has not shared" in text


async def test_data_updates_and_workouts_pass_user_id(call, fake_fulcra):
    fake_fulcra.data_updates.return_value = {"data_types": {}, "file_changes": []}
    text = await call(
        "get_data_updates", {"start_time": START, "end_time": END, "fulcra_userid": PARTNER}
    )
    assert fake_fulcra.data_updates.call_args.kwargs["fulcra_userid"] == PARTNER
    assert PARTNER in text
    fake_fulcra.apple_workouts.return_value = []
    await call("get_workouts", {"start_time": START, "end_time": END, "fulcra_userid": PARTNER})
    assert fake_fulcra.apple_workouts.call_args.kwargs["fulcra_userid"] == PARTNER


async def test_time_series_passes_user_id_only_when_given(call, fake_fulcra):
    import pandas as pd

    fake_fulcra.metric_time_series.return_value = pd.DataFrame()
    await call(
        "get_time_series",
        {"data_type": "HeartRate", "start_time": START, "end_time": END, "sample_rate": 3600},
    )
    assert "fulcra_userid" not in fake_fulcra.metric_time_series.call_args.kwargs
    await call(
        "get_time_series",
        {
            "data_type": "HeartRate",
            "start_time": START,
            "end_time": END,
            "sample_rate": 3600,
            "fulcra_userid": PARTNER,
        },
    )
    assert fake_fulcra.metric_time_series.call_args.kwargs["fulcra_userid"] == PARTNER
