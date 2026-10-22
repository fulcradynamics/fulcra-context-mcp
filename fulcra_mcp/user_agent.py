"""The MCP server's version info in the User-Agent of its Fulcra API requests.
"""

import inspect

from fulcra_api.core import FulcraAPI

from .server_info import version
from .settings import settings


def user_agent_extra() -> str:
    """E.g. `fulcra-context-mcp/1.2.5 (hosted)` or `... (stdio)`."""
    transport = "stdio" if settings.fulcra_environment == "stdio" else "hosted"
    return f"fulcra-context-mcp/{version()} ({transport})"


def fulcra_api_kwargs() -> dict[str, str]:
    if "user_agent_extra" not in inspect.signature(FulcraAPI.__init__).parameters:
        return {}
    return {"user_agent_extra": user_agent_extra()}


def user_agent() -> str:
    """The full User-Agent, for requests the server makes without fulcra-api."""
    try:
        from fulcra_api.user_agent import build_user_agent
    except ImportError:  # older fulcra-api backwards compat for whatever reason
        return user_agent_extra()
    return build_user_agent(user_agent_extra())
