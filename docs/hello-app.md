# AICQ Hello World MCP App

`aicq_open({})` returns a greeting and advertises `ui://aicq/hello/v6.html`.
The existing server serves that resource. After connecting, the UI makes one
read-only `get_data_catalog(name="Mesh Outbox")` call through `app.callServerTool`.
No separate UI server, polling, or OAuth changes.

## Mesh list

Opening AICQ shows the tool name and a loading message until its response arrives.
It lists distinct accessible MomentAnnotation channels named Mesh Outbox, keyed
by owner and data-type ID, and shows their actual count, including zero. Own and
shared channels are included. This is an outbox count, not a count of acknowledged
two-way relationships; the skill has no separate mesh registry. Custom names not
following the skill convention are not discovered. Message contents are only read
after selecting an outbox.

## Message details

Click an outbox, or choose Load messages, to refresh both existing discovery tools:
`get_data_catalog(name="Mesh Outbox")` and `list_shares(direction="both")`.
This discovers a newly shared return outbox without a handshake or acknowledgement.
No record read occurs on list load. Pairing uses exact catalog owner/type IDs, never
names, envelope routing, or acknowledgement state:

- Own selected outbox: its exact outgoing share identifies one unique recipient;
  that peer's incoming direct share and catalog entry identify one return outbox.
- Shared selected outbox: its catalog owner identifies the peer; narrow outgoing
  shares to that peer identify one own outbox. The selected incoming share must
  also be narrow/direct, and the own counterpart must have one direct recipient.
- Only explicit `share_all_data=false`, single-type direct shares are eligible;
  outgoing shares must have one `with_user_ids` recipient, incoming grants must
  have `grant_type="user"` and `sharing_fulcra_userid`. Group shares, file shares,
  multiple types/recipients, and all-data shares are not pairing evidence.
- Catalog channels must support `get_records`. Duplicate owner/type entries and
  duplicate grants do not create extra channels. Same type IDs in different owners
  remain distinct. Missing/ambiguous pairing or failed discovery leaves the selected
  side readable with an explicit incomplete/conversation-unavailable warning.

Only the selected outbox and its uniquely paired counterpart are read with
`get_records`; each retains its own catalog `fulcra_userid` (absent means own).
Both use the same user-selected date window. The initial window is today plus the
preceding 29 UTC calendar dates; editable From/Through dates are inclusive, converted
to timezone-aware start/end-exclusive bounds. Change dates and Load messages to
read older messages. There is no polling or pagination.

The detail panel labels messages Incoming/Outgoing, sorts them chronologically,
and displays timestamps in the browser's local timezone. Missing/invalid timestamps
are labeled unavailable and placed last. Each Tell My Agent control uses that
message's original source outbox/owner/type, not the selected channel's identity.
Mesh envelopes display their body and available routing/kind/slug/message-ID fields;
unrecognized notes remain visible as raw text. All content is text-only: no message
HTML, automatic model context, replies, or acknowledgements.

Read errors and truncation are identified per source; successful messages from the
other side remain visible. Zero records is only reported as an empty conversation
when discovery/pairing and both reads succeed without truncation. Narrow the range
for truncated results; this view does not claim all history or data outside the
user's share permissions (including time-limited grants).

Back to meshes preserves the list. Late discovery/read responses from a previous
selection cannot replace the current view or enable its pending Load button;
stale discovery does not start record reads. Load messages retries discovery and
both selected/paired reads. Multiple conversations with the same peer remain
ambiguous rather than being merged by name. Custom-named outboxes outside the Mesh
Outbox convention are not discovered. Group conversations are not reconstructed.

Tool errors, invalid responses, and transport failures/timeouts produce warnings,
never an empty-success claim. Invitation messaging remains independent.
The visible call indicator is in AICQ itself; the host controls whether app-originated
tool calls also appear in ChatGPT's conversation UI.

- `fulcra_mcp/apps.py`: FastMCP registration and OpenAI global-entrypoint metadata.
- `web/`: UI source and the standard MCP Apps browser SDK.
- `fulcra_mcp/ui/hello.html`: generated self-contained UI, committed and included in Python wheels and source distributions. No CDN or Node runtime is needed to run the server.
- `fulcra_mcp/main.py`: mounts the UI alongside the existing tools in both transports.

We use FastMCP's existing MCP Apps support and the documented OpenAI metadata,
not the separate `openai-mcp-extensions` Python SDK. No Python dependency upgrade.

## Tell My Agent (PLAT-636)

Each returned message has a textarea and **Tell My Agent** button. On explicit
click, `app.sendMessage` sends a user-role request containing the typed instruction
and only that message's record plus its outbox name, type ID, and shared owner ID.
The instruction and JSON context are separate text blocks; the latter is labeled
untrusted data, not instructions or authorization. No tool write, peer reply, or
automatic model-context update occurs. The host owns the subsequent agent turn.

Whitespace-only instructions and unsupported hosts leave the button disabled.
While pending, repeat clicks and input editing are disabled. Success clears the
draft and reports request acceptance, not task completion. Errors/timeouts preserve
the draft and warn to check the conversation before retrying. Drafts are local to
the current rendered detail view and are cleared on navigation/reload.

## Invite button

**Invite someone** sends one user-role `ui/message` through the host, asking the
agent to use `fulcra-mesh` and ask who to invite before creating/sharing anything.
It does not call data tools, create shares, or send an invitation to another user.
Install the companion Fulcra plugin so the agent has the mesh skill; the UI does
not install or deterministically execute skills. The host owns the follow-up turn.

The button enables after the MCP Apps handshake confirms text-message support,
disables while sending, and reports rejection/transport failure without claiming
an invitation was sent. Hosts without support show instructions to ask in chat.

When editing UI source (Node 22+):

```sh
cd web
npm ci
npm test
npm run build
npx playwright install chromium
npm run test:browser
```

Commit both source and regenerated `fulcra_mcp/ui/hello.html`; CI checks they match.
The browser test uses the real SDK and an iframe host harness, not real ChatGPT.
After pulling, restart the tunnel, refresh the ChatGPT connection, and reopen AICQ.
Click the button and verify the conversation receives the mesh request. This is
separate from the known server-session initialization error; no workaround for
that error is introduced here.

## Run this checkout locally

```sh
uv sync --locked
FULCRA_ENVIRONMENT=stdio uv run --locked fulcra-context-mcp
```

This command speaks MCP over stdio, not HTTP. A client normally launches it.
For a transport smoke test, use MCP Inspector and configure that same command:

```sh
npx @modelcontextprotocol/inspector@latest
```

List tools, call `aicq_open` with `{}`, and read `ui://aicq/hello/v6.html`.
The tool is app-visible, so a host may hide it from model-facing tool selectors.

## Reach the local branch from ChatGPT

Use [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
for private testing from both desktop and web. Install `tunnel-client`, create a
tunnel in Platform settings, and associate it with the target ChatGPT workspace.
The operator needs tunnel Read/Use permission and custom MCP server permission.
Set the tunnel runtime key through your local secret-management mechanism;
do not commit it or put it in the plugin archive.

```sh
export FULCRA_ENVIRONMENT=stdio
tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile fulcra-local \
  --tunnel-id "$TUNNEL_ID" \
  --mcp-command "uv --directory /absolute/path/to/fulcra-context-mcp run --locked fulcra-context-mcp"
tunnel-client doctor --profile fulcra-local --explain
tunnel-client run --profile fulcra-local
```

Replace the checkout path with yours, on this branch. The tunnel launches the
server, so a separate stdio process is not needed. Keep the tunnel running.

**Account boundary:** stdio data tools use the local operator's Fulcra credentials.
The entrypoint greeting does not access them, but opening the UI now reads the
account's catalog to discover mesh outboxes. Other tools are also exposed.
Use a dedicated OS account with no Fulcra credentials, or a synthetic test account,
and restrict tunnel/workspace access. Do not expose stdio-mode tools through an
unauthenticated public HTTP wrapper. Multi-user production must retain hosted OAuth.

In ChatGPT Plugins, add a custom MCP server, choose **Tunnel**, and select this
tunnel. For this stdio setup there is no MCP OAuth flow; the tunnel itself controls
access. Create it as a plugin. Confirm discovery includes `aicq_open`, then open
**AICQ** from the sidebar and expect **Hello world**. Refresh the connection after
restarting a changed server; begin a fresh session if the host caches metadata.

To include skills and branding, build your plugin package with a registered-app
mapping for this connection only. Do not also point it at the production MCP URL.
A local marketplace is a desktop install mechanism; the registered tunnel
connection is what allows testing the server in the web client.

## Verification and publication

```sh
uv run --locked pytest
uv build
```

Tests exercise discovery, `{}` invocation, HTML retrieval and existing-tool
coexistence. Passing protocol tests is not a claim of actual ChatGPT rendering.
Record the desktop/sidebar test separately before calling the integration accepted.

For publication, deploy this same server branch with the existing hosted OAuth
configuration and a stable public HTTPS endpoint, then change the plugin's
registered connection. Secure MCP Tunnel is for private testing, not public
plugin distribution. No public endpoint or tunnel is provisioned by this change.

References: [MCP Apps UI](https://developers.openai.com/plugins/build/chatgpt-ui),
[OpenAI extensions](https://developers.openai.com/plugins/build/extensions),
[connection testing](https://developers.openai.com/plugins/deploy/connect-chatgpt).
