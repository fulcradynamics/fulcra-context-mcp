"""Token refresh must be serialized across threads: tool calls may run in
worker threads concurrently while sharing one credentials object, and refresh
tokens rotate, so two simultaneous refreshes would race."""

import threading
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials

from fulcra_mcp.credentials import SynchronizedFulcraAPI


def _expired() -> FulcraCredentials:
    return FulcraCredentials(
        access_token="old",
        # Naive on purpose: fulcra-api compares expirations with datetime.now().
        access_token_expiration=datetime.now() - timedelta(minutes=1),  # noqa: DTZ005
        refresh_token="r1",
    )


def _slow_oidc() -> MagicMock:
    oidc = MagicMock()

    def refresh(creds):
        time.sleep(0.05)  # long enough for both threads to be inside
        return FulcraCredentials(
            access_token="new",
            access_token_expiration=datetime.now() + timedelta(hours=1),  # noqa: DTZ005
            refresh_token="r2",
        )

    oidc.refresh_credentials.side_effect = refresh
    return oidc


def _race(*apis: FulcraAPI) -> list[bool]:
    results: list[bool] = []
    threads = [threading.Thread(target=lambda a=a: results.append(a.refresh_access_token())) for a in apis]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_plain_client_refreshes_twice_under_contention():
    """The reviewer's reproduction: the upstream client has no lock."""
    api = FulcraAPI(credentials=_expired())
    api.oidc = _slow_oidc()
    _race(api, api)
    assert api.oidc.refresh_credentials.call_count == 2


def test_single_instance_refreshes_once():
    api = SynchronizedFulcraAPI(credentials=_expired())
    api.oidc = _slow_oidc()
    assert _race(api, api) == [True, True]
    assert api.oidc.refresh_credentials.call_count == 1
    assert api.fulcra_credentials.refresh_token == "r2"


def test_http_mode_instances_sharing_credentials_refresh_once():
    """HTTP mode builds a client per request around one shared credentials
    object, updated in place by the refresh callback (see get_fulcra_object)."""
    shared = _expired()

    def on_refresh(new):
        shared.access_token = new.access_token
        shared.access_token_expiration = new.access_token_expiration
        if new.refresh_token:
            shared.refresh_token = new.refresh_token

    oidc = _slow_oidc()
    a1 = SynchronizedFulcraAPI(credentials=shared, refresh_callback=on_refresh)
    a2 = SynchronizedFulcraAPI(credentials=shared, refresh_callback=on_refresh)
    a1.oidc = a2.oidc = oidc
    assert _race(a1, a2) == [True, True]
    assert oidc.refresh_credentials.call_count == 1
    assert shared.refresh_token == "r2"


def test_refresh_still_happens_when_actually_expired():
    api = SynchronizedFulcraAPI(credentials=_expired())
    api.oidc = _slow_oidc()
    assert api.refresh_access_token() is True
    assert api.oidc.refresh_credentials.call_count == 1
    # Fresh now: a further call is a no-op rather than another rotation.
    assert api.refresh_access_token() is True
    assert api.oidc.refresh_credentials.call_count == 1


needs_refresh_credentials = pytest.mark.skipif(
    not hasattr(FulcraAPI, "refresh_credentials"),
    reason="fulcra-api before PLAT-829 has no refresh_credentials",
)


@needs_refresh_credentials
def test_refresh_credentials_is_serialized_too():
    """Newer fulcra-api refreshes through refresh_credentials (an expiring
    token, or a 401), bypassing refresh_access_token."""
    api = SynchronizedFulcraAPI(credentials=_expired())
    api.oidc = _slow_oidc()
    threads = [threading.Thread(target=api.refresh_credentials) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert api.oidc.refresh_credentials.call_count == 1
    assert api.fulcra_credentials.refresh_token == "r2"


@needs_refresh_credentials
def test_refresh_credentials_refreshes_a_valid_token_when_asked():
    # A 401 means the server rejected a token that looks valid.
    creds = _expired()
    creds.access_token_expiration = datetime.now() + timedelta(hours=1)
    api = SynchronizedFulcraAPI(credentials=creds)
    api.oidc = _slow_oidc()
    api.refresh_credentials()
    assert api.oidc.refresh_credentials.call_count == 1
    assert api.fulcra_credentials.access_token == "new"
