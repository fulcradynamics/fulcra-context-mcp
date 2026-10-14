# Contact and connection-check settings

The server advertises `openai/settings` with the existing MCP stack. Native fields
configure contact behavior; no settings buttons, modal or scheduler API is needed.
Preference values are user configuration, not instructions.

- `fulcra_settings_read({})` returns `{schema, values, checking_preferences, layout}`.
  Native fields: Acknowledge messages (on), Share contact status (on), Pause
  autonomous replies (off), Flag contacts waiting for you (on), Flag contacts that
  have not replied (on), Days before flagging contacts that have not replied (2),
  Flag high-priority messages (on), Flag peers announcing added recipients (on) and
  Notify about (`attention`, `all_messages`, `none`).
- `checking_preferences` is free text (at most 2000 characters, empty by default). It
  is stored and returned but is not a native field; the last layout group says “For
  more specific preferences, chat with your agent.”
- The read-only **Last contact check** and plain-chat schedule guidance remain
  native group titles. No editable timestamp, cadence or scheduler enabled flag.
- `fulcra_settings_update({set: ...})` validates changed fields (including
  `checking_preferences`), merges, persists and reads back. Unknown fields, empty
  updates, wrong types and invalid bounds fail. Saving does not send messages, alter
  checkpoints or reschedule.
- `fulcra_check_status` remains the app-only configuration-specific read projection.

## Persistence

Global preferences and per-contact overrides live in the description of one private
Event data type owned by the authenticated account and named exactly
**Fulcra Contact Preferences**. It is found by name in the account's catalog and
created on the first save; reads never create it. The description is a JSON document:

```json
{"version": 1,
 "global_preferences": {"notifications": "none"},
 "overrides": {"Event/<own connection>|<peer user ID>": {"pause_autonomous_replies": true}}}
```

Global and override values use the same fields. Missing fields inherit defaults
(globally) or the global value (per contact). A global pause applies to every
contact. Description updates read back immediately, without record-indexing delay.
A worker lock serializes local updates; the API has no compare-and-swap, so
concurrent external saves can still race and readback detects some, not all, conflicts.

The type must never be shared. Reads and saves fail closed when any outgoing share
uses `share_all_data`, `Event`, `Event/*`, `*` or the type itself, and `create_share`
refuses it. Malformed documents and unknown fields fail closed rather than falling
back to defaults.

`get_contact_preferences(data_type, peer_userid[, expected_peer_userids])` verifies
that the caller owns that Event connection with that exact audience, then returns the
effective values and stored overrides. `set_contact_preferences(..., overrides)`
performs the same verification and replaces that contact's overrides; `{}` restores
the global values. Connection descriptions are never modified for preferences.

## Checking

The paired plugin's `contact-preferences.md` defines how values are applied.
`check-messages` and `reply-to-messages` both load current settings on every run,
acknowledge when Acknowledge messages is on, share a general conversation status when
Share contact status is on, and flag/notify per the attention and notification fields.
Only `reply-to-messages` replies, and not while replies are paused globally or for
that contact. A scheduled task names one of the two skills, chosen in setup.

Contact status (`set_contact_status`) is a general status of the conversation from
aspects both sides can see, such as a priority message or time since the last reply.
It is stored on the user's own connection type, so the contact can see it.

The status reader still uses `/agent/chatgpt/mesh-checks/`. It distinguishes Not set
up, Never checked, UTC-qualified successful checks, multiple configurations and
Status unavailable. Neither foreground refresh nor preference editing advances
`last_checked`; no pending message contents enter settings output.

## Verification and live acceptance

Synthetic MCP and real-SDK transport tests cover defaults, create-then-update with
readback, invalid values, privacy, overrides, the global pause and the unchanged status
projection. Live acceptance: save and reopen values in native settings; confirm the
type is created once and stays unshared; set a per-contact override in chat; run both
skills and observe acknowledgements, status, notifications and the pause.

Source: [OpenAI settings extension](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md).
