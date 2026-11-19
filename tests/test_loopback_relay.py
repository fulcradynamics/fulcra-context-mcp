"""The /hermes relay lets loopback-redirect apps sign in with Auth0, which
matches callback ports exactly, and hands them Auth0's own tokens."""

import base64
import json
import urllib.parse

import httpx
import pytest

from fulcra_mcp.main import app
from fulcra_mcp.settings import settings

PUBLIC = "https://mcp.example"
AUTH0 = "tenant.example.auth0.com"
APP = "http://127.0.0.1:53123/callback"


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setattr(settings, "oidc_server_url", None)
    monkeypatch.setattr(settings, "fulcra_oidc_domain", AUTH0)
    monkeypatch.setattr(settings, "fulcra_api", "https://api.example/")


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=PUBLIC) as c:
        yield c


def query(url: str) -> dict:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))


async def authorize(client, **overrides):
    params = {"client_id": "app", "response_type": "code", "redirect_uri": APP,
              "state": "app-state", "code_challenge": "challenge",
              "code_challenge_method": "S256", "scope": "openid offline_access"} | overrides
    return await client.get("/hermes/authorize", params=params)


async def test_sign_in_round_trip_returns_the_code_to_the_apps_port(client):
    response = await authorize(client)
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith(f"https://{AUTH0}/authorize?")
    sent = query(location)
    assert sent["redirect_uri"] == f"{PUBLIC}/hermes/callback"
    assert sent["audience"] == "https://api.example/"
    assert {k: sent[k] for k in ("client_id", "code_challenge", "code_challenge_method", "scope")} == {
        "client_id": "app", "code_challenge": "challenge", "code_challenge_method": "S256",
        "scope": "openid offline_access"}

    page = await client.get("/hermes/callback", params={"code": "auth0-code", "state": sent["state"]})
    assert page.status_code == 200
    target = "http://127.0.0.1:53123/callback?code=auth0-code&amp;state=app-state"
    assert f'href="{target}"' in page.text


async def test_auth0_errors_go_straight_back_to_the_app(client):
    sent = query((await authorize(client)).headers["location"])
    response = await client.get("/hermes/callback", params={
        "error": "access_denied", "error_description": "no", "state": sent["state"]})
    assert response.status_code == 302
    assert query(response.headers["location"]) == {
        "error": "access_denied", "error_description": "no", "state": "app-state"}
    assert response.headers["location"].startswith(APP + "?")


@pytest.mark.parametrize("redirect_uri", [
    "https://evil.example/callback",
    "http://evil.example:53123/callback",
    "http://localhost:53123/callback",
    "http://127.0.0.1/callback",
    "http://user@127.0.0.1:53123/callback",
])
async def test_only_loopback_ports_are_accepted(client, redirect_uri):
    assert (await authorize(client, redirect_uri=redirect_uri)).status_code == 400


async def test_pkce_is_required(client):
    assert (await authorize(client, code_challenge="")).status_code == 400


async def test_a_forged_state_cannot_redirect_off_the_machine(client):
    forged = base64.urlsafe_b64encode(json.dumps({"r": "https://evil.example/cb", "s": "x"}).encode()).decode()
    response = await client.get("/hermes/callback", params={"code": "c", "state": forged})
    assert response.status_code == 400


@pytest.fixture
def auth0(monkeypatch):
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append((str(request.url), dict(urllib.parse.parse_qsl(request.content.decode()))))
        return httpx.Response(200, json={"access_token": "at", "refresh_token": "rt", "expires_in": 86400})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return sent


async def test_code_exchange_uses_the_relay_callback(client, auth0):
    response = await client.post("/hermes/token", data={
        "grant_type": "authorization_code", "code": "auth0-code", "redirect_uri": APP,
        "code_verifier": "verifier", "client_id": "app"})
    assert response.status_code == 200
    assert response.json()["access_token"] == "at"
    assert response.headers["cache-control"] == "no-store"
    assert auth0 == [(f"https://{AUTH0}/oauth/token", {
        "grant_type": "authorization_code", "code": "auth0-code", "code_verifier": "verifier",
        "client_id": "app", "redirect_uri": f"{PUBLIC}/hermes/callback"})]


async def test_refresh_is_forwarded_unchanged(client, auth0):
    form = {"grant_type": "refresh_token", "refresh_token": "rt", "client_id": "app"}
    assert (await client.post("/hermes/token", data=form)).status_code == 200
    assert auth0 == [(f"https://{AUTH0}/oauth/token", form)]


async def test_code_exchange_requires_a_loopback_redirect(client, auth0):
    response = await client.post("/hermes/token", data={
        "grant_type": "authorization_code", "code": "c", "redirect_uri": "https://evil.example/cb"})
    assert response.status_code == 400
    assert auth0 == []
