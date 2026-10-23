# Contact preferences and check status

The server advertises native `openai/settings`. Settings are configuration, not
instructions: saving never sends messages, changes checkpoints or schedules
anything. Every tool here is app-only. Skills edit the same owned document with
exact catalog reads and `update_data_type`, preserving unrelated values
and verifying ownership and readback. Existing broader shares may expose it.

## Tools

- `get_fulcra_settings` returns `{schema, values, checking_preferences, layout}`.
- `update_fulcra_settings({set: ...})` validates, merges, saves and reads back.
  Empty updates, unknown fields, bad values and unverifiable saves fail.
- `get_contact_preferences(data_type, peer_userid[, expected_peer_userids])`
  verifies an owned connection's exact audience and returns effective values and
  overrides. `set_contact_preferences(..., overrides)` replaces them; `{}` restores
  inheritance.
- `get_message_check_status` reports the last check per configuration (not set up,
  never checked, a UTC time, several configurations, or unavailable) from
  `/connect-our-agents/connection-checks/`. It never exposes message contents.

## Values

| Key | Default |
|---|---|
| acknowledge, share status | on |
| pause autonomous replies | off (a global pause applies to every contact) |
| `attention_*` (waiting, overdue, priority, membership announcements, new unmatched/matched contacts) | on |
| `unanswered_days` | 2 (1–365) |
| `notifications` | `attention` (`all_messages`, `none`) |
| `checking_preferences` | stored-only chat text, up to 2000 characters |

Native settings group the attention switches (labeled **Surface**),
`unanswered_days` and `notifications` under **Notification Preferences**.
**Push notifications and email** shows `only surfaced activity`,
`all messages from my contacts` or `no notifications or emails`; updates accept
either labels or stored values. These guide the plugin's reporting; they are not
host notification guarantees.

## Storage

One owned **Fulcra Contact Preferences** Event type holds the document in its
description:

```json
{"version":1,"global_preferences":{},"overrides":{"Event/<own connection>|<peer UUID>":{"notifications":"none"}}}
```

Reads never create it; the first save does. Missing fields inherit defaults, then
global values. Reads and saves fail closed on a malformed document or an explicit
single-type outgoing grant targeting this storage. Existing share-all, wildcard
and mixed-type grants do not block use; they may expose preferences, and are not
changed by the app. Generic `create_share` does not enforce app storage privacy.
Saves are serialized per worker and verified by readback, but there is no
compare-and-swap across workers.

The plugin reloads settings on every `check-messages` / `reply-to-messages` run;
only the latter replies, subject to pauses and task restrictions.
[OpenAI settings specification](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md).
