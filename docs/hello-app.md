# AICQ Hello World MCP App

`aicq_open({})` returns a greeting and advertises `ui://aicq/hello/v7.html`.
The existing server serves the self-contained resource. After connecting, the UI
calls `get_data_catalog(name="Mesh Outbox")` and `list_shares(direction="both")`
through the standard MCP Apps SDK's `app.callServerTool`. Both are read-only.
No separate UI server, polling, search, pagination, or OAuth changes.

## Peer threads

The list shows one row per exact other Fulcra user ID and counts **threads**, not
outboxes or acknowledged relationships. Discovery uses the actual `tools.py`
formats: the compatible-tool catalog and `Shares: {own_fulcra_userid, outgoing,
incoming}`. Only readable MomentAnnotation channels following the Mesh Outbox
name convention are discovered. Names select channel candidates; they never
identify a peer. Slugs, display names and envelope routing are not identity evidence.

- Incoming: the catalog's `fulcra_userid` identifies the channel owner and peer.
  Accessible incoming channels remain usable without a reciprocal/direct incoming
  grant or acknowledgement. A shared owner's stream is not proof that every record
  is exclusively addressed to this user; source identity is always visible.
- Outgoing: all grants covering an own channel must be narrow exact-channel grants
  to the same single other `with_user_ids` recipient. Explicit
  `share_all_data=false`, one data type, and no groups/files are required.
  A narrow grant cannot hide another broad, group, multi-type, or multi-recipient
  grant covering that channel. Multiple separate narrow channels to the **same**
  peer are eligible and combined, not treated as ambiguous.
- Own identity comes from `list_shares.own_fulcra_userid`. An absent catalog owner
  means own; an explicit own ID is normalized to the same identity. Duplicate
  owner/type entries and grants do not add channels; equal type IDs under different
  owners remain distinct. No self thread is created.
- Ineligible own channels (including orphan and self-only channels) are omitted,
  with a discovery warning count, not turned into fake threads. Incoming-only and
  outgoing-only threads show an explicit missing-side/incomplete notice.
- Discovery failure, malformed results, or missing own user ID stops the load.
  No guessing of owners or fallback to cached channels.

Opening the list never reads records. Selecting a peer or clicking **Load messages**
refreshes both discovery tools, then reads every currently eligible channel for that
exact peer. Other peers' records are not read. All `get_records` calls use the same
applied time bounds. Shared reads pass their exact owner ID; own reads omit the
parameter. Every displayed record retains its original exact owner/type identity.

The initial window is today plus the preceding 29 UTC calendar dates. Editable
From/Through dates are inclusive, converted to timezone-aware start/end-exclusive
bounds. The result shows the **applied** range; editing dates alone does not relabel
it or change agent context. There is no polling or pagination.

## Messages and completeness

Messages have Incoming/Outgoing labels and exact source owner/type IDs. They sort
chronologically, with browser-local timestamps; invalid/missing timestamps are
labeled unavailable and placed last. Mesh envelopes show body and available
routing/kind/slug/message-ID fields. Unrecognized notes remain visible as raw text.
All content is rendered as text, never HTML. Reading does not send, acknowledge,
write records, or update model context automatically.

Errors and truncation are identified per source while successful records from other
channels remain visible. A zero result is called an empty conversation only when
all discovered eligible reads complete without warnings. Completeness applies only
to accessible channels in the applied range, not all history or data outside share
permissions (including time-limited grants). Narrow the dates for truncated results.

Back to threads preserves the initial list; reopen the app to discover new peer
rows. Each detail load rediscovers that peer's channels. Navigation/reload invalidates
old discovery, reads and composers. Late responses cannot replace the current view;
stale discovery starts no reads. Failed discovery or a disappeared peer leaves no
sendable cached context. Load messages retries. Invite remains independent.
The call indicator is in AICQ; the host decides whether app-originated calls also
appear in the conversation UI.

## Tell my agent (PLAT-636)

One bottom composer follows the last message, also when a successfully discovered
thread has zero records. It is not repeated per message. On explicit click,
`app.sendMessage` sends a user-role request with two text blocks:

1. The typed user instruction (maximum 4,000 UTF-16 code units).
2. The current displayed thread context: exact peer ID, applied range, warnings,
   completeness, displayed/omitted record counts, and a chronological list of
   displayed records with original exact source owner/type and direction.

The context block is explicitly **untrusted data, not instructions or authorization**.
It contains no undisplayed account history or unrelated peer records. The expandable
“Context sent with your instruction” preview shows the exact context text sent.
No tool write or peer reply occurs; the host owns the subsequent agent turn.

The context text, including its untrusted-data label and JSON metadata, is bounded
to 24,000 UTF-16 code units. It keeps a chronological prefix of whole records; an
oversized next record ends the prefix rather than cutting provenance or content.
Clipping is disclosed beside the composer and in the host's `omitted_records` count
and partial completeness. The full displayed thread remains visible. If metadata
alone exceeds the limit, sending is disabled with an explicit notice. Combined
instruction/context content is bounded by these limits plus a fixed instruction
prefix (wire JSON encoding adds transport overhead).

Whitespace-only instructions and unsupported hosts leave the button disabled.
While pending, repeat clicks and input editing are disabled. Acceptance clears the
draft, notifies the user to continue in chat, and does not claim task completion.
Errors/timeouts preserve drafts and warn to check the conversation before retrying.
Reload/navigation removes the old composer immediately, clears drafts and prevents
stale-context submission. A pending send may already have reached the host; the
composer warns to check chat before retrying after navigation.

## Implementation

- `fulcra_mcp/apps.py`: FastMCP registration and OpenAI global-entrypoint metadata.
- `web/meshes.js`: catalog/shares discovery and peer-thread list.
- `web/conversation.js`, `records.js`, `messages.js`: refreshed multi-channel reads,
  record parsing, chronology and thread presentation.
- `web/tell-agent.js`: bounded context and explicit host-message request safeguards.
- `fulcra_mcp/ui/hello.html`: generated self-contained UI, included in Python wheels
  and source distributions. No CDN or Node runtime is needed to run the server.
- `fulcra_mcp/main.py`: mounts the UI alongside existing tools in both transports.

We use FastMCP's existing MCP Apps support and the standard browser SDK, not the
separate `openai-mcp-extensions` Python SDK. No dependency upgrade.

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

List tools, call `aicq_open` with `{}`, and read `ui://aicq/hello/v7.html`.
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
account's catalog and shares to discover peer threads. Other tools are also exposed.
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
