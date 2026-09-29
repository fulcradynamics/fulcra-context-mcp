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
    fake_fulcra.resolve_filepath.side_effect = Exception("File not found in Fulcra")
    text = await call("list_files", {"path": "/private/", "fulcra_userid": PARTNER})
    assert "has not shared" in text and "list_shares" in text


async def test_list_files_resolves_single_shared_file_after_folder_403(call, fake_fulcra):
    """Sharing exactly one file: listing it as a folder is denied, but resolving
    the file under its parent folder succeeds."""
    fake_fulcra.list_files.side_effect = http_error(403)
    fake_fulcra.resolve_filepath.return_value = [{"id": "f1", "name": "notes.txt", "path": "/shared"}]
    text = await call("list_files", {"path": "/shared/notes.txt", "fulcra_userid": PARTNER})
    fake_fulcra.resolve_filepath.assert_called_once_with("/shared/notes.txt", fulcra_userid=PARTNER)
    assert "has not shared" not in text
    assert _payload(text)["files"][0]["id"] == "f1"


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


# --- get_data_updates(include_shared=True) ---------------------------------

PEER2 = "22222222-3333-4444-5555-666666666666"


def _incoming(*uids, with_self=True):
    grants = [{"grant_type": "self", "sharing_fulcra_userid": ME}] if with_self else []
    for uid in uids:
        grants.append(
            {"grant_type": "user", "sharing_fulcra_userid": uid, "sharing_fulcra_user_name": "N-" + uid[:2]}
        )
    return grants


async def test_include_shared_fans_out_dedupes_and_skips_self(call, fake_fulcra):
    # PARTNER appears twice (a user grant and a group grant on the same data);
    # ME appears as a group grant from the user's own share to a group they joined.
    fake_fulcra.get_fulcra_userid.return_value = ME
    fake_fulcra.get_shared_datasets.return_value = _incoming(PARTNER, PARTNER, ME, PEER2)
    own = {"data_types": {"StepCount": 3}, "file_changes": []}
    changed = {"data_types": {}, "file_changes": [{"full_name": "/shared/x.json"}]}
    quiet = {"data_types": {}, "file_changes": []}
    fake_fulcra.data_updates.side_effect = lambda s, e, fulcra_userid=None: {
        None: own, PARTNER: changed, PEER2: quiet
    }[fulcra_userid]
    text = await call(
        "get_data_updates", {"start_time": START, "end_time": END, "include_shared": True}
    )
    result = _payload(text)
    assert result["data_types"] == {"StepCount": 3}
    assert result["peers_checked"] == 2
    assert list(result["shared"]) == [PARTNER]
    assert result["shared"][PARTNER]["name"] == "N-11"
    assert result["shared"][PARTNER]["file_changes"][0]["full_name"] == "/shared/x.json"
    called = [c.kwargs.get("fulcra_userid") for c in fake_fulcra.data_updates.call_args_list]
    assert called == [None, PARTNER, PEER2]


async def test_include_shared_isolates_a_failing_peer(call, fake_fulcra):
    fake_fulcra.get_shared_datasets.return_value = _incoming(PARTNER, PEER2)
    changed = {"data_types": {"HeartRate": 1}, "file_changes": []}

    def updates(s, e, fulcra_userid=None):
        if fulcra_userid == PARTNER:
            raise http_error(403)
        return changed if fulcra_userid == PEER2 else {"data_types": {}, "file_changes": []}

    fake_fulcra.data_updates.side_effect = updates
    result = _payload(
        await call("get_data_updates", {"start_time": START, "end_time": END, "include_shared": True})
    )
    assert result["shared"][PARTNER] == {"name": "N-11", "error": "HTTP 403"}
    assert result["shared"][PEER2]["data_types"] == {"HeartRate": 1}
    assert result["peers_checked"] == 2


async def test_include_shared_with_no_peers(call, fake_fulcra):
    fake_fulcra.get_shared_datasets.return_value = _incoming()
    fake_fulcra.data_updates.return_value = {"data_types": {}, "file_changes": []}
    result = _payload(
        await call("get_data_updates", {"start_time": START, "end_time": END, "include_shared": True})
    )
    assert result["shared"] == {} and result["peers_checked"] == 0


async def test_include_shared_and_user_id_are_exclusive(call, fake_fulcra):
    text = await call(
        "get_data_updates",
        {"start_time": START, "end_time": END, "include_shared": True, "fulcra_userid": PARTNER},
    )
    assert "not both" in text
    fake_fulcra.data_updates.assert_not_called()


async def test_flag_off_does_not_consult_shares(call, fake_fulcra):
    fake_fulcra.data_updates.return_value = {"data_types": {}, "file_changes": []}
    result = _payload(await call("get_data_updates", {"start_time": START, "end_time": END}))
    fake_fulcra.get_shared_datasets.assert_not_called()
    assert "shared" not in result


# --- fan-out runs off the event loop, sequentially, bounded ----------------


async def test_include_shared_does_not_block_the_event_loop(call, fake_fulcra):
    import asyncio
    import threading
    import time

    loop_thread = threading.get_ident()
    seen_threads: list[int] = []

    def slow_updates(s, e, fulcra_userid=None):
        seen_threads.append(threading.get_ident())
        time.sleep(0.05)
        return {"data_types": {}, "file_changes": []}

    fake_fulcra.get_fulcra_userid.return_value = ME
    fake_fulcra.get_shared_datasets.return_value = _incoming(PARTNER, PEER2, "3" * 36, "4" * 36)
    fake_fulcra.data_updates.side_effect = slow_updates

    ticks = 0

    async def ticker(stop: asyncio.Event):
        nonlocal ticks
        while not stop.is_set():
            ticks += 1
            await asyncio.sleep(0.005)

    stop = asyncio.Event()
    task = asyncio.create_task(ticker(stop))
    result = _payload(
        await call("get_data_updates", {"start_time": START, "end_time": END, "include_shared": True})
    )
    stop.set()
    await task
    # 5 blocking calls x 50 ms = 250 ms; a blocked loop would tick ~once.
    assert ticks >= 10, f"event loop only ticked {ticks} times during the fan-out"
    assert result["peers_checked"] == 4
    assert loop_thread not in seen_threads, "network calls ran on the event loop thread"
    assert len(set(seen_threads)) == 1, "peer calls should be sequential in one worker thread"


async def test_include_shared_caps_peer_count(call, fake_fulcra):
    fake_fulcra.get_fulcra_userid.return_value = ME
    fake_fulcra.get_shared_datasets.return_value = _incoming(*[f"{i:08d}-0000-4000-8000-000000000000" for i in range(25)])
    fake_fulcra.data_updates.return_value = {"data_types": {}, "file_changes": []}
    result = _payload(
        await call("get_data_updates", {"start_time": START, "end_time": END, "include_shared": True})
    )
    assert result["peers_checked"] == 20
    assert result["peers_skipped"] == [f"{i:08d}-0000-4000-8000-000000000000" for i in range(20, 25)]
    assert fake_fulcra.data_updates.call_count == 1 + 20
    # The skipped IDs are exactly the ones the caller can poll one at a time.
    assert not set(result["peers_skipped"]) & set(result["shared"])


async def test_include_shared_isolates_a_timed_out_peer(call, fake_fulcra):
    fake_fulcra.get_fulcra_userid.return_value = ME
    fake_fulcra.get_shared_datasets.return_value = _incoming(PARTNER, PEER2)

    def updates(s, e, fulcra_userid=None):
        if fulcra_userid == PARTNER:
            raise TimeoutError("timed out")
        return {"data_types": {"HeartRate": 1}, "file_changes": []} if fulcra_userid else {"data_types": {}, "file_changes": []}

    fake_fulcra.data_updates.side_effect = updates
    result = _payload(
        await call("get_data_updates", {"start_time": START, "end_time": END, "include_shared": True})
    )
    assert result["shared"][PARTNER]["error"] == "timeout"
    assert result["shared"][PEER2]["data_types"] == {"HeartRate": 1}


async def test_network_timeout_is_reported_not_raised(call, fake_fulcra):
    import urllib.error

    fake_fulcra.data_updates.side_effect = urllib.error.URLError("timed out")
    text = await call("get_data_updates", {"start_time": START, "end_time": END})
    assert "did not respond" in text and "support@fulcradynamics.com" in text


def test_server_startup_sets_network_timeout():
    import socket

    import fulcra_mcp.main  # noqa: F401  (module import applies the setting)
    from fulcra_mcp.settings import settings

    assert settings.http_timeout_seconds == 30.0
    assert socket.getdefaulttimeout() == settings.http_timeout_seconds
