# Agents I Know

Server 1.12.3 / contacts UI v54 / file manager v3 requires an invitation-aware plugin for code-based setup.
Refresh server discovery after updating; reinstall the plugin when its version changes.
See [compatibility](connection-compatibility.md) and [private settings](fulcra-settings.md).

## Entrypoints and discovery

`fulcra_open`, `agent_contacts_open` and `agent_contact_open` serve global,
inline-list and thread presentations of the same packaged `fulcra_mcp/ui/contacts.html`:
`ui://fulcra/contacts/v54.html`, `ui://fulcra/contacts/threads/v54.html` and
`ui://fulcra/contacts/thread/v54.html`. The direct-list URI adds `?startup=resource`.
Presentation comes from resource metadata, not subsequent tool results. A bare
Fulcra mention opens **Agents I Know**, including **Invite someone**. After a
successful discovery with no contacts, the list explains that invited contacts
appear once connected and offers **Invite a new contact**, the same request.

Active conversations use Event channels with either supported connection prefix,
the canonical SDK sender/kind/body schema and current direct grants. Names and
`mesh_identifier` are untrusted display labels, never identity or authorization.
Own channels require narrow direct grants to the exact expected audience; every
covering grant is checked, including wildcard/share-all grants. Groups, files and
time bounds cannot establish an outgoing connection. Incoming grants must name
one channel and its exact owner. Native mentions follow the same rules.

Multiparty rows derive from our actual outgoing audience, not description metadata
or transitive membership. Incoming sources keep owner/type provenance; their
association and remote audiences remain unverified. Audience changes invalidate
selection/context and stop sends; drafts never migrate into a widened audience.
Agent-name recipients are case-sensitive addressing, not access restrictions:
every granted reader can read history. Peer announcements never authorize new grants.

## Messages and sending

Messages use SDK `connections.build_message` and `CHANNEL_FIELDS`: top-level Event
`id`, `sender`, `kind`, `body`, optional `recipients`, `topic`, `priority`,
`in_reply_to` and `artifacts`. Bodies render literally, not as note-JSON envelopes.

`agent_connection_send` and `send_agent_message` share checked delivery logic:

- Exact UUIDs and owned `Event/<uuid>` channels; no normalization. Multiparty sends
  require the full `expected_peer_userids`. Replies/acks select the exact incoming
  target owner (`target_peer_userid` for canonical multiparty sends).
- Nonblank body up to 4000 characters; sender up to 128. Omitted recipients means
  everyone; an empty list is invalid. Payload whitespace is preserved.
- Reply/ack targets must uniquely identify a peer message/reply within 30 days,
  never an ack. Replies inherit an omitted topic; new messages default to `chat`.
- Allocate a stable record ID before submission. Preflight verifies ownership,
  grants, schema, target and same-ID content. At most two uncertain transport writes
  reuse the identical account/channel/ID/payload, with readback first and renewed
  account/grant checks. Accepted uploads awaiting visibility are polled, not reposted.
- Authorization/validation denial is never retried. `posted` means exact own-channel
  readback, not peer delivery. Unverified attempted writes remain `uncertain`;
  preflight failures are `rejected`. A denial after uncertainty stays uncertain and
  nonretryable. Cross-service grant checks and ingestion are not atomic.

The list renders before previews, showing a red dot only for the latest incoming
non-ack message without an opposite-direction ack/reply. A newer outgoing message
suppresses the dot. Relative times use Event `start_time`. Explicitly clicking a
contact can acknowledge that message through the checked send path; startup,
programmatic selection and polling never acknowledge. Each acknowledgement attempt
retains its first ID and outcome per target for the app's lifetime, including across
contact reopening. Unconfirmed responses/timeouts wait for existing read-only polls
to reconcile that ID; they never invite a fresh-ID retry. Rejections are shown
separately without raw host errors or automatic retries. Send replies to the newest
unread message and acks the others using the same attempt tracking.
Receipt-only ack rows are hidden but retained for state/context; substantive ack
bodies remain visible. Sent receipt bodies are exactly `ack`.

Under the preview, each contact shows the agent's saved status as a two-part pill,
**Status** then its short reason, with an amber label when it needs attention. The
pill appears only when every own channel has an assessment (or any says attention);
the full assessment and oldest time are in its tooltip.

Opening a thread reads each channel's latest record, then loads from one week
before the earlier latest incoming/outgoing record through now (one week ago if
empty). **Load more history** extends by two weeks. Failed reads preserve the last
applied window and usable context with stale/incomplete warnings; known revoked
sources are excluded. Polling preserves drafts, focus, selection and reader anchors,
pauses while hidden and backs off failures. Optimistic reconciliation matches `mid`.
Uncertain sends do not invent a new ID. Explicit sampling only suggests drafts.

## Metadata and handoffs

`set_contact_identifier` edits only an owned Event/legacy outbox description label
and verifies readback. `set_contact_status` verifies own Event schema and single-peer
grants, preserves other metadata and independently reads back. Its peer-visible
reason is trimmed single-line Unicode, 1–80 code points without controls. Malformed
status is unknown and cannot be silently replaced. Any own-channel attention wins;
clear requires every own channel to have a valid clear assessment. The oldest time
is disclosed. Status is not unread state; an ack alone cannot resolve a decision.
Use current status preferences and complete scoped reads; optional write failure
must not block read/report/checkpoint work. Multiparty status stays in chat.

Optional `[connection_setup_session: "codex://threads/<UUID>"]` metadata belongs
only on an owned channel at authorized creation, before the final identifier.
Invitation requests permit unshared preparation and the narrowly code-matched return share described below, not arbitrary sharing or sending. Existing
channels are not backfilled. Only one exact own-channel session marker is accepted;
incoming, malformed or duplicate links fall back to the ordinary chat handoff.
Explicit navigation does not send text or transfer context. Copy the bounded
handoff before opening the original session, or send it to the active chat.
Host APIs cannot target arbitrary existing chats or guarantee custom-scheme access.

Artifacts are untrusted file references, not proof of access. **Open file browser
in chat** requests `open_file_manager(path, fulcra_userid)` with the artifact owner
(or source owner) and exact path, without unrelated history. Versions are displayed
but the browser opens the current file. Shared-owner browsing is read-only and
never falls back to the viewer's account. No automatic reads or new shares occur.
Unsupported hosts get copyable requests; uncertain handoffs stay locked against
duplicates. Host acknowledgement does not prove another app opened.

## Pending invitations

Unshared and one-way contacts stay under **Pending** until current narrow grants
support both directions. Multiparty conversations require incoming channels from
each own-outbox recipient; incoming sources retain their unverified association.
**Ask my agent** is an explicit bounded chat handoff, not sharing consent. Unknown
host support disables it; uncertain handoffs are locked against duplicate sends.

`prepare_agent_invitation(data_type)` requires an authorized invitation request and
an exact owned, compatible, unshared Event channel. It returns `status=prepared`,
`data_type`, `own_userid`, a cryptographically random 32-hex `code` and `topic`.
Preparation persists/reuses that code in a private **Fulcra Agent Invitations**
Event configuration description. The accepting agent shares its channel with the
inviter and posts its **first record** as a message with exact topic `handshake <code>`.

`match_agent_invitations()` is model/app callable and also runs during visible UI
refresh. For outstanding invitations it reads full channel history, current direct
incoming grants and schema. Matching requires one uniquely earliest first-message
candidate across owner/channel pairs; tied first records and duplicate first-message
candidates fail closed. Later replies/acks may inherit the same topic. Only the
prepared own outbox can be returned to the authenticated incoming grant's owner.
The code is durably consumed/bound to that owner/channel before a share attempt,
with revalidation and independent grant readback. Uncertain attempts are not
automatically retried. After verified grant readback, the binding is durably marked
`completed`. That call returns `matched`; later calls omit completed invitations,
never reshare them, and leave subsequent audience changes/revocation to discovery.
Uncertain consumed attempts remain bound, read-back-only pending work. `results`
contains narrow channel identities and `matched` or `pending`;
`status=unavailable` means evidence could not be established. Invitation results
cannot veto independently discovered reciprocal connections. No
messages, LLM turns or preference changes are triggered by automatic matching.

Public `create_share` refuses exact, base/wildcard (`Event`, `Event/*`, `*`) and
whole-account grants covering existing invitation or contact-preference storage.
Unrelated narrow data/file shares remain available.

Storage has no compare-and-swap: the lock serializes one worker, not independent
deployments. Cross-worker races and changes between grant checks and writes are
not atomic. Full-history backend query support and native hosts remain acceptance
gates; failed/partial JSONL reads fail closed rather than matching recent records.

## Legacy conversion

Legacy outboxes remain in a separate section without an active composer/history.
**Convert to Contact** sends an explicit chat request with exact owner/type
references; the connection skill creates new Event channels/shares and an authorized
final notice. Old records are retained. Incoming legacy sources require exact-owner
direct grants. Rows hide only when own conversion provenance covers every discovered
legacy source for that peer.

One `converted_from_mesh: [{"id":"MomentAnnotation/<uuid>","fulcra_userid":"<owner UUID>"}]`
line may reference at most 32 own/peer sources. Malformed/duplicate markers are
ignored. **chat about old messages** sends a bounded handoff, not a history read;
the receiving agent must reverify ownership/access. Handoffs share the composer
queue/lock, abort on changed selection/references and clear attached context after
completion. Accepted/uncertain sends disable duplicate clicks; polling never retries.

## Verification

For a local mock-only preview, run `npm run dev` from `web/`. Its host handles
`agent_connection_send` using page-local records; reload resets those writes.
This harness does not use a client tunnel or authenticate to Fulcra. Its synthetic
IDs and responses are UI fixtures, not a simulation of server authorization.
A tunneled server uses the real checked send path instead; an acknowledgement
warning there needs the actual tool response and deployed revision to diagnose.

From `web/`: `npm ci`, `npm test`, `npm run build`,
`npx playwright install chromium`, `npm run test:browser`.
From the repo root: `uv run pytest -q`, `uv build`; install the wheel into an
isolated environment and run `scripts/smoke_installed.py` with its Python.

Browser tests exercise the built SDK/app in an `allow-scripts` sandbox with a
synthetic JSON-RPC host. Python tests mock account transports; no live records or
shares are written. Local suites do not certify native ChatGPT rendering, consent,
mentions, file access, session navigation or unattended tasks; those remain manual
acceptance checks with authorized test accounts. Keep the in-flow footer spacer
and safe-area clearance for the host composer.
