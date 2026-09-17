"""Fulcra credentials must survive a server restart intact.

Regression tests for the prod "needs re-auth" disconnects (docs/disconnect-
diagnosis.md): token records used to embed their own copy of the Fulcra
credentials, so a Fulcra token refresh made through the access-token path was
lost as soon as a restart rehydrated the refresh-token path's stale copy.
"""

import json
import time
from datetime import datetime, timedelta
from unittest.mock import create_autospec

import pytest
from fastmcp.exceptions import ToolError
from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    RefreshToken,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyHttpUrl

import fulcra_mcp.credentials as credentials_module
from fulcra_mcp.provider import OIDC_SCOPES, FulcraOAuthProvider
from fulcra_mcp.settings import settings

CLIENT = OAuthClientInformationFull(
    client_id="client-1",
    client_secret="secret",
    redirect_uris=[AnyHttpUrl("https://claude.ai/api/mcp/auth_callback")],
    grant_types=["authorization_code", "refresh_token"],
)


def fresh_creds(tag: str, expired: bool = False) -> FulcraCredentials:
    delta = timedelta(hours=-1) if expired else timedelta(hours=24)
    return FulcraCredentials(
        access_token=f"auth0-access-{tag}",
        access_token_expiration=datetime.now() + delta,  # noqa: DTZ005 fulcra-api compares naive
        refresh_token=f"auth0-refresh-{tag}",
    )


def make_provider() -> FulcraOAuthProvider:
    return FulcraOAuthProvider(issuer_url=AnyHttpUrl("http://localhost:4499"))


@pytest.fixture
def state_path(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "state_path", tmp_path)
    return tmp_path


async def login(provider: FulcraOAuthProvider, creds: FulcraCredentials):
    """Drive the tail of the login flow: /callback stored creds, /token exchanges."""
    code = AuthorizationCode(
        code="mcp_code",
        client_id=CLIENT.client_id,
        redirect_uri=CLIENT.redirect_uris[0],
        redirect_uri_provided_explicitly=True,
        expires_at=time.time() + 300,
        scopes=OIDC_SCOPES,
        code_challenge="challenge",
    )
    provider.auth_codes[code.code] = code
    provider.client_credentials[CLIENT.client_id] = creds
    return await provider.exchange_authorization_code(CLIENT, code)


async def refresh(provider: FulcraOAuthProvider, refresh_token: str):
    token_obj = await provider.load_refresh_token(CLIENT, refresh_token)
    assert token_obj is not None
    return await provider.exchange_refresh_token(CLIENT, token_obj, [])


async def test_fulcra_refresh_survives_restart_and_mcp_refresh(state_path):
    p1 = make_provider()
    tokens = await login(p1, fresh_creds("v1"))

    # A tool call refreshes the Fulcra token through the access-token path.
    grant_id, creds = p1.credentials_for_token(tokens.access_token)
    creds.access_token = "auth0-access-v2"
    creds.refresh_token = "auth0-refresh-v2"
    p1.save_grant(grant_id)

    # Restart: a new process rehydrates everything from disk, and the client's
    # next action is an MCP token refresh.
    p2 = make_provider()
    tokens2 = await refresh(p2, tokens.refresh_token)

    grant_id2, creds2 = p2.credentials_for_token(tokens2.access_token)
    assert grant_id2 == grant_id
    assert creds2.access_token == "auth0-access-v2"
    assert creds2.refresh_token == "auth0-refresh-v2"

    # Both paths resolve to one object, so in-memory updates cannot diverge.
    assert (await p2.load_access_token(tokens2.access_token)) is not None
    assert p2.credentials_for_token(tokens2.access_token)[1] is creds2
    p2.refresh_tokens.clear()  # force the disk path for the refresh token too
    await p2.load_refresh_token(CLIENT, tokens2.refresh_token)
    assert p2.grant_credentials[p2.refresh_grant[tokens2.refresh_token]] is creds2


async def test_token_records_reference_grant_not_credentials(state_path):
    p = make_provider()
    tokens = await login(p, fresh_creds("v1"))
    record = json.loads(next((state_path / "access_tokens").iterdir()).read_text())
    assert set(record) == {"token", "grant_id"}
    assert (state_path / "grants" / f"{record['grant_id']}.json").exists()
    assert "auth0-access-v1" not in json.dumps(record)
    assert p.token_grant[tokens.access_token] == record["grant_id"]


def write_legacy_records(
    state_path, provider, creds_json: str, access: str, refresh: str
):
    access_obj = AccessToken(
        token=access,
        client_id=CLIENT.client_id,
        scopes=OIDC_SCOPES,
        expires_at=int(time.time()) + 3600,
    )
    refresh_obj = RefreshToken(
        token=refresh, client_id=CLIENT.client_id, scopes=OIDC_SCOPES
    )
    for kind, tok, obj in (
        ("access_tokens", access, access_obj),
        ("refresh_tokens", refresh, refresh_obj),
    ):
        path = provider._token_record_path(kind, tok)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"token": obj.model_dump_json(), "credentials": creds_json})
        )


async def test_legacy_records_are_adopted_into_one_grant(state_path):
    seed = make_provider()
    write_legacy_records(
        seed, seed, fresh_creds("old").to_json(), "mcp_a1", "mcp_refresh_r1"
    )

    p1 = make_provider()
    assert (await p1.load_access_token("mcp_a1")) is not None
    grant_id, creds = p1.credentials_for_token("mcp_a1")
    assert grant_id.startswith("legacy-")
    assert creds.access_token == "auth0-access-old"
    # The record was rewritten in the new form.
    rewritten = json.loads(p1._token_record_path("access_tokens", "mcp_a1").read_text())
    assert rewritten["grant_id"] == grant_id and "credentials" not in rewritten

    # Fulcra refresh, then restart, then MCP refresh via the legacy refresh
    # record: the refreshed values must win over the record's embedded copy.
    creds.access_token = "auth0-access-new"
    creds.refresh_token = "auth0-refresh-new"
    p1.save_grant(grant_id)

    p2 = make_provider()
    tokens = await refresh(p2, "mcp_refresh_r1")
    _, creds2 = p2.credentials_for_token(tokens.access_token)
    assert creds2.access_token == "auth0-access-new"
    assert creds2.refresh_token == "auth0-refresh-new"


async def test_exchange_without_login_state_fails_loudly(state_path):
    p = make_provider()
    code = AuthorizationCode(
        code="mcp_orphan",
        client_id=CLIENT.client_id,
        redirect_uri=CLIENT.redirect_uris[0],
        redirect_uri_provided_explicitly=True,
        expires_at=time.time() + 300,
        scopes=OIDC_SCOPES,
        code_challenge="c",
    )
    p.auth_codes[code.code] = code  # /callback ran elsewhere: no client_credentials
    with pytest.raises(TokenError) as excinfo:
        await p.exchange_authorization_code(CLIENT, code)
    assert excinfo.value.error == "invalid_grant"
    assert not list((state_path).glob("access_tokens/*"))


# --- get_fulcra_object (hosted branch) ---------------------------------------


@pytest.fixture
def hosted(state_path, monkeypatch):
    monkeypatch.setattr(settings, "fulcra_environment", "prod")
    provider = make_provider()
    monkeypatch.setattr(credentials_module, "oauth_provider", provider)
    return provider


def use_token(monkeypatch, token: str):
    monkeypatch.setattr(
        credentials_module,
        "get_access_token",
        lambda: AccessToken(
            token=token, client_id=CLIENT.client_id, scopes=OIDC_SCOPES
        ),
    )


async def test_expired_fulcra_token_is_refreshed_before_use(hosted, monkeypatch):
    tokens = await login(hosted, fresh_creds("v1", expired=True))
    use_token(monkeypatch, tokens.access_token)
    grant_id, creds = hosted.credentials_for_token(tokens.access_token)

    fake_api = create_autospec(FulcraAPI, instance=True)

    def refresh_ok():
        fake_api.refresh_callback(fresh_creds("v2"))
        return True

    fake_api.refresh_access_token.side_effect = refresh_ok

    def fake_ctor(**kwargs):
        fake_api.refresh_callback = kwargs["refresh_callback"]
        assert kwargs["credentials"] is creds
        return fake_api

    monkeypatch.setattr(credentials_module, "FulcraAPI", fake_ctor)

    assert credentials_module.get_fulcra_object() is fake_api
    assert creds.access_token == "auth0-access-v2"
    persisted = FulcraCredentials.from_json((hosted._grant_path(grant_id)).read_text())
    assert persisted.access_token == "auth0-access-v2"


async def test_failed_fulcra_refresh_raises_actionable_error(hosted, monkeypatch):
    tokens = await login(hosted, fresh_creds("v1", expired=True))
    use_token(monkeypatch, tokens.access_token)
    fake_api = create_autospec(FulcraAPI, instance=True)
    fake_api.refresh_access_token.return_value = False
    monkeypatch.setattr(credentials_module, "FulcraAPI", lambda **kw: fake_api)

    with pytest.raises(ToolError, match="Reconnect the Fulcra connector"):
        credentials_module.get_fulcra_object()
    fake_api.fulcra_api.assert_not_called()


async def test_token_without_grant_raises_actionable_error(hosted, monkeypatch):
    hosted.tokens["mcp_phantom"] = AccessToken(
        token="mcp_phantom",
        client_id=CLIENT.client_id,
        scopes=OIDC_SCOPES,
        expires_at=int(time.time()) + 3600,
    )
    use_token(monkeypatch, "mcp_phantom")
    with pytest.raises(ToolError, match="not connected to a Fulcra account"):
        credentials_module.get_fulcra_object()


# --- multi-instance and legacy-divergence hardening ---------------------------


def creds_expiring_in(tag: str, delta: timedelta) -> FulcraCredentials:
    return FulcraCredentials(
        access_token=f"auth0-access-{tag}",
        access_token_expiration=datetime.now() + delta,  # noqa: DTZ005 fulcra-api compares naive
        refresh_token=f"auth0-refresh-{tag}",
    )


def write_legacy_record(provider, kind: str, token: str, creds: FulcraCredentials):
    if kind == "access_tokens":
        obj = AccessToken(
            token=token,
            client_id=CLIENT.client_id,
            scopes=OIDC_SCOPES,
            expires_at=int(time.time()) + 3600,
        )
    else:
        obj = RefreshToken(token=token, client_id=CLIENT.client_id, scopes=OIDC_SCOPES)
    path = provider._token_record_path(kind, token)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"token": obj.model_dump_json(), "credentials": creds.to_json()})
    )


@pytest.mark.parametrize("order", ["access_first", "refresh_first"])
async def test_legacy_diverged_records_resolve_to_newest(state_path, order):
    """A Fulcra refresh shortly before the fix deploys leaves the access record
    newer than the refresh record. Whichever is loaded first, the client must
    end up on the fresh credentials, not the rotated-out ones."""
    seed = make_provider()
    write_legacy_record(
        seed,
        "refresh_tokens",
        "mcp_refresh_r1",
        creds_expiring_in("v1", timedelta(hours=1)),
    )
    write_legacy_record(
        seed, "access_tokens", "mcp_a1", creds_expiring_in("v2", timedelta(hours=24))
    )

    p1 = make_provider()
    if order == "access_first":
        assert (await p1.load_access_token("mcp_a1")) is not None
        assert (await p1.load_refresh_token(CLIENT, "mcp_refresh_r1")) is not None
    else:
        assert (await p1.load_refresh_token(CLIENT, "mcp_refresh_r1")) is not None
        assert (await p1.load_access_token("mcp_a1")) is not None

    grant_id, creds = p1.credentials_for_token("mcp_a1")
    assert grant_id == f"legacy-{CLIENT.client_id}"
    assert p1.refresh_grant["mcp_refresh_r1"] == grant_id
    assert creds.access_token == "auth0-access-v2"
    assert creds.refresh_token == "auth0-refresh-v2"
    persisted = FulcraCredentials.from_json(p1._grant_path(grant_id).read_text())
    assert persisted.access_token == "auth0-access-v2"

    # Restart, then the MCP refresh that used to promote the stale copy.
    p2 = make_provider()
    tokens = await refresh(p2, "mcp_refresh_r1")
    _, creds2 = p2.credentials_for_token(tokens.access_token)
    assert creds2.access_token == "auth0-access-v2"


async def test_expired_cache_picks_up_grant_refreshed_elsewhere(hosted, monkeypatch):
    """Another Cloud Run instance refreshed the grant on disk; this process
    must adopt it instead of spending its rotated-out refresh token."""
    tokens = await login(hosted, fresh_creds("v1", expired=True))
    use_token(monkeypatch, tokens.access_token)
    grant_id, creds = hosted.credentials_for_token(tokens.access_token)
    hosted._grant_path(grant_id).write_text(fresh_creds("v2").to_json())

    fake_api = create_autospec(FulcraAPI, instance=True)
    fake_api.refresh_access_token.return_value = False
    monkeypatch.setattr(credentials_module, "FulcraAPI", lambda **kw: fake_api)

    assert credentials_module.get_fulcra_object() is fake_api
    fake_api.refresh_access_token.assert_not_called()
    assert creds.access_token == "auth0-access-v2"
    assert creds.refresh_token == "auth0-refresh-v2"
    assert hosted.credentials_for_token(tokens.access_token)[1] is creds


async def test_near_expiry_refreshes_up_front(hosted, monkeypatch):
    """A token that would expire mid-request is refreshed before the request,
    under the grant lock, rather than lazily inside fulcra-api."""
    tokens = await login(hosted, creds_expiring_in("v1", timedelta(seconds=30)))
    use_token(monkeypatch, tokens.access_token)
    _, creds = hosted.credentials_for_token(tokens.access_token)
    assert not creds.is_expired()

    fake_api = create_autospec(FulcraAPI, instance=True)

    def refresh_ok():
        fake_api.refresh_callback(fresh_creds("v2"))
        return True

    fake_api.refresh_access_token.side_effect = refresh_ok

    def fake_ctor(**kwargs):
        fake_api.refresh_callback = kwargs["refresh_callback"]
        return fake_api

    monkeypatch.setattr(credentials_module, "FulcraAPI", fake_ctor)

    credentials_module.get_fulcra_object()
    fake_api.refresh_access_token.assert_called_once()
    assert creds.access_token == "auth0-access-v2"
