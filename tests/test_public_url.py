"""The server describes itself using the host each request came in on, so one
deployment works on its custom domain, run.app URL and tagged previews without
being told its own URL."""

import time
import urllib.parse
from unittest.mock import MagicMock

import httpx
import pytest
from mcp.server.auth.provider import AccessToken
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from fulcra_mcp import file_transfer, provider
from fulcra_mcp.main import app, oauth_provider
from fulcra_mcp.provider import OIDC_SCOPES
from fulcra_mcp.public_url import public_origin
from fulcra_mcp.settings import settings

PUBLIC = "https://public.example"


@pytest.fixture(autouse=True)
def no_override(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "oidc_server_url", None)
    monkeypatch.setattr(settings, "state_path", tmp_path)


def client_for(base_url: str, **kwargs) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=base_url, **kwargs
    )


@pytest.mark.parametrize("mount", ["", "/mcp", "/MCP", "/openai/mcp"])
async def test_authorization_server_metadata_uses_the_request_host(mount):
    async with client_for(PUBLIC) as client:
        response = await client.get(f"{mount}/.well-known/oauth-authorization-server")

    assert response.status_code == 200
    doc = response.json()  # Parsing also proves Content-Length matches the new body.
    assert doc["issuer"] == f"{PUBLIC}/"
    assert doc["authorization_endpoint"] == f"{PUBLIC}/authorize"
    assert doc["token_endpoint"] == f"{PUBLIC}/token"
    assert doc["registration_endpoint"] == f"{PUBLIC}/register"
    assert int(response.headers["content-length"]) == len(response.content)


@pytest.mark.parametrize(
    "path, resource",
    [
        ("/.well-known/oauth-protected-resource", f"{PUBLIC}/"),
        ("/.well-known/oauth-protected-resource/mcp", f"{PUBLIC}/mcp"),
        ("/.well-known/oauth-protected-resource/openai/mcp", f"{PUBLIC}/openai/mcp"),
    ],
)
async def test_protected_resource_metadata_uses_the_request_host(path, resource):
    async with client_for(PUBLIC) as client:
        doc = (await client.get(path)).json()

    assert doc["resource"] == resource
    assert doc["authorization_servers"] == [f"{PUBLIC}/"]


async def test_the_401_challenge_uses_the_request_host():
    async with client_for(PUBLIC) as client:
        response = await client.post("/mcp", json={})

    assert response.status_code == 401
    assert f'resource_metadata="{PUBLIC}/.well-known/' in response.headers["www-authenticate"]


@pytest.mark.parametrize(
    "base_url",
    [
        "https://public.example:8443",
        "https://pr-1---dev-mcp-abc-uw.a.run.app",
        "http://localhost:4499",
        "http://127.0.0.1:9000",
        "http://[::1]:9000",
    ],
)
async def test_the_issuer_matches_the_url_the_client_used(base_url):
    async with client_for(base_url) as client:
        doc = (await client.get("/.well-known/oauth-authorization-server")).json()

    assert doc["issuer"] == f"{base_url}/"


@pytest.mark.parametrize(
    "trusted_hosts, issuer",
    [
        ("*", f"{PUBLIC}/"),  # FORWARDED_ALLOW_IPS set: the proxy's scheme counts.
        ("127.0.0.2", "http://public.example/"),  # Unset: the proxy isn't trusted.
    ],
)
async def test_the_scheme_comes_from_a_trusted_proxy(trusted_hosts, issuer):
    # uvicorn wraps the app in this middleware when it serves it.
    proxied = ProxyHeadersMiddleware(app, trusted_hosts=trusted_hosts)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=proxied),
        base_url="http://public.example",
        headers={"X-Forwarded-Proto": "https"},
    ) as client:
        doc = (await client.get("/.well-known/oauth-authorization-server")).json()

    assert doc["issuer"] == issuer


@pytest.mark.parametrize("host", ['evil.example"><script>', "user@evil.example", "[::1", ""])
async def test_an_unusable_host_falls_back_to_the_server_address(host):
    async with client_for("https://server.example:8443", headers={"Host": host}) as client:
        response = await client.get("/.well-known/oauth-authorization-server")

    assert response.json()["issuer"] == "https://server.example:8443/"


async def test_oidc_server_url_overrides_the_request_host(monkeypatch):
    monkeypatch.setattr(settings, "oidc_server_url", "https://override.example/")
    async with client_for(PUBLIC) as client:
        doc = (await client.get("/.well-known/oauth-authorization-server")).json()

    assert doc["issuer"] == "https://override.example/"


async def test_login_redirects_to_and_exchanges_with_the_request_host(monkeypatch):
    fake = MagicMock()
    fake.get_authorization_code_url.return_value = "https://auth.example/authorize"
    monkeypatch.setattr(provider, "FulcraAPI", MagicMock(return_value=fake))
    client_redirect = "https://client.example/cb"

    async with client_for(PUBLIC) as client:
        registered = await client.post(
            "/register",
            json={"redirect_uris": [client_redirect], "token_endpoint_auth_method": "none"},
        )
        assert registered.status_code == 201, registered.text
        authorize = await client.get(
            "/authorize",
            params={
                "client_id": registered.json()["client_id"],
                "redirect_uri": client_redirect,
                "response_type": "code",
                "code_challenge": "x" * 43,
                "code_challenge_method": "S256",
                "state": "public-url-test",
            },
        )
    assert authorize.status_code == 302, authorize.text
    fake.get_authorization_code_url.assert_called_once()
    assert fake.get_authorization_code_url.call_args.kwargs["redirect_uri"] == f"{PUBLIC}/callback"

    # The exchange must repeat the URL sent at /authorize, whatever this request says.
    async with client_for("https://other.example") as client:
        callback = await client.get("/callback", params={"code": "c", "state": "public-url-test"})
    assert callback.status_code == 302, callback.text
    assert callback.headers["location"].startswith(f"{client_redirect}?")
    fake.authorize_with_authorization_code.assert_called_once_with(
        code="c", redirect_uri=f"{PUBLIC}/callback"
    )
    code = urllib.parse.parse_qs(urllib.parse.urlsplit(callback.headers["location"]).query)["code"][0]
    oauth_provider.auth_codes.pop(code)


@pytest.mark.parametrize(
    "tool, arguments, link",
    [
        ("write_file", {"path": "/reports/q3.xlsx", "encoding": "upload_link"}, "/files/upload/"),
        ("read_file", {"path": "/reports/q3.xlsx", "as_link": True}, "/files/download/"),
    ],
)
async def test_a_tool_call_makes_file_links_for_the_request_host(
    monkeypatch, fake_fulcra, tool, arguments, link
):
    """Tools run in the transport's own tasks, not the request's, so this goes
    through the real endpoint rather than calling the link helpers directly."""
    fake_fulcra.resolve_filepath.return_value = [
        {"id": "file-1", "name": "q3.xlsx", "path": "/reports/q3.xlsx", "size": 3}
    ]
    monkeypatch.setattr(settings, "fulcra_environment", "hosted")
    monkeypatch.setattr(file_transfer, "current_grant_id", lambda: "grant-1")
    monkeypatch.setitem(
        oauth_provider.tokens,
        "mcp_test",
        AccessToken(
            token="mcp_test",
            client_id="c",
            scopes=OIDC_SCOPES,
            expires_at=int(time.time()) + 3600,
        ),
    )
    headers = {
        "Authorization": "Bearer mcp_test",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    call = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    async with app.router.lifespan_context(app), client_for(PUBLIC, headers=headers) as client:
        response = await client.post("/mcp", json=call)

    assert response.status_code == 200
    assert f"{PUBLIC}{link}" in response.text


def test_without_a_request_the_origin_is_localhost():
    assert public_origin() == f"http://localhost:{settings.port}"
