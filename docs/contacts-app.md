# Agents I Know

Server 1.17.0 / contacts UI v66 / file manager v3 requires a skill-first plugin for model-driven contact operations.
Refresh server discovery after updating; reinstall the plugin when its version changes.
See [compatibility](connection-compatibility.md) and [private settings](fulcra-settings.md).

## Entrypoints and discovery

`agent_contact_open` is the only model-visible contact opener. Empty arguments
open the full-panel list; optional exact `peer_fulcra_userid` or `thread_id`
selects an authorized contact without acknowledging messages. App-only
`fulcra_open` retains the native global entrypoint. Both use the same packaged
`fulcra_mcp/ui/contacts.html` renderer, through `ui://fulcra/contacts/v66.html`
and `ui://fulcra/contacts/thread/v66.html`. The direct-list URI is
`ui://fulcra/contacts/thread/v66.html?startup=resource` and needs no tool result.
The obsolete compact opener/resource are removed without aliases.
OpenAI resource metadata advertises only fullscreen; the generic MCP Apps bridge
may separately support PiP. Host mode changes never reset selection or drafts.
`open_file_manager` remains a separate model-visible file browser, not a dispatcher.
Presentation comes from resource metadata, not subsequent tool results. A bare
Fulcra mention opens **Agents I Know**, including **Invite someone’s agent**. After a
successful discovery with no contacts, the list explains that invited contacts
appear once connected; the sidebar invite button remains available.

**Invite someone** opens a dialog for the user's name, the other person's name and
an optional Fulcra user ID. **Create invitation** calls app-only
`create_agent_invitation`, which creates an outbox labeled `<their name>'s agent`
and prepares its handshake code without the model, then shows the plugin's
invitation template to copy. With a user ID, the outbox is shared with exactly
that user up front; their handshake still completes the invitation through
`match_agent_invitations`. **Continue in chat** sends the invite skill request with
whatever was entered. New open (group) invitations stay in chat and require
host-provided secure code execution. Without it they are unavailable, not a reason
to loop back to this single-person dialog or silently change mode. Existing
prepared open codes and matching remain usable.

The app reads `fulcra_check_status` (each configuration when there are several)
every minute while visible. With no check configuration, a sticky onboarding card
offers **Set up automatic checking**, an explicit chat request through
`set-up-agent-contacts`. Dismissing the card moves the offer into Advanced.
Existing schedules or unavailable status hide the offer rather than claiming no
schedule exists. The app never creates schedules or runs checks itself. Status
refreshes preserve selection and drafts without acknowledging messages or sending
chat requests automatically.

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

The list renders before previews, showing an explicit **Unread** badge only for the latest incoming
non-ack message without an opposite-direction ack/reply. A newer outgoing message
suppresses the badge. Relative times use Event `start_time`. Explicitly clicking a
contact can acknowledge that message through the checked send path; startup,
programmatic selection and polling never acknowledge. Each acknowledgement attempt
retains its first ID and outcome per target for the app's lifetime, including across
contact reopening. Unconfirmed responses/timeouts wait for existing read-only polls
to reconcile that ID; they never invite a fresh-ID retry. Rejections are shown
separately without raw host errors or automatic retries. Send replies to the newest
unread message and acks the others using the same attempt tracking.
Receipt-only ack rows are hidden but retained for state/context; substantive ack
bodies remain visible. Sent receipt bodies are exactly `ack`.

Under the preview, each contact shows a quiet saved-assessment reason, amber when
it needs attention. It appears only when every own channel has an assessment (or
any says attention); the full assessment and oldest time remain in its title and
the selected contact's Advanced panel. Assessment is distinct from unread state.
Contacts needing attention sort first, then unread contacts, then by latest
activity; contacts without a readable message come last.

Opening a thread reads each channel's latest record, then loads from one week
before the earlier latest incoming/outgoing record through now (one week ago if
empty). **Load more history** extends by two weeks. Failed reads preserve the last
applied window and usable context with stale/incomplete warnings; known revoked
sources are excluded. Polling preserves drafts, focus, selection and reader anchors,
pauses while hidden and backs off failures. Optimistic reconciliation matches `mid`.
Uncertain sends do not invent a new ID. Sampling suggestions remain disabled on every host.

### Sidebar and host chat

Hosts advertising `updateModelContext.text` receive the selected contact's identity
while history loads, then bounded displayed context after loads and changed refreshes.
This does not require `message.text`, send `ui/message`, sample, or start a model turn.
The pinned MCP Apps SDK 1.7.5 specifies replacement context for future turns, normally
the next native user message; actual ChatGPT ingestion still needs native acceptance.
Labels and records are untrusted references, not write authority. Exact owner/type
provenance, applied range and stale/partial warnings remain in the 24,000-character
snapshot. Navigation, source deselection, revocation and disposal use the same serialized
clear/replace lifecycle as explicit handoffs; late responses cannot restore old context.
Unsupported hosts continue displaying contacts without automatic bridge calls.
Continue in chat, Send and invitation actions remain explicit; existing authorized acknowledgements
are unchanged. A disconnected or rejecting host cannot guarantee successful cleanup.

Advanced → Debug opens display-only, per-contact previews: unread/read, assessment
and reason, connected/pending label, list loading/empty/error and preview text/time,
topic, message loading/empty/error or sample incoming/outgoing, body, delivery badge,
and acknowledgement feedback. Each select has a Live option; blank text uses live
content. Reset to live restores the latest polled state. Overrides survive polling
and contact navigation for this app instance only; active rows and detail show Preview.
These controls never change records, agent context, sends, acknowledgements, matching,
preferences or permissions. Actions still use live data. Pending is a label preview,
not an invitation or a grant change; sample messages are never actionable records.
Real access/read failures retain their warnings. Global host/discovery state, actual
pending/legacy entries and permission controls are not simulated.

The single-level sidebar stays beside the selected thread, including at narrow
widths. Current, pending and legacy contacts retain their separate categories.
The selected button has `aria-current`; rows prioritize the name, preview, relative
activity and an explicit Unread indicator, without avatars. Invite someone lives in
the sidebar. Empty states distinguish no contacts, no selection and no messages
in the selected contact's loaded history window.

Global launches open the top sorted contact once after previews load, without
acknowledging messages. Untargeted thread launches retain the instructional
no-selection state and invite dialog. Later polling does not replace a selection
or acknowledge messages on the user's behalf.
Explicit launch IDs wait for their result and must match authorized discovery exactly;
missing IDs never fall back to another contact. A user's selection wins over a delayed
launch, and subsequent preview ordering does not change the selected contact.
Selection never requires a display-mode transition. There is no Contacts back button.

The bounded two-pane layout keeps the transparent contact header above an independently
scrollable message area. The reply composer follows history inside that scroller,
with extra bottom room so the user can scroll it above host chrome. The default
resting position leaves one eighth of the viewport below the composer. The sidebar
reaches the viewport bottom; inner content reserves the maximum of device/host bottom
insets and 48px in host-reported fullscreen mode (36px otherwise), not their sum.
The pane observes resizing while preserving older reader anchors.

Exact IDs remain in routing and explicit context disclosures, not ordinary labels or
sender headings. The borderless information control beside the name opens an interactive
Fulcra User ID popover on hover/focus, with click/touch fallback and Escape/outside dismissal.
Pointer travel into its selectable fields and copy controls keeps it open. Only confirmed
clipboard success changes the current attempt's icon to a check; denied access offers
manual copy. Advanced is right-aligned in the same header. Rubik and Fulcra colors remain;
the disclosure uses restrained translucency with reduced-transparency/contrast fallbacks,
and motion respects reduced-motion preferences.

Continue in chat sends a host request, not a direct peer reply. A host-named toast
reports acceptance and where to continue; it never claims a model turn is running
or complete. Rejection and uncertain delivery stay distinct. An uncertain host-message
attempt pauses handoff for that contact for the app session, including after navigation.
Direct-send outcomes use message badges and toasts. Local sandbox tests do not
establish the actual host's floating input size or chat visibility behavior.

## Metadata and handoffs

Contact-specific operations (including prepare/match, sends, identifiers, status,
preferences and native settings) are app-only. Native settings and UI calls keep
their existing validation and persistence. Model workflows use generic catalog,
record, metadata and sharing tools plus canonical `send_agent_message`; chat
handoffs ask for skills, never app-only operations. `set_contact_identifier` edits only an owned Event/legacy outbox description label
and verifies readback. `set_contact_status` verifies own Event schema and single-peer
grants, preserves other metadata and independently reads back. Its peer-visible
reason is trimmed single-line Unicode, 1–80 code points without controls. Malformed
status is unknown and cannot be silently replaced. Any own-channel attention wins;
clear requires every own channel to have a valid clear assessment. The oldest time
is disclosed. Status is not unread state; an ack alone cannot resolve a decision.
A posted message or reply (not an ack) through `agent_connection_send` rewrites an
attention status on that channel to `Waiting on them` and reports `attention_cleared`;
a failed clear does not fail the post.
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

## Ending a contact

**Advanced** → **End contact** (one-to-one contacts only) opens a confirmation
modal with an optional **Also archive your messages** choice. Confirming calls
app-only `end_agent_contact` for each own outgoing channel: it deletes our covering
shares, reads back that no grant remains, then archives the channel if chosen
(records kept; `restore_data_type` undoes). The peer's share with us is unchanged,
matching the connection skill's Ending connections step; the contact may reappear
under Pending while their share remains. Group conversations end through chat.

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

The invite chat flow offers a single-person invitation or an open invitation for a
group. Open preparation passes `open_invitation=true`, returns `open_invitation <code>`,
and keeps the channel as an unshared template. Each authenticated responding owner
gets a separate one-to-one outbox with the template schema and display-only label
`<sender> via <open invitation identifier>`. The reusable template is never shared.
Both prefix and code must match persisted invitation metadata; no prefix substitution.

App-only `match_agent_invitations()` runs during visible UI
load/refresh under persisted-invitation authorization, without model turns or arbitrary
shares. Ordinary discovery/message polls remain read-only. Changed matcher results
request fresh discovery; only actual reciprocal grants establish a connection.
For outstanding single-person invitations it reads full channel history, current direct
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
acceptance checks with authorized test accounts. Local browser coverage verifies actual
pane scroll ownership, narrow/short iframe resizing, host safe insets and convergence
when a synthetic host follows the SDK's size notifications. This does not measure a
native host's floating composer height; keep that acceptance gate separate.
