"""PLAT-967: a stdio server without saved credentials keeps answering while the
device-code login waits. get_fulcra_object() runs on the event loop, so it must
never wait on the network or on the user."""

import asyncio
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastmcp.exceptions import ToolError
from fulcra_api.credentials import FulcraCredentials

from fulcra_mcp import credentials
from fulcra_mcp.settings import settings

# Far below any wait the implementation could reasonably want; the old code
# waited up to 30 seconds here.
FAST = 1.0


def fresh_creds() -> FulcraCredentials:
    return FulcraCredentials(
        access_token="fake-token",
        access_token_expiration=datetime.now(UTC) + timedelta(hours=1),
        refresh_token="fake-refresh",
    )


class FakeOidc:
    def __init__(self, flow):
        self._flow = flow

    def authorize_via_device_flow(self, prompt_callback):
        return self._flow(prompt_callback)


@pytest.fixture
def login(monkeypatch):
    """Stdio mode with no saved credentials and a scripted device flow.

    Set ``login.flow`` to a function taking the prompt callback and returning
    credentials (or raising). ``login.started`` counts logins begun.
    """

    class Login:
        flow = None
        started = 0
        saved = []

    state = Login()

    class FakeAPI:
        def __init__(self, **kwargs):
            state.started += 1
            self.oidc = FakeOidc(lambda cb: state.flow(cb))
            self.fulcra_credentials = None

    monkeypatch.setattr(settings, "fulcra_environment", "stdio")
    monkeypatch.setattr(credentials, "stdio_fulcra", None)
    monkeypatch.setattr(credentials, "_login_thread", None)
    monkeypatch.setattr(credentials, "_login_prompt", None)
    monkeypatch.setattr(credentials, "_login_error", None)
    monkeypatch.setattr(credentials, "_load_stdio_credentials", lambda: None)
    monkeypatch.setattr(credentials, "_save_stdio_credentials", state.saved.append)
    monkeypatch.setattr(credentials, "SynchronizedFulcraAPI", FakeAPI)
    monkeypatch.setattr(credentials.webbrowser, "open_new_tab", lambda uri: True)
    return state


def call() -> str:
    """Call get_fulcra_object(), which must raise; return the message and
    check that it came back promptly."""
    began = time.monotonic()
    with pytest.raises(ToolError) as err:
        credentials.get_fulcra_object()
    assert time.monotonic() - began < FAST
    return str(err.value)


def wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out waiting for the login thread"
        time.sleep(0.005)


async def test_event_loop_stays_responsive_while_device_code_is_fetched(login):
    # The device-code request is stalled: no prompt has been produced yet.
    release = threading.Event()
    def flow(prompt):
        release.wait(10)

    login.flow = flow

    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    try:
        began = time.monotonic()
        with pytest.raises(ToolError, match="starting"):
            credentials.get_fulcra_object()
        assert time.monotonic() - began < FAST
        await asyncio.sleep(0.1)
        assert ticks > 0
    finally:
        task.cancel()
        release.set()


def test_pending_login_reports_url_and_code_and_is_reused(login):
    release = threading.Event()

    def flow(prompt):
        prompt("device-code", "https://auth.example/activate", "ABCD-EFGH")
        release.wait(10)
        return fresh_creds()

    login.flow = flow
    try:
        # The first call may land before the worker has the code.
        wait_for(lambda: "ABCD-EFGH" in _message_or_empty())
        message = call()
        assert "https://auth.example/activate" in message
        assert "ABCD-EFGH" in message
        assert login.started == 1
    finally:
        release.set()
        wait_for(lambda: credentials._login_thread is None)


def _message_or_empty() -> str:
    try:
        credentials.get_fulcra_object()
    except ToolError as exc:
        return str(exc)
    return ""


def test_completed_login_is_saved_and_used(login):
    creds = fresh_creds()
    login.flow = lambda prompt: creds

    _message_or_empty()
    wait_for(lambda: credentials.stdio_fulcra is not None)

    assert credentials.get_fulcra_object() is credentials.stdio_fulcra
    assert credentials.stdio_fulcra.fulcra_credentials is creds
    assert login.saved == [creds]


def test_failed_login_reports_the_failure_without_waiting(login):
    def flow(prompt):
        raise RuntimeError("auth server unreachable")

    login.flow = flow

    _message_or_empty()
    wait_for(lambda: credentials._login_thread is None)

    message = call()
    assert "auth server unreachable" in message
    assert "starting" not in message


def test_expired_login_reports_failure_then_starts_over(login):
    login.flow = lambda prompt: None  # device code expired or was denied

    _message_or_empty()
    wait_for(lambda: credentials._login_thread is None)

    assert "expired" in call()
    assert login.started == 1

    # The failure was reported once; the next call begins a new login.
    call()
    assert login.started == 2
    wait_for(lambda: credentials._login_thread is None)
