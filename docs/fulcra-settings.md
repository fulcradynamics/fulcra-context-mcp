# Contact preferences and check status

The server advertises native `openai/settings`; values are configuration, not
instructions. No settings action sends messages, changes checkpoints or schedules.

- `fulcra_settings_read` returns `{schema, values, checking_preferences, layout}`.
  Defaults: acknowledge/share status on, autonomous replies not paused; attention
  switches for waiting, overdue, priority, peer membership announcements and new
  unmatched/matched contacts (`attention_new_unmatched_contact`,
  `attention_new_matched_contact`) on;
  unanswered threshold 2 days (1–365); notifications `attention` (also
  `all_messages` or `none`). `checking_preferences` is stored-only chat-editable
  text, at most 2000 characters, not a native field.
  Native attention labels use **Surface** and live with `unanswered_days` and
  `notifications` in **Notification Preferences**. **Push notifications and email**
  displays exactly `only surfaced activity`, `all messages from my contacts`,
  `no notifications or emails`. The native settings spec has no separate enum
  label mechanism: read/update return these labels and update accepts labels or
  canonical values. Storage and effective contact preferences retain
  `attention` / `all_messages` / `none`. These guide reporting, not host delivery
  guarantees, notification permissions or schedule creation.
- `fulcra_settings_update({set: ...})` validates, merges, persists and reads back.
  Empty updates, unknown fields, invalid types/ranges and unverifiable saves fail.
- `get_contact_preferences(data_type, peer_userid[, expected_peer_userids])`
  verifies an owned Event connection's exact audience and returns effective values
  plus overrides. `set_contact_preferences(..., overrides)` replaces overrides;
  `{}` restores inheritance. A global reply pause applies to every contact.
- `fulcra_check_status` is an app-only configuration-specific read. Native group
  titles display the last contact check and plain-chat schedule guidance.

## Private persistence

One owned **Fulcra Contact Preferences** Event type holds this description:

```json
{"version":1,"global_preferences":{},"overrides":{"Event/<own connection>|<peer UUID>":{"notifications":"none"}}}
```

Reads never create it; first save does. Missing fields inherit defaults/global
values. No preferences live on shared connection descriptions. Old internal
settings files and override markers are neither read nor migrated.

Reads/saves fail closed on malformed documents or covering outgoing shares
(`share_all_data`, `Event`, `Event/*`, `*`, or the type itself); `create_share`
refuses the preference type. A worker lock serializes local saves and independent
readback verifies them. Storage has no compare-and-swap: external concurrent
updates can still race, and readback cannot detect every conflict.

## Checks and acceptance

The paired plugin loads fresh settings on every `check-messages`/`reply-to-messages`
run; only the latter replies, subject to global/contact pause and task restrictions.
Status describes general peer-visible conversation facts, never private reasoning.

The status reader uses `/connect-our-agents/connection-checks/` and distinguishes not set up,
never checked, successful UTC timestamps, multiple configurations and unavailable
state. It never exposes pending message contents or advances `last_checked`.

Synthetic tests cover persistence, SDK transport, privacy, overrides and status.
Native settings rendering, reopen/save, scheduler consent and actual skill behavior
remain host acceptance checks. [OpenAI settings specification](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md).
