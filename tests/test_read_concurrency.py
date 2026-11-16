"""Read tools leave the event loop free while the synchronous SDK waits."""
import asyncio
from contextvars import ContextVar
import threading
from unittest.mock import Mock

import pytest

from fulcra_mcp import tools


@pytest.mark.parametrize("name,args,method", [
    ("get_data_catalog", {}, "v1_catalog"),
    ("list_shares", {}, "get_datashares"),
    ("get_records", {"data_type": "Event/00000000-0000-0000-0000-000000000001", "latest": True}, "resolve_data_type"),
])
async def test_read_tools_run_sdk_off_loop_with_request_context(monkeypatch, name, args, method):
    request = ContextVar("request")
    request.set("current-user")
    loop_thread = threading.get_ident()

    def read(*args, **kwargs):
        assert threading.get_ident() != loop_thread, "SDK I/O must not block the event loop"
        assert request.get() == "current-user"
        return []

    api = Mock()
    getattr(api, method).side_effect = read
    api.get_shared_datasets.return_value = []
    monkeypatch.setattr(tools, "get_fulcra_object", lambda: api)
    monkeypatch.setattr(tools, "_own_userid", lambda api: "me")
    await getattr(tools, name)(**args)


async def test_parallel_record_reads_overlap(monkeypatch):
    barrier = threading.Barrier(2)
    api = Mock()

    def resolve(*args, **kwargs):
        try:
            barrier.wait(timeout=1)
        except threading.BrokenBarrierError:
            pytest.fail("Parallel reads must reach the SDK concurrently")
        return []

    api.resolve_data_type.side_effect = resolve
    monkeypatch.setattr(tools, "get_fulcra_object", lambda: api)
    await asyncio.gather(*(tools.get_records(
        "Event/00000000-0000-0000-0000-000000000001", latest=True,
    ) for _ in range(2)))


def test_parallel_first_reads_share_one_stdio_client(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import time
    from fulcra_mcp import credentials

    monkeypatch.setattr(credentials.settings, 'fulcra_environment', 'stdio')
    monkeypatch.setattr(credentials, 'stdio_fulcra', None)
    def load():
        time.sleep(.02)
        return object()
    constructor = Mock(side_effect=lambda **kwargs: object())
    monkeypatch.setattr(credentials, '_load_stdio_credentials', load)
    monkeypatch.setattr(credentials, 'SynchronizedFulcraAPI', constructor)
    start = threading.Barrier(2)
    def read(_):
        start.wait(timeout=1)
        return credentials.get_fulcra_object()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(read, range(2))
    assert first is second
    constructor.assert_called_once()


def test_parallel_first_reads_share_one_hosted_grant(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import time
    from fulcra_api.credentials import FulcraCredentials
    from fulcra_mcp.provider import oauth_provider

    monkeypatch.setattr(oauth_provider, 'grant_credentials', {})
    def load():
        time.sleep(.02)
        return FulcraCredentials(access_token='synthetic').to_json()
    path = Mock()
    path.read_text.side_effect = load
    monkeypatch.setattr(oauth_provider, '_grant_path', lambda grant: path)
    start = threading.Barrier(2)
    def read(_):
        start.wait(timeout=1)
        return oauth_provider._load_grant('cold-read-test')
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(read, range(2))
    assert first is second
    path.read_text.assert_called_once()
