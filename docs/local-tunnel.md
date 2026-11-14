# Local MCP variants through a secure tunnel

Stdio uses the local operator's Fulcra credentials. `FULCRA_MCP_VARIANT` selects
`standard` (default), `openai`, or `claude`; other values fail settings validation.
The selected server uses the same composition as `/mcp`, `/openai/mcp`, or
`/claude/mcp`, respectively, without an HTTP listener or MCP OAuth flow.
Hosted HTTP still serves all three routes with OAuth; the variant setting does
not change its routing. Stdio does not test HTTP authentication or browser file
transfer URLs.

## Prepare the account and checkout

Use a dedicated test OS account and synthetic Fulcra account. Authenticate with
`fulcra auth login` in that account before starting the tunnel. All authorized
tunnel users act as this local account; there is no per-ChatGPT-user Fulcra login.
Never use shared workspace credentials or expose local credentials through an
unauthenticated public HTTP wrapper.

From the checkout:

```sh
uv sync --locked
FULCRA_ENVIRONMENT=stdio FULCRA_MCP_VARIANT=openai \
  uv run --locked fulcra-context-mcp
```

That command speaks MCP over stdio; normally a client launches it. Stop it before
continuing: the tunnel will launch its own process. Use `claude` to test the
Claude composition, or omit the variant for the standard server.

## Create and run a tunnel profile

Install [tunnel-client](https://github.com/openai/tunnel-client/releases/latest).
Create or reuse a tunnel in [Platform settings](https://platform.openai.com/settings/organization/tunnels)
and associate it with the intended ChatGPT workspace. Creation requires Tunnels
Read + Manage; running/using it requires Read + Use. Supply the runtime key using
`CONTROL_PLANE_API_KEY` through your local secret mechanism; never put it in Git,
chat, or the plugin ZIP. Set `TUNNEL_ID` to the full ID returned by Platform.

```sh
tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile fulcra-openai \
  --tunnel-id "$TUNNEL_ID" \
  --mcp-command "env FULCRA_ENVIRONMENT=stdio FULCRA_MCP_VARIANT=openai uv --directory /absolute/path/to/fulcra-context-mcp run --locked fulcra-context-mcp"

tunnel-client doctor --profile fulcra-openai --explain
tunnel-client run --profile fulcra-openai
```

Replace the checkout path; quote it inside the command string if it contains
spaces. The `env` assignments are saved in the launch command so restarting the
profile does not depend on exported variant settings. Keep the tunnel running
for discovery and calls. Use a separate profile name and `FULCRA_MCP_VARIANT=claude`
for Claude. Do not run competing profiles against the same tunnel at once.

To locate an existing profile:

```sh
tunnel-client profiles list
```

Inspect `control_plane.tunnel_id` in the listed YAML file (default directory:
`~/.config/tunnel-client`). Environment and flag overrides can supersede saved
values. Profile creation does not provision a new OpenAI tunnel.

## Connect the plugin

In ChatGPT, choose **Plugins → Add custom MCP server → Connection: Tunnel**,
select the tunnel, and select no MCP authentication for this stdio setup. Access
is controlled by the tunnel; Fulcra authentication is already local. Copy the
registered MCP app's `asdk_app_…` ID, not the tunnel or wrapper plugin ID.

Use that app ID with the plugin's
[registered test builder](https://github.com/fulcradynamics/fulcra-openai-plugin/blob/main/docs/testing.md#registered-test-variants).
The registered-only ZIP must omit the portable production connection.
Refresh discovery and use a fresh conversation after changing the server.
Verify `get_user_info` identifies the intended test account, then open Agents I
Know. Automated stdio tests use a synthetic backend; actual tunnel connectivity
and native ChatGPT rendering require this separate acceptance check.

Secure tunnels are for private testing, not public plugin distribution. Production
retains hosted OAuth and a stable public HTTPS endpoint. See OpenAI's
[tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).
