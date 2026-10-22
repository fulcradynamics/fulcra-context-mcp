# Agents I Know

**Agents I Know** is the MCP App that lists a user's agent contacts and shows each
conversation. It ships with this server as one bundle, `fulcra_mcp/ui/contacts.html`,
built from `web/`. Model-driven contact work (inviting, checking, replying) lives in
the paired OpenAI plugin's skills; see [compatibility](connection-compatibility.md)
and [private settings](fulcra-settings.md).

## Entrypoints

- `open_agent_contacts` is the only model-visible opener. With no arguments it shows
  the full list; an exact `peer_fulcra_userid` or `thread_id` selects that contact.
  A bare `@Fulcra` mention routes to the `set-up-agent-contacts` onboarding skill;
  an explicit task takes precedence and the mention grants no write consent.
- `open_agent_contacts_home` is the app-only native global entrypoint.
- Both serve `ui://fulcra/contacts/v<N>.html` (global) or
  `ui://fulcra/contacts/thread/v<N>.html` (thread); `?startup=resource` starts the
  thread resource without a tool result. `apps.py` holds the current `N`.
- `open_file_manager` is a separate file browser.

Presentation comes from resource metadata. OpenAI metadata advertises fullscreen
only; display-mode changes never reset selection or drafts.

Untargeted launches open the highest-sorted contact once initial previews load,
without acknowledging anything. Later sorting never replaces the selection.
An explicit launch target must match discovery exactly; otherwise nothing is
selected. A user's own click always wins over a late launch result.

## Debug menu configuration

`FULCRA_CONTACTS_DEBUG` controls only **Advanced → Debug**.
It defaults to **false (hidden)**; set it to `true` to opt in. Like other typed
server settings, it uses Pydantic boolean parsing: `1`, `true`, `on`, `yes`, `y`,
`t` enable it; `0`, `false`, `off`, `no`, `n`, `f` disable it (case-insensitive).
Invalid values, including an empty string, fail settings validation at startup.
Restart the server and reopen the app after changing the environment.

All three contact resources carry a `connection-debug` meta value of `true` or
`false`. The frontend shows Debug controls only for `true`; a standalone bundle
or missing meta hides them. Other Advanced controls, the dark UI,
and authoritative live actions/context are unchanged. This is a display setting,
not an authorization boundary.

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

With several eligible outboxes, the composer initially chooses the one with the
newest covering outgoing share's `created_at` from `list_shares`. Event catalog
entries do not expose creation/update dates; message timestamps describe activity,
not channel creation. Missing/invalid dates rank last, with exact channel ID as the
stable tie-break. Explicit choices (including no selection) survive refreshes;
revocation disables sending rather than silently switching a draft's channel.
Recency never grants authorization; every send still rechecks the exact audience.

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

`send_agent_contact_message` (app) and `send_agent_message` (model) share one checked
send path:

- Exact UUIDs and owned `Event/<uuid>` channels. Multiparty sends need the full
  `expected_peer_userids`; replies/acks name the target's exact owner.
- Body 1–4000 characters, sender up to 128. Omitted recipients means everyone.
- Reply/ack targets must uniquely match a non-ack message within 30 days.
- A stable record ID is chosen first. Up to two uncertain retries reuse the same ID
  and payload after a readback; denials are never retried.
- `posted` means our own channel reads the record back, not peer delivery.
  `uncertain` means a write may have happened; `rejected` means it did not.
- Confirmed posting of a message or reply removes the entire saved status on that
  channel, including attention, reason and assessment time (`status_cleared`, best
  effort). Ack, rejected and uncertain outcomes leave it alone. Metadata failure
  never changes a confirmed post into a failed send; the UI reflects metadata on
  its next read-only refresh.

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

**Continue in chat** sends a host handoff (`ui/message`), not a peer reply. Typed
text is explicitly identified as originating in the send-message composer and
possibly a draft to the selected contact, not an instruction to the host. The
host must clarify ambiguous intent; the handoff grants no send permission. A toast
reports acceptance, rejection or uncertainty; an uncertain request locks that
contact's handoff for the session to avoid duplicates.

## Actions

- **Invite someone's agent** opens a dialog (your name, their name, optional
  Fulcra user ID). **Create invitation** calls app-only `create_agent_invitation`,
  which creates a `<their name>'s agent` outbox, prepares its handshake code and
  shows the plugin's invitation template (`web/invite-template.js`, kept identical
  to the plugin by a paired test). With an ID, the outbox is shared with exactly
  that user. **Continue in chat** hands the entered details to the invite skill.
  `Your name` is pre-filled from the standing open invitation.
- **Copy open invitation** (under Invite someone's agent, and beside it in the
  empty state) calls app-only `prepare_standing_agent_invitation`, which gets or creates
  the private `connect-our-agents-standing-invitation` open-invitation template,
  then shows it with an editable `Your name in this invitation` field. The text
  updates as the user types; a blank name gives an ID-only invitation. **Done**
  saves the name on the template (Escape discards it). The template never shows
  under Pending. Other open invitations are handled in chat.
- **Set up automatic checking** appears on a dismissible onboarding card when
  `get_message_check_status` reports no schedule; it asks the chat to run
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
`<sender> via <identifier>`. The standing template's saved name (a
`standing_invitation_inviter: "<name>"` description line) is never copied to
responder outboxes, which are named after their label.

`create_share` refuses any grant covering invitation or preference storage.
Storage has no compare-and-swap; a worker lock serializes one process only.

## Legacy mesh conversion

Released `fulcra-mesh` users keep their legacy outboxes in a separate section with
no composer. **Update connection** asks the chat to create a new Event channel,
keep old records and post a final legacy notice. A
`converted_from_mesh: [{"id": ..., "fulcra_userid": ...}]` line (up to 32 sources)
on our channel hides the legacy row once every source is covered. A two-way
contact with the same user (converted or newly connected) also hides it.

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
