import io
import os
import urllib.error
from unittest.mock import MagicMock

import pytest
from fastmcp import Client
from fulcra_api.core import FulcraAPI

# Settings are read at import time; force stdio mode so the suite behaves the
# same regardless of the developer's shell environment.
os.environ["FULCRA_ENVIRONMENT"] = "stdio"

import fulcra_mcp.tools as tools_module
from fulcra_mcp.tools import tools_mcp


@pytest.fixture
def fake_fulcra(monkeypatch):
    """Replace the FulcraAPI object with a mock so tools never hit the network.

    The mock is specced against the installed FulcraAPI so a call to a method
    the SDK does not have fails here instead of in users' hands. An unspecced
    MagicMock accepted `fulcra_v1_api_path` after fulcra-api 0.1.42 renamed it
    to `fulcra_v1alpha1_api_path`, so every test passed while get_records was
    broken for custom types in any install that resolved the new SDK.
    """
    fake = MagicMock(spec=FulcraAPI)
    monkeypatch.setattr(tools_module, "get_fulcra_object", lambda: fake)
    return fake


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
