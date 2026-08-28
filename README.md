## fulcra-context-mcp: An MCP server to access your Fulcra Context data


This is an MCP server that provides tools and resources to call the Fulcra API using [`fulcra-api`](https://github.com/fulcradynamics/fulcra-api-python).

There is a public instance of this server running at `https://mcp.fulcradynamics.com/mcp`.  See [https://docs.fulcradynamics.com/](https://docs.fulcradynamics.com/) to get started quickly.  This repo is primarily for users who need to run the server locally, want to see under the hood, or want to help contribute.

When run on its own (or when `FULCRA_ENVIRONMENT` is set to `stdio`), it acts as a local MCP server using the stdio transport.  Otherwise, it acts as a remote server using the Streamble HTTP transport.  It handles the OAuth2 callback, but doesn't leak the exchanged tokens to MCP clients.  Instead, it maintains a mapping table and runs its own OAuth2 service between MCP clients.

### Remote Connection using Proxy

There is a public instance of this server running at `https://mcp.fulcradynamics.com/`.  Point your OAuth2-capable MCP clients at that.

### Local Connection

Example Claude Desktop config using `uvx`:
```
{
    "mcpServers": {
        "fulcra_context": {
            "command": "uvx",
            "args": [
                "fulcra-context-mcp@latest"
            ]
        }
    }
}
```

### Debugging / Developer Tools

- Both the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) and [mcp-remote](https://github.com/geelen/mcp-remote) tools can be useful in debugging.

#### Viewing Tools

Every MCP client is different, but many abbreviate abbreviate tool and parameter descriptions for summaries. To avoid confusing client models, keep the initial descriptions short (full description in one line, around 80 characters).

While developing locally, the `scripts/simulate_tools.py` script simulates what this might look like to an MCP client:
```
FULCRA_ENVIRONMENT=stdio uv run python scripts/simulate_tools.py --command "uv run fulcra-context-mcp"
```

## Bugs / Feature Requests

Please feel free to reach out via [the GitHub repo for this project](https://github.com/fulcradynamics/fulcra-context-mcp) or [join our Discord](https://discord.com/invite/aunahVEnPU) to reach out directly.  Email also works (`support@fulcradynamics.com`).

<a href="https://glama.ai/mcp/servers/@fulcradynamics/fulcra-context-mcp">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@fulcradynamics/fulcra-context-mcp/badge" />
</a>
