"""PLAT-865: the server's Fulcra API requests name fulcra-context-mcp and how it runs."""

import io
import json
import urllib.request
from datetime import UTC, datetime, timedelta

import pytest
from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials

import fulcra_mcp.file_transfer as ft
import fulcra_mcp.user_agent as ua
from fulcra_mcp import credentials
from fulcra_mcp.server_info import version
from fulcra_mcp.settings import settings

# fulcra-api releases before PLAT-864 can't add our token; the request tests
# need one that can.
needs_user_agent_support = pytest.mark.skipif(
    not ua.fulcra_api_kwargs(),
    reason="installed fulcra-api has no user_agent_extra (PLAT-864)",
)


def fresh_creds() -> FulcraCredentials:
    return FulcraCredentials(
        access_token="fake-token",
        access_token_expiration=datetime.now(UTC) + timedelta(hours=1),
        refresh_token="fake-refresh",
    )


class FakeResponse(io.BytesIO):
    status = 200


@pytest.fixture
def sent_user_agents(monkeypatch) -> list[str | None]:
    seen: list[str | None] = []

    def fake_urlopen(req, *args, **kwargs):
        seen.append(req.get_header("User-agent"))
        return FakeResponse(json.dumps({}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen


@pytest.mark.parametrize(
    ("environment", "transport"), [("stdio", "stdio"), ("prod", "hosted")]
)
def test_token_names_server_version_and_transport(monkeypatch, environment, transport):
    monkeypatch.setattr(settings, "fulcra_environment", environment)
    assert ua.user_agent_extra() == f"fulcra-context-mcp/{version()} ({transport})"


def test_older_fulcra_api_gets_no_extra_arguments(monkeypatch):
    class OldFulcraAPI:
        def __init__(self, credentials=None):
            pass

    monkeypatch.setattr(ua, "FulcraAPI", OldFulcraAPI)
    assert ua.fulcra_api_kwargs() == {}


def test_newer_fulcra_api_gets_the_token(monkeypatch):
    class NewFulcraAPI:
        def __init__(self, credentials=None, user_agent_extra=None):
            pass

    monkeypatch.setattr(ua, "FulcraAPI", NewFulcraAPI)
    assert ua.fulcra_api_kwargs() == {"user_agent_extra": ua.user_agent_extra()}


@needs_user_agent_support
def test_hosted_requests_carry_the_token(monkeypatch, sent_user_agents):
    monkeypatch.setattr(settings, "fulcra_environment", "prod")

    fulcra = credentials.fulcra_for_grant("grant-1", fresh_creds())
    fulcra.fulcra_api("/user/v1alpha1/info")

    assert len(sent_user_agents) == 1
    assert sent_user_agents[0].startswith("fulcra-api/")
    assert sent_user_agents[0].endswith(f" fulcra-context-mcp/{version()} (hosted)")


@needs_user_agent_support
def test_stdio_requests_carry_the_token(monkeypatch, sent_user_agents):
    monkeypatch.setattr(settings, "fulcra_environment", "stdio")
    monkeypatch.setattr(credentials, "stdio_fulcra", None)
    monkeypatch.setattr(credentials, "_load_stdio_credentials", fresh_creds)

    fulcra = credentials.get_fulcra_object()
    fulcra.fulcra_api("/user/v1alpha1/info")

    assert len(sent_user_agents) == 1
    assert sent_user_agents[0].endswith(f" fulcra-context-mcp/{version()} (stdio)")


def test_upload_chunks_carry_the_token(monkeypatch, sent_user_agents):
    monkeypatch.setattr(settings, "fulcra_environment", "prod")

    ft._put_chunk("https://storage.example/upload", b"abcd", 0, 4)

    assert sent_user_agents == [ua.user_agent()]
    assert ua.user_agent().endswith(f"fulcra-context-mcp/{version()} (hosted)")


def test_token_is_valid_for_fulcra_api():
    # fulcra-api rejects tokens with characters outside printable ASCII.
    if not ua.fulcra_api_kwargs():
        pytest.skip("installed fulcra-api has no user_agent_extra (PLAT-864)")
    FulcraAPI(**ua.fulcra_api_kwargs())
