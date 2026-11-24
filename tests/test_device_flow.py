"""Device sign-in (RFC 8628): what Hermes's `mcp login --flow device` does, against the real routes, with
Auth0 faked."""

import json
import urllib.error
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fulcra_api.credentials import FulcraCredentials
from pydantic import AnyHttpUrl
from starlette.applications import Starlette

from fulcra_mcp import device_flow
from fulcra_mcp.device_flow import DEVICE_GRANT
from fulcra_mcp.provider import OIDC_SCOPES, FulcraOAuthProvider
from fulcra_mcp.settings import settings
from mcp.server.auth.settings import ClientRegistrationOptions

ORIGIN = "http://localhost:4499"
# What Hermes's device login registers (tools/mcp_oauth_device.py).
HERMES_CLIENT = {"redirect_uris": ["http://127.0.0.1:27890/callback"], "grant_types": [DEVICE_GRANT, "refresh_token"],
                 "response_types": [], "token_endpoint_auth_method": "client_secret_post", "client_name": "Hermes",
                 "scope": "openid"}


def auth0_error(error: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://auth0", 403, "x", {}, BytesIO(json.dumps({"error": error}).encode()))


@pytest.fixture
def auth0(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "state_path", tmp_path)
    monkeypatch.setattr(settings, "device_oidc_client_id", "device-client")
    fake = MagicMock()
    fake.oidc.get_device_code.return_value = (
        "auth0-device-code", "https://tenant.auth0.com/activate?user_code=ABCD-EFGH", "ABCD-EFGH", 900, 5)
    monkeypatch.setattr(device_flow, "_auth0", lambda: fake)
    return fake


def app_for(provider):
    return Starlette(routes=provider.get_routes("/mcp"))


def make_provider():
    return FulcraOAuthProvider(
        issuer_url=AnyHttpUrl(ORIGIN),
        client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=OIDC_SCOPES,
                                                              default_scopes=OIDC_SCOPES),
        required_scopes=["openid"],
    )


async def register(client):
    response = await client.post("/register", json=HERMES_CLIENT)
    assert response.status_code == 201, response.text
    return response.json()


def creds_from_auth0():
    return FulcraCredentials(access_token="auth0-access", refresh_token="auth0-refresh",
                             access_token_expiration=datetime.now(timezone.utc) + timedelta(hours=1))


async def test_the_whole_flow_as_hermes_runs_it(auth0):
    provider = make_provider()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_for(provider)), base_url=ORIGIN) as client:
        meta = (await client.get("/.well-known/oauth-authorization-server")).json()
        assert meta["device_authorization_endpoint"] == f"{ORIGIN}/device_authorization"
        assert DEVICE_GRANT in meta["grant_types_supported"]

        registered = await register(client)
        assert DEVICE_GRANT in registered["grant_types"]
        secret = {"client_id": registered["client_id"], "client_secret": registered["client_secret"]}

        started = await client.post("/device_authorization", data={**secret, "resource": f"{ORIGIN}/mcp"})
        assert started.status_code == 200, started.text
        flow = started.json()
        assert flow["user_code"] == "ABCD-EFGH"
        assert flow["verification_uri"] == "https://tenant.auth0.com/activate"
        assert flow["device_code"] != "auth0-device-code"  # Auth0's code stays on the server.

        poll = {**secret, "grant_type": DEVICE_GRANT, "device_code": flow["device_code"]}
        auth0.oidc.get_token.side_effect = auth0_error("authorization_pending")
        pending = await client.post("/token", data=poll)
        assert (pending.status_code, pending.json()["error"]) == (400, "authorization_pending")
        auth0.oidc.get_token.side_effect = auth0_error("slow_down")
        assert (await client.post("/token", data=poll)).json()["error"] == "slow_down"

        auth0.oidc.get_token.side_effect = None
        auth0.oidc.get_token.return_value = creds_from_auth0()
        approved = await client.post("/token", data=poll)
        assert approved.status_code == 200, approved.text
        tokens = approved.json()
        auth0.oidc.get_token.assert_called_with(DEVICE_GRANT, {"device_code": "auth0-device-code"})
        assert (await client.post("/token", data=poll)).json()["error"] == "invalid_grant"  # used once

        # The issued tokens are ordinary ones: they resolve to the grant, and the SDK refreshes them.
        grant_id, creds = provider.credentials_for_token(tokens["access_token"])
        assert grant_id.startswith("device-") and creds.access_token == "auth0-access"
        assert device_flow.oidc_client_id(grant_id) == "device-client"
        refreshed = await client.post("/token", data={**secret, "grant_type": "refresh_token",
                                                       "refresh_token": tokens["refresh_token"]})
        assert refreshed.status_code == 200, refreshed.text


async def test_clients_are_authenticated_and_codes_are_bound_to_them(auth0):
    provider = make_provider()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_for(provider)), base_url=ORIGIN) as client:
        a, b = await register(client), await register(client)
        assert (await client.post("/device_authorization", data={"client_id": a["client_id"],
                                                                 "client_secret": "wrong"})).status_code == 401
        basic = httpx.BasicAuth(a["client_id"], a["client_secret"])
        flow = (await client.post("/device_authorization", auth=basic)).json()
        stolen = await client.post("/token", data={"client_id": b["client_id"], "client_secret": b["client_secret"],
                                                   "grant_type": DEVICE_GRANT, "device_code": flow["device_code"]})
        assert stolen.json()["error"] == "invalid_grant"
        auth0.oidc.get_token.side_effect = auth0_error("access_denied")
        poll = {"grant_type": DEVICE_GRANT, "device_code": flow["device_code"]}
        assert (await client.post("/token", data=poll, auth=basic)).json()["error"] == "access_denied"
        assert (await client.post("/token", data=poll, auth=basic)).json()["error"] == "invalid_grant"


async def test_browser_clients_keep_working_and_cannot_use_the_device_grant(auth0):
    provider = make_provider()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_for(provider)), base_url=ORIGIN) as client:
        browser = await client.post("/register", json={"redirect_uris": ["https://claude.ai/cb"],
                                                       "token_endpoint_auth_method": "client_secret_post"})
        assert browser.status_code == 201
        info = browser.json()
        denied = await client.post("/device_authorization", data={"client_id": info["client_id"],
                                                                  "client_secret": info["client_secret"]})
        assert denied.json()["error"] == "unauthorized_client"
        bad = await client.post("/token", data={"client_id": info["client_id"], "client_secret": info["client_secret"],
                                                "grant_type": "authorization_code", "code": "nope",
                                                "redirect_uri": "https://claude.ai/cb", "code_verifier": "x" * 43})
        assert bad.json()["error"] == "invalid_grant"  # answered by the SDK, as before


async def test_expired_codes(auth0):
    provider = make_provider()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_for(provider)), base_url=ORIGIN) as client:
        info = await register(client)
        secret = {"client_id": info["client_id"], "client_secret": info["client_secret"]}
        flow = (await client.post("/device_authorization", data=secret)).json()
        with patch.object(device_flow.time, "time", return_value=10**12):
            expired = await client.post("/token", data={**secret, "grant_type": DEVICE_GRANT,
                                                        "device_code": flow["device_code"]})
        assert expired.json()["error"] == "expired_token"
        auth0.oidc.get_token.assert_not_called()


async def test_off_without_a_device_client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "state_path", tmp_path)
    monkeypatch.setattr(settings, "device_oidc_client_id", None)
    provider = make_provider()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_for(provider)), base_url=ORIGIN) as client:
        meta = (await client.get("/.well-known/oauth-authorization-server")).json()
        assert "device_authorization_endpoint" not in meta
        assert (await client.post("/device_authorization", data={})).status_code in (404, 405)
        assert (await client.post("/register", json=HERMES_CLIENT)).status_code == 400
    assert device_flow.oidc_client_id("device-x") is None
    assert device_flow.oidc_client_id("abc") == settings.oidc_client_id
