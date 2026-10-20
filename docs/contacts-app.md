# Agents I Know

**Agents I Know** is the MCP App that lists a user's agent contacts and shows each
conversation. It ships with this server as one bundle, `fulcra_mcp/ui/contacts.html`,
built from `web/`. Model-driven contact work (inviting, checking, replying) lives in
the paired OpenAI plugin's skills; see [compatibility](connection-compatibility.md)
and [private settings](fulcra-settings.md).

## Entrypoints

- `agent_contact_open` is the only model-visible opener. With no arguments it shows
  the full list; an exact `peer_fulcra_userid` or `thread_id` selects that contact.
  A bare Fulcra mention opens it.
- `fulcra_open` is the app-only native global entrypoint.
- Both serve `ui://fulcra/contacts/v<N>.html` (global) or
  `ui://fulcra/contacts/thread/v<N>.html` (thread); `?startup=resource` starts the
  thread resource without a tool result. `apps.py` holds the current `N`.
- `open_file_manager` is a separate file browser.

Presentation comes from resource metadata. OpenAI metadata advertises fullscreen
only; display-mode changes never reset selection or drafts.

Global launches open the top contact once previews load, without acknowledging
anything. Thread launches without a target show the instructional empty state.
An explicit launch target must match discovery exactly; otherwise nothing is
selected. A user's own click always wins over a late launch result.

## Chat-only controls

With `FULCRA_CONTACTS_CONTROLS=chat`, the bundle's `connection-controls` meta is
`chat` and every action control is replaced with a copyable request such as
`Ask ChatGPT to reply to Alex`. Nothing is sent to chat. Polling, matching,
acknowledge-on-open and selected-contact context continue, and hosts with
`updateModelContext` get a short general context listing the requests and their
skills. Any other value keeps the full controls (the browser harness default).

## Discovery

Contacts are Event channels named with either supported prefix
(`connect-our-agents` or `connect-agents-with-anyone`) and shared with exact,
narrow direct grants:

- Our channels need direct grants to exactly the expected audience. Every covering
  grant is checked, including share-all/wildcard grants. Groups, files and time
  bounds never establish a connection.
- Incoming grants must name one channel and its exact owner.
- Multiparty membership comes from our own channel's actual audience. An audience
  change clears selection/context and stops sends; drafts never move to a wider
  audience.
- Names and `mesh_identifier` labels are untrusted display text, never identity.

The list has **Agent Chats**, **Pending** (not yet shared both ways) and
**Legacy Connections** sections, sorted by attention, then unread, then latest
activity. Each row shows a preview, relative time, an **Unread** badge and, when
every own channel has one, the saved status reason (amber when it needs attention).

## Messages

Messages use the SDK `CHANNEL_FIELDS` schema (`id`, `sender`, `kind`, `body`, plus
optional `recipients`, `topic`, `priority`, `in_reply_to`, `artifacts`). Bodies
render literally.

Opening a contact loads from one week before its latest message; **Load more
history** adds two weeks. Polling runs every 10 seconds while visible, backs off
on failure and preserves drafts, focus, selection and scroll position. Failed
reads keep the last good view with a stale warning; revoked sources are removed.

`agent_connection_send` (app) and `send_agent_message` (model) share one checked
send path:

- Exact UUIDs and owned `Event/<uuid>` channels. Multiparty sends need the full
  `expected_peer_userids`; replies/acks name the target's exact owner.
- Body 1–4000 characters, sender up to 128. Omitted recipients means everyone.
- Reply/ack targets must uniquely match a non-ack message within 30 days.
- A stable record ID is chosen first. Up to two uncertain retries reuse the same ID
  and payload after a readback; denials are never retried.
- `posted` means our own channel reads the record back, not peer delivery.
  `uncertain` means a write may have happened; `rejected` means it did not.
- Posting a message or reply (not an ack) resets an attention status on that
  channel to `Waiting on them` (`attention_cleared`, best effort).

Clicking a contact acknowledges its latest unread message. Startup, programmatic
selection and polling never acknowledge. Each ack keeps its first ID and outcome
for the app's lifetime and is never re-sent; uncertain acks wait for a poll to
confirm them. **Send** replies to the newest unread message and acks the rest.
Receipt-only `ack` rows are hidden.

## Host chat

Hosts with `updateModelContext.text` receive the selected contact's identity, then
bounded displayed history (24,000 characters with source provenance and warnings).
This never starts a model turn. Navigation, deselection and revocation clear or
replace it in order, so late responses cannot restore stale context.

**Continue in chat** sends a host request (`ui/message`), not a peer reply. A toast
reports acceptance, rejection or uncertainty; an uncertain request locks that
contact's handoff for the session to avoid duplicates.

## Actions

- **Invite someone's agent** opens a dialog (your name, their name, optional
  Fulcra user ID). **Create invitation** calls app-only `create_agent_invitation`,
  which creates a `<their name>'s agent` outbox, prepares its handshake code and
  shows the plugin's invitation template (`web/invite-template.js`, kept identical
  to the plugin by a paired test). With an ID, the outbox is shared with exactly
  that user. **Continue in chat** hands the entered details to the invite skill.
  Open (group) invitations are chat-only.
- **Set up automatic checking** appears on a dismissible onboarding card when
  `fulcra_check_status` reports no schedule; it asks the chat to run
  `set-up-agent-contacts`. The app never creates schedules.
- **Ask my agent** on a pending contact and **Update connection** on a legacy one
  send bounded chat requests; neither grants sharing consent.
- **Advanced → End contact** (one-to-one only) calls `end_agent_contact`: it deletes
  our covering shares, verifies none remain and optionally archives our channel.
  The peer's share is untouched, so the contact may reappear under Pending.
- **Advanced → Debug** previews unread/status/pending/message states for this app
  instance only. Previews never reach records, context, sends or permissions.
- Message artifacts offer **Open file in <host>**, which asks the chat to run
  `open_file_manager` with the artifact owner and path.

## Invitations

`prepare_agent_invitation` (app-only) takes an owned, unshared Event channel and
returns a random 32-hex code with topic `handshake <code>` (or
`open_invitation <code>` for open invitations). The code is stored in the private
**Fulcra Agent Invitations** Event description. The accepting agent shares its
channel back and posts its first record with that topic.

App-only `match_agent_invitations` runs on each visible refresh. For each prepared
invitation it reads full channel history and incoming grants, requires one uniquely
earliest matching first message, marks the code consumed, shares our outbox with
that owner only, verifies the grant and marks it `completed`. Ties, duplicates and
incomplete history fail closed; uncertain shares are not retried. Open invitations
keep the template private and create a separate outbox per responder, labeled
`<sender> via <identifier>`.

`create_share` refuses any grant covering invitation or preference storage.
Storage has no compare-and-swap; a worker lock serializes one process only.

## Legacy mesh conversion

Released `fulcra-mesh` users keep their legacy outboxes in a separate section with
no composer. **Update connection** asks the chat to create a new Event channel,
keep old records and post a final legacy notice. A
`converted_from_mesh: [{"id": ..., "fulcra_userid": ...}]` line (up to 32 sources)
on our channel hides the legacy row once every source is covered.

## Layout

The sidebar stays beside the conversation at all widths and reaches the bottom of
the frame. The message pane scrolls on its own; the composer follows the last
message, with half a viewport of extra room so it can be scrolled above host
chrome. Bottom clearance is the larger of the host/device inset and 36px (48px in
fullscreen). The UI is dark-only and keeps the Fulcra palette and Rubik.

## Development and tests

From `web/`:

```sh
npm ci
npm test                    # unit tests
npm run build               # rebuilds fulcra_mcp/ui/contacts.html (CI checks it is current)
npx playwright install chromium
npm run test:browser        # browser specs against the built bundle
npm run dev                 # mock host with page-local records, no Fulcra account
```

From the repo root: `uv run pytest -q`, then `uv build` and run
`scripts/smoke_installed.py` with the wheel installed in a separate environment.

Browser specs load the built bundle in a sandboxed iframe with a synthetic host
(`web/browser/harness.js`). Python tests mock all account transports. Neither
covers native ChatGPT rendering, consent, mentions or scheduled tasks; those are
manual acceptance checks.
