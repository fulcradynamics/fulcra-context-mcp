"""The Hermes plugin's endpoint.

The same server as /mcp for now. The plugin connects here so its behavior can be kept (frozen) or changed
for the plugin without touching /mcp.
"""
from .endpoint import create_server

HERMES_MCP_PATH = "/hermes/mcp"


def create_hermes_server():
    return create_server()
