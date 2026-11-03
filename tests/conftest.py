import io
import os
import urllib.error
from unittest.mock import create_autospec

import pytest
from fastmcp import Client
from fulcra_api.core import FulcraAPI

# Settings are read at import time; force stdio mode so the suite behaves the
# same regardless of the developer's shell environment.
os.environ["FULCRA_ENVIRONMENT"] = "stdio"

import fulcra_mcp.tools as tools_module
from fulcra_mcp.tools import tools_mcp

FAKE_USER_ID = "00000000-0000-0000-0000-00000000f00d"


@pytest.fixture
def fake_fulcra(monkeypatch):
    """Replace the FulcraAPI object with a mock so tools never hit the network.

    The mock is autospec'd against the real client class so a tool that calls a
    method the SDK no longer has (or with the wrong signature) fails here rather
    than in a user's session.
    """
    fake = create_autospec(FulcraAPI, instance=True)
    fake.get_fulcra_userid.return_value = FAKE_USER_ID
    monkeypatch.setattr(tools_module, "get_fulcra_object", lambda: fake)
    return fake


@pytest.fixture
def app_capabilities(monkeypatch):
    """Advertise MCP Apps on the actual initialize request (not a server mock)."""
    from mcp import ClientSession
    from mcp.types import InitializeRequest
    original = ClientSession.send_request

    async def send_request(self, request, *args, **kwargs):
        if isinstance(request.root, InitializeRequest):
            request.root.params.capabilities.__pydantic_extra__['extensions'] = {
                'io.modelcontextprotocol/ui': {'mimeTypes': ['text/html;profile=mcp-app']}}
        return await original(self, request, *args, **kwargs)

    monkeypatch.setattr(ClientSession, 'send_request', send_request)


@pytest.fixture
async def client():
    async with Client(tools_mcp) as c:
        yield c


@pytest.fixture
def call(client):
    """Call a tool and return its text response."""

    async def _call(name: str, args: dict | None = None) -> str:
        result = await client.call_tool(name, args or {})
        return result.content[0].text

    return _call


def http_error(code: int, body: bytes = b"", reason: str = "error") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.fulcradynamics.com/data", code, reason, None, io.BytesIO(body)
    )
