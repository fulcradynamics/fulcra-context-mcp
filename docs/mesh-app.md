# Fulcra Mesh MCP App

`aicq_open({})` returns a readiness message and advertises `ui://fulcra/mesh/v26.html`.
The existing server serves the self-contained resource. After connecting, the UI
calls `get_data_catalog(name="Mesh Outbox")` and `list_shares(direction="both")`
through the standard MCP Apps SDK's `app.callServerTool`. Both are read-only.
Visible-app polling refreshes discovery and only the selected thread's messages.
No separate UI server, in-widget search, pagination, or OAuth changes.

## Human-readable mesh identifiers

`set_mesh_identifier(data_type: str, identifier: str)` is a dedicated authenticated
write tool for the caller's own active `MomentAnnotation/<uuid>` Mesh Outbox only.
It resolves the exact catalog ID with `fulcra_userid=<authenticated user ID>`,
requires one entry with that same owner and ID and a Mesh Outbox name, and refuses
incoming/shared, missing, ambiguous, deprecated, or non-mesh types. An outgoing
outbox need not already be shared (creation/backfill can precede sharing).

The description contract is one suffix `[mesh_identifier: "JSON string label"]`.
After the closing bracket, both parsers allow only JSON whitespace: U+0020
(space), U+0009 (tab), U+000D (CR), and U+000A (LF). All other characters,
including U+FEFF, U+0085, and U+001C–U+001F, make the marker malformed.
This explicit set avoids Python `strip()` versus JavaScript `trim()` differences.
The value is 1–80 Unicode code points, already trimmed, single-line, with no
Unicode control/format/surrogate characters or line/paragraph separators.
Brackets, quotes and backslashes inside a label are JSON escaped, not parsed by
a bracket regex. The shared Python parse/write helpers are in
`fulcra_mcp.mesh_identifier`; the display parser is in `web/mesh-identifier.js`.
The writer JSON-escapes spaces as `\u0020`, preserving repeated spaces through
catalog whitespace folding. Catalog output also protects existing raw JSON
string values while normalizing surrounding prose; invalid markers remain
invalid rather than being repaired by whitespace folding.

Appending or replacing one valid suffix preserves unrelated description bytes.
An identical value is a no-op. Multiple markers, malformed reserved markers, or
a marker followed by non-whitespace prose fail closed without writes. A marker
string inside the JSON label is data, not another marker. Generic
`create_data_type(base_type="moment", name="Mesh Outbox …", description=...)`
still accepts descriptions with the marker at creation. Agents that lack context
at creation can backfill explicitly with `set_mesh_identifier` during a later
check/send; app polling never writes. Plugin instruction policy is separate.

Legacy moment creation uses the SDK's `create_annotation` and
`POST /user/v1alpha1/annotation`. The setter uses authenticated SDK `fulcra_api`
GET and PUT on that same resource family: `/user/v1alpha1/annotation/{uuid}`.
It does not use `update_data_type`: the input-service endpoint updates a different
`data_types` table, not the legacy annotation behind this Mesh Outbox.
The annotation GET/PUT protocol was verified against the authoritative backend
routes and models. PUT replaces metadata and requires name, description, tags,
and annotation type; sending a description-only body is not safe or valid.

After the existing exact-owner catalog check, the setter checks the raw annotation
ID, `fulcra_userid`, and `annotation_type="moment"`. It requires complete valid
metadata, then sends only `name`, `description`, `annotation_type`, `spec`,
`measurement_spec`, and `tags`, preserving every non-description field from GET.
Row IDs, source IDs, and timestamps are never echoed into PUT. Missing or malformed
metadata fails closed; there are no fabricated defaults. Only a canonical supplied
`MomentAnnotation/<uuid>` is accepted, without path escaping or label inference.

The SDK follows the PUT's 303 redirect with GET. Independently of that response,
the setter performs another GET and verifies exact owner, ID, type, label, full
description, and unchanged non-description writable fields. No-op calls also read
back. A final exact-owner catalog lookup verifies the displayed marker.
The success JSON contains `data_type`, `fulcra_userid`, `identifier`, `changed`
and `verified: true`. Failures never return that success shape. There is no
compare-and-swap API: concurrent external edits can still be overwritten between
GET and PUT; readback is not an atomic concurrency guarantee.

Transport regressions exercise real SDK authentication, catalog resolution,
JSON request serialization, and 303 handling with synthetic HTTP responses,
including independent readback and preservation failures. Deployed/live behavior
remains untested; no live-account writes are part of verification.

All shared list/detail presentations and composer captions put the readable label
first, with the exact peer UUID on a smaller, muted line. Without a valid marker,
the UUID remains the primary identifier. Named outboxes show their data-type ID
as secondary text below the delivery selector; duplicate names retain exact IDs
in option labels so channels can still be distinguished. Prefer valid outgoing
labels owned by the current user over incoming ones. With multiple candidates in
the preferred direction, the lexically smallest exact data-type ID wins,
independent of catalog order or label text. Account-owner names remain separately
marked `Account:` and are not verified mesh/agent labels. Labels are untrusted
plain text, never HTML, grouping keys, routing values, or authorization evidence.
Rename polling updates existing keyed rows and headings, not identities. Message
block catalog names and owner/type provenance in attached context stay unchanged;
display identifiers are excluded from message source context. Mention search uses
mesh identifiers and exact peer IDs; the three base resources and direct-start
variant use v26.

## Native composer at-mentions

`mesh_mentions_search(query: string)` is an authenticated, read-only, app-visible
native picker tool. The server advertises the current named capability
`openai/mentions: {"searchTool": "mesh_mentions_search"}`. On the pinned
FastMCP/MCP stack this is emitted in `initialize.capabilities.experimental`, a
supported capability location for negotiated protocols through `2025-11-25`.
The stack negotiates newer requests down to that version; it does not implement
`2026-07-28`'s `server/discover`. The deprecated tool-level
`openai/extensions.mentions/search` marker is removed, not dual-advertised.
Standard MCP Apps metadata and read-only annotations remain intact.

Search returns `content: []` and `structuredContent: {items: ResourceLink[]}`:

- **List Meshes**, always first after successful discovery, references
  `mesh://threads`. Its JSON descriptor names `mesh_threads_open` with `{}`.
- Up to **20 peer suggestions**, named **Open Mesh: <mesh identifier> (<peer ID>)**
  or **Open Mesh: <peer ID>** when no valid identifier exists. Identifier selection
  matches the list: prefer valid own/outgoing description markers, then incoming;
  within a direction the lexically smallest exact data-type ID wins. Account-owner
  names are not used as mesh identifiers. Malformed markers are ignored.
  Search is case-insensitive over the selected identifier and exact IDs, with surrounding
  query whitespace ignored. Empty queries return the first peers, ordered by
  exact ID. Same-name peers stay distinct; same-peer channels are deduplicated.
- Peer links use `mesh://threads/id-<percent-encoded-exact-peer-id>`. The resolver
  rechecks current authorization and returns `peer_fulcra_userid`, `title`, and
  `open_tool: {name: "mesh_conversation_open", arguments: {peer_fulcra_userid}}`.
  `open_tool` is application descriptor data for the agent, not a host extension
  or a promise that resource selection invokes a tool.

Server instructions and opener descriptions tell the agent to open the list or
exact thread when the user submits one of these action mentions without another
task, rather than asking what to do next. An explicit user request takes
precedence. Titles remain untrusted data, and opening grants no permission to
send messages, create shares, or mutate data. Resolving a suggestion does not
read message bodies; an opened thread subsequently loads its normal dated view.
The list link is now a small action descriptor rather than an HTML attachment,
so the model has an explicit tool-backed path to rendering. Previously issued
peer links and the direct-start HTML resource remain supported.

Search and peer resolution use current request credentials, catalog and shares,
not cached account discovery. Incoming-owner and all-covering-outgoing-grant
rules match `web/meshes.js`, with shared parity fixtures. Unknown, revoked, or
newly ambiguous peers fail closed. Discovery failure is an error, not an empty
list or stale result. There are no message reads, model calls or writes during
search/resolution. Hosted HTTP retains OAuth; stdio uses operator credentials.

According to the [OpenAI composer at-mention contract](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md#composer-at-mentions),
expected native-picker support is **Desktop only**, not Web/iOS/Android. The Web
column refers to the Work browser and excludes classic ChatGPT. Selection inserts
a prompt reference; actual agent tool choice and UI rendering remain host
acceptance checks, not guarantees supplied by the mention protocol.

Tests cover serialized capability negotiation, removal of the legacy marker,
search bounds/filtering, encoded exact IDs, descriptor-to-opener/resource routing,
HTTP OAuth rejection, account isolation, revocation and metadata-only backend
access. To test in ChatGPT: restart the server, refresh connection discovery,
and use a fresh conversation. Submit **List Meshes** alone, then a peer action
alone; expect `mesh_threads_open({})` and `mesh_conversation_open` with the resolved
ID respectively, without a clarification. Also test an explicit different task,
duplicate names and a revoked peer. Compare the direct tunnel target and plugin
target separately; protocol success does not prove plugin-mediated discovery.
No plugin rebuild is required for these server-only instructions.

## Automatic refresh

- Refresh immediately after connection and on return to visible, then nominally
  every 10 seconds after the preceding batch finishes. One scheduler owns list
  discovery and selected-thread reads; the latter reuse that same discovery.
- **Refresh threads** is available only on the thread list. Detail retains **Back
  to threads** and **Load messages** (which also applies edited dates). Automatic
  polling remains active in both views, without a global refresh indicator. Manual requests during a
  batch coalesce into one follow-up. Discovery and all source reads drain before
  the next batch, even when a sibling request fails. Tool timeout is 30 seconds.
- Discovery or message-read failure backs off to 20, 40, then at most 80 seconds;
  success resets to 10 seconds. Manual retry and return-to-visible bypass the
  delay. Truncation/missing-side notices alone are not transient failures.
- Hidden documents start no requests. In-flight requests finish; a discovery
  completed while hidden starts no message reads. SDK resource teardown and
  pagehide clear timers/listeners, discard queued refreshes and ignore late data.
- Only the first message-read attempt per selected thread view shows a spinner,
  inside the message area below its divider. It drains all sibling reads, then
  disappears on success or failure. Discovery failure also consumes the first
  attempt. Subsequent polls, manual retries and date loads never show a spinner;
  navigating away and selecting again starts a new view. Reduced motion keeps
  the loading text/static marker without rotation.
- Read failures (including partial failures) and selected-view discovery failures
  show `Could not load messages. Retrying in X seconds.` The scheduler publishes
  the actual next deadline only after the whole batch drains; a display-only tick
  derives the live countdown from that deadline and never starts requests.
  During retry: `Could not load messages. Retrying…`. Hidden apps show
  `Could not load messages. Retries paused while this app is hidden.` instead of
  a fictitious deadline. Countdown ticks are cleared on navigation and disposal.
  Known revoked peers stay `This thread is no longer available.`, including after
  a later discovery failure; retry text is not a promise to restore access.
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

## Branding and layout

Design references:
- https://github.com/kubla/fulcra-design-reference — Context Web `DESIGN.md`,
  `SOURCES.md`, and repository README.
- https://www.ui-skills.com/skills/leonxlnx/minimalist-skill — editorial minimalism.

Deliberate adaptation: retain Fulcra's black/charcoal surfaces, Rubik, mint actions
and readable violet disclosure selection rather than the generic warm monochrome
palette and alternative fonts. Use whitespace, thin dividers, flat surfaces and
compact controls, not boxed panels, pills, decorative gradients, shadows, icons,
decorative animations, hero/bento layouts or stock imagery. First-load feedback and
a subtle 180ms opacity/4px translation on newly created message content are functional
exceptions. Unchanged/reordered keyed rows do not animate again; reduced motion skips
insertion animation. Row geometry does not animate, preserving reader anchors.
The identity image is the existing
`fulcra_mcp/static/icon.png`, embedded unchanged, alongside a plain text wordmark;
no new logo was invented. Metadata uses a lighter gray for readability on dark
surfaces. Message bodies, catalog labels and expanded context wrap at narrow widths.

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
  is exclusively addressed to this user; exact source identity remains in the context preview.
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
  outgoing-only threads retain an explicit missing-side/incomplete notice in context.
- Discovery failure, malformed results, or missing own user ID stops the load.
  No guessing of owners or fallback to cached channels.

Opening the list never reads records. Selecting a peer or clicking **Load messages**
refreshes both discovery tools, then reads every currently eligible channel for that
exact peer. Other peers' records are not read. All `get_records` calls use the same
applied time bounds. Shared reads pass their exact owner ID; own reads omit the
parameter. Every displayed record retains its original exact owner/type identity.

The initial window is today and yesterday: two UTC calendar dates. Editable
From/Through dates are inclusive, converted to timezone-aware start/end-exclusive
bounds. Context retains the **applied** range; editing dates alone does not relabel
it or change agent context. Polls use the last submitted dates, ignoring unsaved
picker edits. There is no pagination or Load more. A failed newly requested range
may retain the previous displayed range, marked stale in context but still sendable;
retries continue to request the submitted range, never the unsubmitted inputs.

## Messages and completeness

Message headers show `Incoming (catalog item name)` or simply `Outgoing`.
The thread heading omits an account label that only repeats the exact peer ID;
readable account names and the existing primary/secondary peer identity remain.
Original catalog names and exact source IDs remain in attached context.
Names come from the source catalog entry, not the account label or envelope;
missing/blank names use `Catalog name unavailable`. Names are display-only:
keyed row identity and authorization still use exact owner/type IDs, which remain
in the bounded context and its preview rather than message headers. **Latest
first** is the default; **Oldest first** reverses valid timestamps. Browser-local
timestamps appear on a separate muted, smaller line with tighter spacing/line-height.
Direction/catalog-name headers have stronger weight than body text without larger type;
invalid/missing timestamps
are labeled unavailable and placed last. Recognized v1 mesh envelopes show only
the existing parsed body, without the generated routing/kind/slug/message-ID line.
No new parsing or normalization is applied; unrecognized notes remain intact as raw text.
All content is rendered as text, never HTML. Reading does not send, acknowledge,
write records, or update model context automatically.

Errors and truncation are retained per source in context while successful records from other
channels remain visible. Successful nonempty loads show no redundant status, count,
range or last-success label. Successful empty reads show `No messages in this date range.`;
failures never masquerade as empty success. Missing sides/truncation remain in context.
Completeness applies only
to accessible channels in the applied range, not all history or data outside share
permissions (including time-limited grants). Narrow the dates for truncated results.

Keyed thread rows preserve keyboard focus; Back to threads returns focus to the
selected row (or Refresh threads if it disappeared). Keyed messages preserve the
visible message and its pixel offset while reading history, with **New activity**
to jump to the latest edge in either order. Already-latest readers follow incoming
content, except when focusing thread controls. Refresh retains
focus, open disclosures and pending attachment state; navigation invalidates old reads
and composers. Late responses cannot replace the current peer view.

Discovery failure retains last-good displayed data with stale/unverified metadata
and original provenance internally and in context. Previously loaded context remains sendable, including
a successfully loaded empty thread; the preview and sent payload include stale and
incomplete warnings. Discovery failure reads no cached channels. A message-source
failure retains only that source's last-good
records from the same range, marked stale with source identity and last-success
time in bounded context. The reading view uses the concise retry status above, not
technical errors, source IDs, counts, ranges or diagnostic timestamps.
This is a presentation change, not a claim that retained records are current.
Other successful sources refresh normally.
Successful discovery removes revoked sources immediately, even if subsequent
reads fail; a disappeared peer has no sendable cached context. Load messages or
Refresh threads retries. Invite remains independent.
The host decides whether app-originated calls appear in its conversation UI;
the app does not depend on those traces for first-load or failure feedback.

## Shared composer and direct sending (resource v26)

Both the global app and conversation panel use a two-row composer labeled
`Talk to <thread identifier>` and a primary **Send** button. Send calls the
model/app-visible `mesh_send` tool directly on the same authenticated server:
no `ui/message`, sampling, LLM relay, new outbox or share is involved.

The tool accepts exact `peer_userid`, owned `outbox`, case-sensitive `peer_agent`,
`body` and fresh UUID `mid`, with v1 `kind`, `pri` and `slug` defaults. The request's
OAuth credentials supply the sender account; there is no account override.
Before writing it verifies an active, recordable, own MomentAnnotation Mesh Outbox
and all covering outgoing grants, including account-wide and base-type selectors.
Exactly one unbounded, single-channel, single-peer direct grant is required;
groups, files, extra recipients/types, broad or ambiguous grants are refused.
It rechecks grants and account identity immediately before the write. It never
creates or repairs sharing. Generic lower-level writes are not a retry fallback.

The tool adapts Hermes' native mesh send operation: the same eight-key v1 envelope
is JSON-serialized in `note`, written with the moment annotation source, then read
back independently. `posted` proves the exact envelope is query-visible in the own
outbox, not delivery or acknowledgement. `rejected` means nothing submitted;
`uncertain` means the write may have occurred and must be reconciled by `mid`,
without automatic resend. A matching ID in the preceding seven days is read back
rather than written again; this is not atomic distributed idempotency. Concurrent
external clients and grant changes cannot be made transactional by these APIs.

The sole outgoing source is selected automatically; with several, choose an exact
outbox in **Delivery address**. A unique recipient agent from displayed own
outgoing envelopes for that exact peer/source is reused. Otherwise enter the exact
name in Delivery address; no label, incoming sender claim or wildcard is substituted.
Native Hermes receive requires exact `to_user` and case-sensitive `to=local_agent`;
a compatible envelope is discoverable from incoming shares without sender LLM history.
Unknown agent names therefore remain a user setup step, not a guessed default.

Each explicit Send immediately displays an optimistic outgoing row with a muted
`sending…` badge. Pending guards span navigation. Failures retain the draft;
uncertain posts show `unconfirmed` and pause further direct sends for that peer
until exact source-qualified polling reconciles them. No automatic retry is made.
Readback/polling success clears only the original, unchanged draft version, never
another peer or newer composition. Rows reconcile against full envelopes plus
owner/type identity, not message IDs alone. Local posts remain visible until
polled even if they fall outside the applied history dates; their state is included
in the displayed context. Drafts and pending state are app-memory-only and lost on
closure, so inspect the outbox before retrying after reopening an uncertain send.

The separate secondary button is exactly **talk with my agent about this thread**.
It attaches the bounded current displayed context, awaits host acknowledgement,
revalidates navigation/context identity, then sends the optional exact composition
as a user-role host-chat message. A blank composition sends only
“Let’s talk about this mesh thread.” Both host `message.text` and
`updateModelContext.text` capabilities are required for this secondary path, not
for direct Send. Host acceptance is not mesh posting or completion of an agent task.
No PiP transition, native composer focus, or conversation expansion is guaranteed.

The reusable `web/thread-context.js` builder preserves exact peer ID, applied
range, warnings, completeness, displayed/omitted counts and each displayed
record's source owner/type and direction. Historical bodies are quoted untrusted
reference data, not instructions. The preview shows the exact attachment text.
Its 24,000 UTF-16-code-unit bound includes label and metadata and retains whole
records in displayed order. Clipping is disclosed; oversized metadata disables
only handoff. Stale or empty previously loaded context remains usable; revoked
sources are removed. No unrelated peer or undisplayed history is attached.

One app-wide serialized context queue orders attaches and empty-content clears.
Navigation, revocation and changed displayed records/range/order/warnings invalidate
attachments. A late attach drains before cleanup and cannot send after invalidation.
Unchanged polls do not reattach or clear merely because freshness advanced. Clear
failures stay visible; teardown awaits cleanup, but transport loss cannot retract
already consumed context. Send feedback remains separate from cleanup feedback.

`web/direct-send.spec.js` covers direct writes, optimistic reconciliation, duplicate
click/navigation protection, uncertain recovery and optional/blank handoff with the
real SDK and synthetic data. Existing native-context, thread, polling and layout
suites cover bounded context, capability gates, stale/revoked sources and host races.
Python tests cover authorization, all covering grants, exact readback and per-user
HTTP OAuth isolation. Live ChatGPT and backend ingestion latency remain unverified.

## Thread entrypoint: Mesh conversation (resource v26)

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

The tool advertises `ui://fulcra/mesh/thread/v26.html`. Its resource serves the
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

The panel uses the same direct Send and secondary chat handoff described above.
Host-message acceptance clears only the unchanged originating draft, even after
navigation. A user-role bridge message does not establish native user authorship
or override consent. Check the host conversation before retrying uncertain handoffs.

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
a transport timeout. Direct mesh writes are separate; acknowledgements are never automatic.

Capture synthetic thread-composer screenshots at 1120px and 320px:

```sh
cd web
THREAD_PREVIEW_DIR=/home/fulcra/.hermes/cache/scratch npx playwright test thread-entrypoint.spec.js -g 'thread presentation layout'
```

Outputs are `mesh-thread-1120.png` and `mesh-thread-320.png` in that directory.
These are scrolled, fixed-height synthetic iframe previews, not ChatGPT screenshots;
they check the small textarea, suggestion controls and horizontal fit, not real-host
autoResize or overlay behavior.

## Inline Mesh threads (resource v26)

`mesh_threads_open({})`, titled **Mesh threads**, is read-only and visible to model
and app. It returns `{presentation: "threads"}` without accessing an account. Its
resource `ui://fulcra/mesh/threads/v26.html` serves the same compiled HTML with a
fixed `mesh-presentation="threads"` meta marker. Resource metadata prefers `inline`
and advertises `["inline", "fullscreen"]`, matching this presentation's app
capabilities. Inline is a display mode, not an invented entrypoint type. Existing
global/thread entrypoint metadata and controls are unchanged.

The compact list uses the existing authorized exact-peer discovery and keyed rows.
Initial-result and host-context handlers are registered before connection; initial
results arriving before or after initialization are consumed without recalling the
opener. Refresh/polling and first-load/failure feedback remain shared. No messages or
composer are mounted until an explicit row selection has host panel acceptance.

A row click requests fullscreen once only if the host advertises it, or directly
selects when already fullscreen. The returned mode is authoritative, not the
request. Denial, unsupported mode and errors retain the list with honest status;
there is no message-send fallback, model turn, sampling or write on opening.
Pending requests are serialized. Late responses after teardown, host inline return,
or removal/replacement of the exact authorized peer row cannot select a thread.
The accepted panel reuses the shared message view, direct-send composer and
capability-gated suggestions. Back may
stay fullscreen. Host inline return clears selection and invalidates attached or
pending context through the existing shared lifecycle before any pending send.
Timeouts cannot retract a host display transition; late responses never select an
old peer, and opening a peer still requires an explicit click.

`web/inline-threads.spec.js` tests the real SDK in a synthetic sandbox host,
including 320/1120px lists and panels, early/late initialization, denial/error,
revocation, teardown, duplicate clicks and context cleanup. Capture previews with
`INLINE_PREVIEW_DIR=/home/fulcra/.hermes/cache/scratch npm run test:browser` from
`web/`: `mesh-inline-320.png`, `mesh-inline-1120.png`, and corresponding
`mesh-inline-panel-320.png` / `mesh-inline-panel-1120.png`. These are synthetic
Chromium previews, not live ChatGPT acceptance. Host preferences remain hints;
actual host rendering and autoResize require operator acceptance.

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
- `fulcra_mcp/mesh.py`: native v1 envelope write authorization and readback.
- `web/thread-actions.js`, `mesh-send.js`, `reply-suggestions.js`: shared direct
  sends, source-qualified reconciliation, chat handoff and explicit suggestions.
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
agent to use `fulcra-mesh` to show a copyable invitation first, using the connected
user's verified ID and the mesh skill URL—not to ask for the other user's ID.
It then offers optional recipient/purpose context to personalize the invitation,
prepare an authorized unshared outbox and draft a first message. No sharing or
posting until peer identity is verified and the user authorizes it. The plugin's
0.2.5 mesh skill owns this workflow; the button does not create data or invites.
Test the actual model response in a fresh chat:
copyable prompt before optional questions, no recipient-ID prerequisite, no writes
on a generic invite request. Synthetic SDK tests verify only the button payload.
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
In both entrypoints, verify that Send calls only `mesh_send`, shows a sending row,
and reconciles readback without an LLM turn. Verify the secondary chat handoff
with a composition and with a blank draft, including bounded context attachment.
Separately open Mesh conversation as a thread tab with `{}` and through a model
reference to an exact peer ID. Verify the shared controls, capability notices,
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

List tools, call `aicq_open` with `{}`, and read `ui://fulcra/mesh/v26.html`.
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
