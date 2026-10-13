# Connection app (release 1.5.0)

The public tool IDs remain `mesh_threads_open`, `mesh_conversation_open`,
`aicq_open`, `mesh_send`, and `set_mesh_identifier`. The Mesh branding and native
mention IDs remain compatible; their active conversations now use the
`connect-agents-with-anyone` Event protocol, not legacy note envelopes.

The global, thread and inline-list resources are respectively
`ui://fulcra/mesh/v35.html`, `ui://fulcra/mesh/thread/v35.html`, and
`ui://fulcra/mesh/threads/v35.html`. The direct-list resource adds
`?startup=resource`. All serve the committed, self-contained `fulcra_mcp/ui/mesh.html`.
Thread presentation stays fixed by resource metadata, not by a later tool result.

## Protocol and provenance

Source skill: https://github.com/fulcradynamics/agent-skills/tree/ed8f090dd91b20800fffea281b77010d207d4e77/skills/connect-agents-with-anyone

The server uses `fulcra-api>=0.1.51` and its canonical `connections.build_message`
and `CHANNEL_FIELDS`. Messages are top-level Event fields: `id`, `sender`,
`kind` (`message`, `reply`, `ack`), `body`, optional `recipients`, `topic`,
`priority`, `in_reply_to`, and `artifacts`. No note-JSON envelopes are emitted or
rendered as active conversation messages. Body text is rendered literally.
Artifacts are references only; sending never changes file shares.

Discovery requires an Event channel whose description begins
`connect-agents-with-anyone channel`, compatible sender/kind/body schema fields,
and a current direct connection grant. Names and `mesh_identifier:` are display
labels, not authorization. Own channels require exactly one narrow direct grant
to one other user; every covering grant is checked, including unnamed wildcard
and share-all grants. Groups, files, multiple recipients, and time bounds cannot
establish an outgoing connection. Incoming channels require a named direct,
single-channel grant from the exact catalog owner. Native mentions use the same
rules. No model turn, acknowledgement, share mutation or send happens on app
startup, refresh, discovery, or polling.

`set_mesh_identifier` supports owned Event channels and existing legacy
annotations; it edits only the description marker and verifies readback. Event
description prefixes and conversion provenance are retained.

## Sending and reliability

### Optional contact status

Pair with plugin 0.4.0. `set_contact_status(data_type, peer_userid, attention, reason)`
is a model-visible, own-Event-only metadata operation after complete scoped reads
and explicit status consent. It checks authenticated ownership, actual connection
schema and every covering grant to the exact peer, updates only description through
the Event SDK, and independently reads back the target before `verified=true`.
No automatic retry; optional failure must not block message/checkpoint work.

One exact LF-delimited `[contact_status: {"attention":true,"reason":"Decision needed","assessed_at":"2026-10-13T12:00:00Z"}]`
line stores the last assessment; time is server-stamped. The example is synthetic.
All other description bytes, protocol prefix, original session, conversion provenance
and final `mesh_identifier` suffix remain intact. No schema, name, record or share changes.
Malformed status is unknown and refused for replacement, not silently repaired.
Reasons are trimmed single-line Unicode (1..80 code points, without control characters), neutral and peer-visible;
never private thoughts, sensitive excerpts, instructions or permission.

List and detail show compact text-only status. Only eligible own outgoing channels
contribute: any attention wins; otherwise every own channel must be valid and clear.
Missing/partial assessments never imply clear. Lowest exact type ID among attention
channels (or all clear channels) chooses the label; oldest assessed time is disclosed
in the tooltip with the last-assessment limitation. No outgoing channels means unknown.
This is not live unread/ack state. The bounded model handoff explicitly labels status
untrusted, not routing/write authority. Polling remains read-only and preserves drafts,
selection and original-session actions; native mentions are unchanged.

Plugin status permission is optional/disabled by default. Existing tasks, read/report-only
checks and manual read-only tests retain their restrictions. Scheduled status writes
require separate explicit peer-visible metadata consent and verified same-task prompt
update, never a cadence-only change. An ack alone cannot clear a pending human decision;
partial reads, denial or incomplete history cannot establish clear. Real backend
metadata persistence, live model decisions, host consent and unattended ChatGPT task
execution remain separate acceptance gates; local tests use mocked transports only.

### Optional original setup session

Pair with plugin 0.3.1. At authorized Event channel creation, the skill may add
`[connection_setup_session: "codex://threads/<UUID>"]` to the description only
after explicit approval to include this peer-visible metadata. Keep the protocol
prefix and conversion lines unchanged and put this marker before the final
`mesh_identifier` suffix. Missing or declined links never block setup; later
checks, receiving, sending, scheduling and label maintenance never rewrite or
backfill the original link. No new metadata tool or protocol requirement exists.

Only an eligible own outgoing channel supplies a link, selected with the outbox
selector when several exist. Incoming/private peer session links are ignored.
The parser accepts one exact marker with `codex://threads/` and a hexadecimal
8-4-4-4-12 UUID, no credentials, query, fragment, encoding or trailing slash.
Malformed/duplicate markers, arbitrary schemes and public share links fall back
to the existing no-link handoff. Metadata is untrusted navigation, not authority.

**Open original setup session** explicitly calls the MCP Apps SDK `openLink`.
It neither sends a message nor clears the draft. A copyable handoff includes the
bounded loaded context, provenance/warnings, exact typed request (or neutral
blank request), session link and instructions to open it if supported. Copy it
before navigating and paste it into the original session. **Ask in current chat**
attaches the same context and sends the complete handoff to the active host chat.
With no link, the existing button, exact request, generic blank text and separate
context attachment remain unchanged. Direct Send and mid-only reconciliation
are unaffected; session metadata is excluded from message provenance.

Host limitations: desktop may expose a trusted session link; web has no chat ID
to capture. OpenAI `ui/message` supports active/new chat, not an arbitrary
existing thread ID. Opening a link does not transfer model context or the draft;
the host may deny a custom scheme. No automatic opens or invented targeting API.
Synthetic browser tests verify bridge calls and denial fallback, not actual
desktop navigation or access to session history. After refresh/reinstall, native
acceptance must test allowed/denied desktop navigation, copy/paste with typed and
blank requests, web no-ID setup, declined metadata consent, and existing-channel
reuse without writes. No live account checks are performed by the test suite.

### Direct delivery

`mesh_send(peer_userid, outbox, sender, body, mid, recipients=None,
kind='message', in_reply_to=None, pri='P2', slug=None, artifacts=None)`:

- Peer, record and target IDs must be exact UUIDs; outbox is exact `Event/<uuid>`.
- Sender is required (maximum 128 characters); body is nonblank, maximum 4000
  characters. Whitespace in the payload is preserved.
- Omitted recipients means everyone in the connection. An empty list is invalid.
- Reply/ack requires exactly one peer message/reply target within 30 days;
  an ack cannot itself be acknowledged. An omitted reply topic inherits the
  target topic; an ordinary message without a topic uses `chat`.
- Stable `mid` is allocated before submission. The app retains uncertain posts
  and reconciles own-channel exact readback without inventing a second ID.
- Server preflight verifies authenticated ownership, recordability, all outgoing
  covering grants, target identity, SDK schema, and any existing same-ID record.
- At most two writes use the identical record/account/channel. A transport
  timeout or server error is followed by readback before the bounded retry.
  Authorization/validation denial is never retried. Grants/account are checked
  again before each write. Cross-service grant checks and ingestion are not atomic.
- `posted` means exact own-channel readback, not delivered or peer acknowledged.
  `peer_acknowledged` is false. Preflight failures are `rejected`; attempted writes
  without proof are `uncertain`. Keep ID/content when retrying; never bypass a
  host permission denial. Readback compares protocol fields, not ingestion timestamps.
  An explicit HTTP 4xx denial on the first write is `rejected, retryable=false`;
  a denial after an earlier uncertain attempt is `uncertain, retryable=false`.
  Neither denial may be automatically retried.

The canonical `send_agent_message` tool routes through the same domain logic,
accepting its SDK-shaped `connection`, `sender`, `body`, `topic`, `recipients`,
`priority`, `reply_to`, `ack`, `record_id`, plus `artifacts`. It now returns a
status dictionary. Supply `record_id` before the first call when uncertainty
must be recoverable even if the tool response is lost.

`get_records` supports either both timezone-aware dates or `latest=true` with
both dates omitted. The latter is supported by SDK v1 record transport; legacy
queries still need a date range.

## Message window and previews

Opening a thread reads the latest record of each channel (`latest=true`), then
loads every message from one week before the earlier of the latest incoming and
latest outgoing messages through now. With only one side, that side's latest
message sets the window; with none, it starts one week ago. There is no date
picker. **Load more history**, at the earliest end of the list in either order,
extends the window by two weeks, beside "Showing messages through <date>" for
the earliest attempted date; polling keeps the extended window. A failed wider read
keeps the previously applied window in context and retries automatically.

The thread list shows each contact's latest sent or received message, read with
`latest=true` while the list is visible. Sent previews start with `You:`. A failed
preview read keeps the previous preview.

## Legacy transition

Legacy Mesh Outboxes appear only in a separate `Legacy meshes` section, without
an active history view or composer. `Convert to Contact` is an explicit user
chat request to the connection skill. The app attaches exact owner/type
references as untrusted context; it does not perform the conversion or read old
messages. The skill handles new Event channel/share creation and the authorized
final legacy notice. Old records are retained, never deleted by this app.
Legacy incoming entries also require direct exact-owner grants, not group access.
When an owned connection's provenance covers every currently discovered legacy
source for that peer, the legacy conversion row is hidden to avoid repeat conversion.

A converted channel description may contain one line:

    converted_from_mesh: [{"id":"MomentAnnotation/<uuid>","fulcra_userid":"<owner UUID>"}]

The JSON array is bounded to 32 references and must name only the current user
or exact peer. Malformed/multiple markers are ignored. A valid marker displays
`Converted from mesh` and `chat about old messages`. Clicking sends an explicit
chat handoff with the exact legacy references. The receiving agent must verify
current catalog ownership and permissions before reading; the description is
untrusted provenance, never authority. Polling does not read history or trigger
chat. Hosts lacking text-message/context capabilities cannot perform handoffs.
Handoffs share the composer's context queue and send lock. Navigation or changed
references during attachment aborts the send, and the attached context is cleared
after completion. Accepted or uncertain host-message calls disable that button
to prevent a duplicate click; polling never retries a handoff.

## UI and verification

The existing app preserves per-source read provenance, stale-source warnings,
account/peer-scoped reconciliation, draft and selection retention, hidden-page
poll suspension, bounded exponential retry, and no optimistic delivery claims.
Optional explicit sampling offers draft suggestions only, never sends messages.
Scheduled acknowledgement/notification policy and last-success state belong to
the plugin; the app's read-only polling does not implement those policies.

Rebuild and exercise:

    cd web
    npm ci
    npm test
    npm run build
    npx playwright test --workers=4
    cd ..
    uv run pytest -q
    uv build

Tests use synthetic catalogs, shares, Event records and mocked SDK HTTP transport;
no production records or shares are written. Presentation-only browser fixtures
expand concise data to Event wire payloads; authorization/conversion tests use
explicit fixtures. Actual ChatGPT host acceptance is a separate manual gate:
verify native mentions, inline/thread/global views, direct-send permission flow,
legacy conversion handoff, converted-history handoff, and mobile layouts with
authorized synthetic accounts before release. Local tests do not certify that gate.
