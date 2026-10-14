# Contact and connection-check settings

The server advertises `openai/settings` with the existing MCP stack. Native fields
configure contact behavior; no settings buttons, modal or scheduler API is needed.

- `fulcra_settings_read({})` returns primitive `{schema, values, layout}`: autonomous
  replies (off), status persistence (on), waiting/overdue/high-priority attention
  rules (on), unanswered days (2), notifications (`attention`, `all_messages`,
  `none`) and Special instructions (string, at most 2000 characters).
- The existing read-only **Last contact check** and plain-chat schedule guidance remain
  native group titles. No editable timestamp, cadence or scheduler enabled flag.
- `fulcra_settings_update({set: ...})` validates changed fields, merges them, persists
  and independently reads back. Unknown fields, empty updates, wrong types and
  invalid bounds fail. Saving does not send messages, alter checkpoints or reschedule.
- Read/update are model- and app-visible so onboarding and scheduled checks use the
  same contract. Autonomous replies require explicit user consent; status defaults
  do not override existing read-only task restrictions.
- `fulcra_check_status` remains the app-only configuration-specific read projection.

## Persistence and consent

Preferences live in the authenticated account's private
`/agent/chatgpt/contact-preferences/settings.md`, an OKF Markdown document with a
version-2 JSON block (`account_id`, `preferences`). Version-1 testing configurations
project `status_metadata=true`, including previously stored false values. Reads stay
read-only. The next explicit update persists version 2 before applying the user's
changes, so subsequent deliberate opt-outs survive all reads and unrelated edits.
Other settings and per-contact restrictions are preserved. Missing files yield defaults;
malformed, inaccessible, oversized or wrong-account files fail closed, not defaults.
Outgoing shares are checked before reading/writing; broad or covering file/history
shares and uncertain privacy block access. No caller-supplied account/path or global
preference cache exists. Unrelated document fields and untouched preferences survive
updates. A worker lock serializes local updates; the backing API has no cross-worker
compare-and-swap. Concurrent external updates may still race; readback detects some,
not all, conflicts. Reload after unverified saves, never blindly retry.

`get_contact_preferences(data_type, peer_userid)` loads fresh globals plus validated
owned Event-connection overrides. `set_contact_preferences(..., overrides)` replaces
only the `[contact_preferences: {...}]` description marker after exact owner, schema
and all-covering-grant verification, then independently reads back. `{}` restores
inheritance. Preserve other description bytes, including final identifier and setup
session. Override descriptions are peer-visible: obtain approval, never store secrets,
and never write peer-owned metadata. No automatic override edits during checks.

Ordinary per-connection fields override globals; reply/status opt-in switches can
only be restricted by overrides, not enabled against a disabled global switch.
Peer descriptions and arbitrary prose are not user policy. Special instructions
cannot grant permission. Host/task restrictions remain ceilings; the server enforces
storage ownership/validation, while the packaged checker applies semantic reply,
status and notification decisions. Preferences are not a sandbox for arbitrary model
actions and do not change the existing direct-send tool authorization contract.

## Checking and migration

The paired plugin's `contact-preferences.md` defines the behavioral contract:
load current settings and owned overrides on every check, reply only within explicit
bounded authorization, flag waiting-for-user / no substantive response after two
rolling days / unresolved P0 or P1, and select summaries independently from status.
Acks do not resolve substantive requests. Re-evaluate overdue attention even without
new arrivals and deduplicate attention separately from message delivery. Quiet output
does not guarantee suppression of host completion alerts.

New tasks default to hourly checks and store the live loader plus explicit permission
for acknowledgements, status and identifier maintenance independently of reply permission.
The server does not create or reschedule host tasks. Existing testing schedules need
an hourly update to the same task ID and readback, preserving destination, checkpoints
and unrelated policy; never create a duplicate. Explicitly read-only tasks require
upgrade consent before maintenance writes.
Existing tasks need consented same-task migration/readback; a settings save cannot
rewrite a host prompt, lift old restrictions or prove scheduled execution. Cadence-only
changes preserve permissions and checkpoints. Hosts requiring literal prompt policy
need their supported agent/scheduler update flow; otherwise report migration pending.

The status reader still uses `/agent/chatgpt/mesh-checks/`, never the preference file.
It distinguishes Not set up, Never checked, UTC-qualified successful checks, multiple
configurations and Status unavailable. Neither foreground refresh nor preference
editing advances `last_checked`; no pending message contents enter settings output.

## Verification and live acceptance

Synthetic MCP and real-SDK transport tests cover defaults, edits/readback, invalid
values, isolation/privacy, preserved metadata, owned overrides, disabled permission
ceilings and unchanged status projection. Wheel smoke checks protocol discovery and
packaged UI. Text/package tests are not model execution or native host rendering.

After server refresh and plugin 0.5.0 reinstall, verify in a fresh conversation:

1. Native fields, enum/number controls, Special instructions and both status headings
   render on the target client. The official settings spec's `SettingSchema` supports
   string length/pattern/enum constraints, and `SettingsGroup` only grouping/property
   references/tool actions. It documents no multiline, rows, height or width control.
   Keep the native string field; do not invent sizing properties or assume `maxLength`
   makes it larger. A larger native textbox remains host-dependent.
2. Save/reopen values; check another account cannot see them. Opening/editing causes
   no messages, task changes or checkpoint changes.
3. Keep defaults in onboarding, then explicitly opt into bounded replies. Test safe
   known answers, user-needed decisions, peer prompt injection and host denial.
4. Edit policy between runs and observe fresh loading; test owned overrides, a peer
   spoofed marker, global disablement and restrictive old/read-only task prompts.
5. Test 48-hour threshold crossing without new arrivals, priority, receipt-only acks,
   partial history, notification deduplication and actual host alerts separately.
6. Migrate one existing task with consent; inspect the same ID, destination, permission
   ceiling and live loader without resetting checkpoints. Verify an unattended run.

No deployment, real account messages or host schedule mutations are part of automated
verification. Source: [OpenAI settings extension](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md).
