# Fulcra Mesh MCP App

`aicq_open({})` returns a readiness message and advertises `ui://fulcra/mesh/v17.html`.
The existing server serves the self-contained resource. After connecting, the UI
calls `get_data_catalog(name="Mesh Outbox")` and `list_shares(direction="both")`
through the standard MCP Apps SDK's `app.callServerTool`. Both are read-only.
Visible-app polling refreshes discovery and only the selected thread's messages.
No separate UI server, search, pagination, or OAuth changes.

## Automatic refresh (PLAT-649)

- Refresh immediately after connection and on return to visible, then nominally
  every 10 seconds after the preceding batch finishes. One scheduler owns list
  discovery and selected-thread reads; the latter reuse that same discovery.
- **Refresh threads** is available only on the thread list. Detail retains **Back
  to threads** and **Load messages** (which also applies edited dates). Automatic
  polling and the in-flight spinner remain active in both views. Manual requests during a
  batch coalesce into one follow-up. Discovery and all source reads drain before
  the next batch, even when a sibling request fails. Tool timeout is 30 seconds.
- Discovery or message-read failure backs off to 20, 40, then at most 80 seconds;
  success resets to 10 seconds. Manual retry and return-to-visible bypass the
  delay. Truncation/missing-side notices alone are not transient failures.
- Hidden documents start no requests. In-flight requests finish; a discovery
  completed while hidden starts no message reads. SDK resource teardown and
  pagehide clear timers/listeners, discard queued refreshes and ignore late data.
- A text status and subtle spinner are visible for the actual in-flight batch,
  including slow/failing sibling requests, not while waiting for the timer.
  Reduced-motion preference removes animation, retaining the text/static marker.
- Polls never make model turns, write mesh data, acknowledge messages, attach model
  context, send instructions, or schedule unattended agents. They may clear an
  explicitly attached snapshot when its displayed content becomes invalid.

The real-SDK local browser harness in `web/polling.spec.js` covers first/new thread
discovery, selected-only reads, arriving messages, coalescing/draining, backoff and
retry, applied dates, stale/revoked data, account labels, spinner/reduced motion,
keyed focus/disclosures/pending attachments, both-order scroll anchoring, visibility and SDK
teardown. It uses synthetic fixtures and a controlled browser clock, not an account.
Actual ChatGPT iframe visibility/timer throttling, outer-host scrolling/autoResize,
and live API rate limits still require operator acceptance; these fixtures cannot
prove those host behaviors.

## Branding and layout (PLAT-637)

Design references:
- https://github.com/kubla/fulcra-design-reference — Context Web `DESIGN.md`,
  `SOURCES.md`, and repository README.
- https://www.ui-skills.com/skills/leonxlnx/minimalist-skill — editorial minimalism.

Deliberate adaptation: retain Fulcra's black/charcoal surfaces, Rubik, mint actions
and readable violet disclosure selection rather than the generic warm monochrome
palette and alternative fonts. Use whitespace, thin dividers, flat surfaces and
compact controls, not boxed panels, pills, decorative gradients, shadows, icons,
decorative animations, hero/bento layouts or stock imagery. The refresh spinner is
a functional exception for request observability. The identity image is the existing
`fulcra_mcp/static/icon.png`, embedded unchanged, alongside a plain text wordmark;
no new logo was invented. Metadata uses a lighter gray for readability on dark
surfaces. Message bodies, source UUIDs and expanded context wrap at narrow widths.

Editable styles live in `web/styles.css`. `web/build.mjs` embeds them, the existing
brand image, the bundled Rubik Latin variable WOFF2 and its complete OFL license
into the single `fulcra_mcp/ui/mesh.html`. There are no runtime external font,
image, stylesheet or script requests. Other writing systems fall back to system
fonts. See `web/assets/README.md` for asset provenance. Rebuilding is offline once
npm dependencies are installed. The public `aicq_open` identifier and its app-only
visibility/global entrypoint metadata are unchanged. The distinct thread entrypoint
below uses the same compiled HTML, with only a fixed presentation meta tag changed
by the server resource handler; there is no second frontend build.

### Host footer and safe areas

The document body has real scrollable bottom padding of
`160px + env(safe-area-inset-bottom, 0px) + var(--host-safe-bottom, 0px)`.
This is not a fixed footer or an absolutely positioned spacer. There is no fixed
body height, overflow lock or nested scrolling message list; SDK autoResize stays
at its default enabled setting, so host-driven sizing includes this padding.

The installed `@modelcontextprotocol/ext-apps` 1.7.5 declarations (`app.d.ts` and
`spec.types.d.ts`) supply optional `safeAreaInsets` in pixels. `main.js` applies
`getHostContext()` after connection and registers `hostcontextchanged` before
connection. All four edges are respected; unrelated partial context changes do
not reset the insets. The SDK describes mobile safe areas, not floating composer
height. The fixed 160px allowance remains even when a host supplies no insets.
CSS environment and host bottom insets are added conservatively; a host reporting
the same device inset twice may leave extra whitespace. Hosts with an overlay
taller than 160px still need live acceptance testing and potentially a larger
allowance. Actual ChatGPT rendering/autoResize remains a host acceptance check,
not something the local synthetic harness proves.

### Repeatable local visual review

The real SDK browser tests in `web/messages.spec.js` use only synthetic catalog,
share and message fixtures in an iframe with `sandbox="allow-scripts"`. They do
not connect to an account or server. The host harness places a 160px fixed bar
over a 900px-high viewport and checks both 1120px and 320px widths. Tests verify
initial and changed SDK insets, continued resize notifications, loaded Rubik,
zero network requests, UUID/message/context wrapping, no horizontal overflow,
keyboard focus/Enter, and scroll reachability above the bar for the composer,
final feedback, context disclosure and Invite. Existing send/read-only regression
tests run alongside these checks.

From this checkout, reproduce the previews with:

```sh
cd /home/fulcra/.hermes/cache/scratch/mesh-conversation/web
npm run build
BRAND_PREVIEW_DIR=/home/fulcra/.hermes/cache/scratch npx playwright test messages.spec.js -g 'Fulcra branding'
```

The clock is fixed to 2026-01-10 for these synthetic previews. Output:
- `/home/fulcra/.hermes/cache/scratch/brand-preview-wide.png`
- `/home/fulcra/.hermes/cache/scratch/brand-preview-narrow.png`
- `/home/fulcra/.hermes/cache/scratch/brand-preview-composer-wide.png`
- `/home/fulcra/.hermes/cache/scratch/brand-preview-composer-narrow.png`

The first pair shows the top of the thread; the second shows the composer and
attachment feedback scrolled above the simulated host bar. These are real
Chromium screenshots of fixtures, not live account data or ChatGPT screenshots.

## Peer threads

The list shows one row per exact other Fulcra user ID and counts **threads**, not
outboxes or acknowledged relationships. Discovery uses the actual `tools.py`
formats: the compatible-tool catalog and `Shares: {own_fulcra_userid, outgoing,
incoming}`. Only readable MomentAnnotation channels following the Mesh Outbox
name convention are discovered. Names select channel candidates; they never
identify a peer. Slugs, display names and envelope routing are not identity evidence.
When incoming shares provide one unambiguous `sharing_fulcra_user_name` for that
exact peer, the row and thread heading show **Account: name**, alongside the exact
ID. Missing/conflicting names fall back to ID only. This is not an agent name;
agents sharing one account are not distinguishable through these APIs.

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

The initial window is today and yesterday: two UTC calendar dates. Editable
From/Through dates are inclusive, converted to timezone-aware start/end-exclusive
bounds. The result shows the **applied** range; editing dates alone does not relabel
it or change agent context. Polls use the last submitted dates, ignoring unsaved
picker edits. There is no pagination or Load more. A failed newly requested range
may retain the previous displayed range, explicitly labeled stale but still sendable;
retries continue to request the submitted range, never the unsubmitted inputs.

## Messages and completeness

Messages have Incoming/Outgoing labels and exact source owner/type IDs. **Latest
first** is the default; **Oldest first** reverses valid timestamps. Browser-local
timestamps are shown; invalid/missing timestamps are
labeled unavailable and placed last. Mesh envelopes show body and available
routing/kind/slug/message-ID fields. Unrecognized notes remain visible as raw text.
All content is rendered as text, never HTML. Reading does not send, acknowledge,
write records, or update model context automatically.

Errors and truncation are identified per source while successful records from other
channels remain visible. A zero result is called an empty conversation only when
all discovered eligible reads complete without warnings. Completeness applies only
to accessible channels in the applied range, not all history or data outside share
permissions (including time-limited grants). Narrow the dates for truncated results.

Keyed thread rows preserve keyboard focus; Back to threads returns focus to the
selected row (or Refresh threads if it disappeared). Keyed messages preserve the
visible message and its pixel offset while reading history, with **New activity**
to jump to the latest edge in either order. Already-latest readers follow incoming
content, except when focusing thread controls. Refresh retains
focus, open disclosures and pending attachment state; navigation invalidates old reads
and composers. Late responses cannot replace the current peer view.

Discovery failure retains last-good displayed data with explicit stale/unverified
status and last-success time. Previously loaded context remains sendable, including
a successfully loaded empty thread; the preview and sent payload include stale and
incomplete warnings. Discovery failure reads no cached channels. A message-source
failure retains only that source's last-good
records from the same range, marked stale with source identity and last-success
time in the UI and bounded context. Other successful sources refresh normally.
Successful discovery removes revoked sources immediately, even if subsequent
reads fail; a disappeared peer has no sendable cached context. Load messages or
Refresh threads retries. Invite remains independent.
The call indicator is in Fulcra Mesh; the host decides whether app-originated calls also
appear in the conversation UI.

## Global presentation: Continue conversation in chat (resource v17)

Within the global entrypoint, the sole thread action is **Continue conversation in chat**, directly below the
date pickers and above messages in both orders. There is no instruction textarea,
Tell my agent fallback, or combined request relay. The user types and sends their
request in the host's native chat.

Only an explicit click calls
`app.updateModelContext({content: [{type: 'text', text}]})` with the exact current
preview. It does not call `sendMessage`, start a model turn, write Mesh data,
reply or acknowledge anything. `updateModelContext.text` support is required
independently of `message.text`; unsupported hosts retain read-only browsing and
show an attachment-unavailable notice. Invite remains a separate message flow.

The reusable `web/thread-context.js` builder preserves exact peer ID, applied
range, warnings, completeness, displayed/omitted counts and each displayed
record's source owner/type and direction. Historical bodies are labeled quoted
untrusted reference data, not instructions. No unrelated peer or undisplayed
history is included. The expandable preview shows the exact attachment text.
The 24,000 UTF-16-code-unit bound includes label and metadata, retaining only a
prefix of whole records in displayed order. Clipping is disclosed; oversized
metadata disables attachment. Successfully loaded stale or empty context remains
usable with its original range and explicit warnings; revoked sources are removed.

Attachment pending state prevents repeat clicks across refresh and navigation.
Failures/timeouts report unconfirmed attachment and permit explicit retry, never
an automatic message or retry. After confirmed attachment, the app requests PiP
only if the host advertises it. Returned mode, denial and errors are reported
honestly; neither PiP nor this button guarantees opening/focusing native chat.
Guidance explicitly says the conversation may need manual expansion.

One app-wide serialized context queue orders attaches and empty-content clears
across peers. Back, navigation, source revocation, applied-range changes and
changed displayed records/order/warnings invalidate the attachment. A late attach
must drain before cleanup and cannot request PiP after invalidation. Unchanged
polls do not reattach or clear merely because refresh timestamps changed. Changed
polls clear attached context; a new explicit click is required to attach again.
Clear failures remain visible even on the thread list. SDK teardown awaits
cleanup; abrupt closure or transport loss cannot guarantee host cleanup. A timeout
is not proof of nondelivery, and context already consumed cannot be retracted.

`web/native-context.spec.js` exercises the real SDK in an allow-scripts-only
sandbox, including capability independence, no ui/message before/after click,
bounded exact-peer context, failures, serialization, invalidation and teardown.
Message/provenance, stale-load, polling, focus, disclosure and scroll tests assert
context-only attachment for the global presentation. The separate thread-entrypoint
tests below cover its explicit message-send path. These verify local protocol
behavior with synthetic data, not live ChatGPT acceptance.

## Thread entrypoint: Mesh conversation (PLAT-657, resource v17)

`mesh_conversation_open` is titled **Mesh conversation**, visible to both model and
app, read-only, and registered with `openai/ui.entrypoints: [{type: "thread"}]`.
It accepts `{}` for a manual picker or an optional exact `peer_fulcra_userid` string
for a referenced peer. It returns `{presentation: "thread", peer_fulcra_userid}`
without reading or writing an account. Blank IDs are rejected; nonblank IDs are
preserved exactly, not trimmed, resolved by name, or normalized. Discovery in the
app determines availability using authorized catalog/sharing relationships. An
unknown, unavailable or ambiguous peer stays on the picker with an explanation;
no different peer is substituted. Multiple eligible channels for one exact peer
are still one thread, not ambiguity.

The tool advertises `ui://fulcra/mesh/thread/v17.html`. Its resource serves the
same compiled `mesh.html` as the global entrypoint, replacing only the fixed
`mesh-presentation` meta tag. Presentation is never inferred from `displayMode`:
both entrypoints may be fullscreen. Initial tool-result/cancellation handlers are
registered before `connect()`. The first result is consumed once whether it
arrives before or after the connection resolves; the opener is never called again.
The pinned SDK 1.7.5 supplies a `CallToolResult` notification with
`structuredContent`; optional `hostContext.toolInfo` is tool metadata, not the
initial result. Thread launch waits for that result. If it never arrives, users
can use Refresh threads and choose a peer; a late result cannot override an
explicit picker choice. Global launch retains its existing readiness/discovery UX.

The shared thread composer adds a two-row textarea and **Tell my agent** only in
thread presentation. An explicit click on a nonblank draft attaches the bounded
displayed context separately, awaits acknowledgment, then revalidates navigation
and the context lifecycle before sending exactly one `role: "user"` message whose
sole text block is the original textarea value, including leading/trailing
whitespace. No prefix or history is appended to that message. Both `message.text`
and `updateModelContext.text` capabilities are required; there is no silent fallback.
The shared 24,000-code-unit context bound, exact peer/source provenance, applied
dates, clipping and stale/revoked-source handling described above apply here too.

Pending sends are guarded across repeated clicks and peer navigation. Drafts are
kept per peer in memory until the app closes; failures and uncertain delivery retain
them. Only host acceptance while that composer is still current and the draft
version unchanged clears the draft. Send outcome feedback is separate from context
cleanup feedback. Acceptance means the host accepted the bridge request, not that
the agent completed an action. A user-role bridge message does not establish native
user authorship, override consent, post directly to a peer, or acknowledge anything.
Timeouts cannot prove nondelivery; check the host conversation before retrying.

**Suggest replies** runs only on explicit click and only when the host advertises
`sampling`. It calls `app.createSamplingMessage` with the same bounded untrusted
current context, `includeContext: "none"`, no tools, and `maxTokens: 400`. Its
instruction requests up to three short logical replies. The parser accepts only an
assistant text completion containing a JSON array of one to three nonblank strings,
each at most 300 code units, with a total text bound of 2,000 code units. Control
characters, malformed/prose responses, truncated/tool-use completions and other
content types are rejected. Suggestions render as plain text. Selecting one
explicitly replaces the draft only; it never sends. Late results after context,
navigation or draft changes are discarded, and outstanding sampling is guarded
across navigation. Errors/unsupported hosts display truthful notices, not fabricated
replies. Without sampling, the Suggest replies button is hidden while the notice
“This host does not support reply suggestions (sampling).” remains visible.
Opening, reading and polling never request sampling.

`web/thread-entrypoint.spec.js` uses the real pinned SDK in a synthetic sandbox host
to exercise launch timing, exact matching, presentation separation, message wire
content, capability gates, pending/navigation races, uncertainty and sampling.
`web/reply-suggestions.test.js` checks the strict parser. No account or provider is
called. Actual ChatGPT thread-tab discovery/rendering, sampling availability and
host consent behavior remain operator acceptance checks. The host may reject or
modify sampling; sampling is not a subscription to native-chat replies. Serialized
context cleanup cannot retract context already consumed or guarantee ordering after
a transport timeout. No direct Mesh write or automatic acknowledgment is implemented.

Capture synthetic thread-composer screenshots at 1120px and 320px:

```sh
cd web
THREAD_PREVIEW_DIR=/home/fulcra/.hermes/cache/scratch npx playwright test thread-entrypoint.spec.js -g 'thread presentation layout'
```

Outputs are `mesh-thread-1120.png` and `mesh-thread-320.png` in that directory.
These are scrolled, fixed-height synthetic iframe previews, not ChatGPT screenshots;
they check the small textarea, suggestion controls and horizontal fit, not real-host
autoResize or overlay behavior.

## Implementation

- `fulcra_mcp/apps.py`: FastMCP registration, global/thread metadata and fixed resource presentation.
- `web/entrypoint.js`: pre-connect initial-result delivery and resource presentation.
- `web/meshes.js`: catalog/shares discovery and reliable account labels.
- `web/refresh.js`, `threads.js`: visible lifecycle scheduler, backoff, keyed list.
- `web/conversation.js`, `records.js`, `messages.js`: refreshed multi-channel reads,
  record parsing, ordering, stale provenance and thread presentation.
- `web/message-list.js`: keyed message reconciliation and scroll anchoring.
- `web/thread-composer.js`, `thread-context.js`, `native-context.js`: persistent
  thread action, bounded context and serialized attachment/cleanup lifecycle.
- `web/thread-actions.js`, `reply-suggestions.js`: thread-only exact-text sends and
  explicitly requested, capability-gated suggestions.
- `fulcra_mcp/ui/mesh.html`: generated self-contained UI, included in Python wheels
  and source distributions. No CDN or Node runtime is needed to run the server.
- `fulcra_mcp/main.py`: mounts the UI alongside existing tools in both transports.

We use FastMCP's existing MCP Apps support and the standard browser SDK, not the
separate `openai-mcp-extensions` Python SDK. No dependency upgrade.

## Invite button

**Invite someone** is global at the top-right in both the list and thread views.
At narrow widths it wraps to its own right-aligned header row without horizontal
overflow. Invitation help and live status remain directly below the header;
moving the control does not change its capability gating or message behavior.

The real-SDK layout regression in `web/messages.spec.js` checks both 1120px and
320px, list-only refresh, Back navigation, Load messages, in-flight status, keyboard
invitation, acceptance/rejection feedback and no automatic context attachment.
Capture synthetic list/thread screenshots with:

```sh
cd web
LAYOUT_PREVIEW_DIR=/home/fulcra/.hermes/cache/scratch npx playwright test messages.spec.js -g 'global top-right'
```

Outputs are `layout-list-1120.png`, `layout-list-320.png`,
`layout-thread-1120.png` and `layout-thread-320.png` in that directory.

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

Commit both source and regenerated `fulcra_mcp/ui/mesh.html`; CI checks they match.
The browser test uses the real SDK and an iframe host harness, not real ChatGPT.
After pulling, restart the tunnel, refresh the ChatGPT connection, and reopen Fulcra Mesh.
In the global entrypoint, click Continue conversation in chat and verify context
attachment without a model turn; then type and send a request in native chat.
Separately open Mesh conversation as a thread tab with `{}` and through a model
reference to an exact peer ID. Verify its distinct controls, capability notices,
exact typed message, host consent behavior and suggestions if sampling is supported.
Test Invite separately. This is
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

List tools, call `aicq_open` with `{}`, and read `ui://fulcra/mesh/v17.html`.
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
The entrypoint readiness message does not access them, but opening the UI reads the
account's catalog and shares to discover peer threads. Other tools are also exposed.
Use a dedicated OS account with no Fulcra credentials, or a synthetic test account,
and restrict tunnel/workspace access. Do not expose stdio-mode tools through an
unauthenticated public HTTP wrapper. Multi-user production must retain hosted OAuth.

In ChatGPT Plugins, add a custom MCP server, choose **Tunnel**, and select this
tunnel. For this stdio setup there is no MCP OAuth flow; the tunnel itself controls
access. Create it as a plugin. Confirm discovery includes `aicq_open`, then open
**Fulcra Mesh** from the sidebar. Refresh the connection after
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
