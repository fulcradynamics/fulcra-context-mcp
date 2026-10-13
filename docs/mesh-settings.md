# Mesh check settings

The server advertises `openai/settings` alongside mentions using the existing
FastMCP experimental capabilities on MCP 2025-11-25. No dependency upgrade or
scheduler service is involved.

- `aicq_settings_read({})` returns `{schema, values, layout}`. Schema properties
  and values are empty: there is no editable timestamp, cadence or enabled flag.
- Two native group titles display **Last mesh check: <status>** and
  **To change the schedule, ask in chat: “Change how often you check my Fulcra messages.”**
  Both have empty `items`; there is no tool action, modal, button or chat launch.
- `aicq_settings_update({set: ...})` rejects edits, including an empty update.
- `aicq_check_status({configuration_id?: ...})` retains the read-only status and
  explicit configuration-selection contract. All three tools are app-only;
  the model uses the packaged setup skill and existing file/task tools.

## Native host surface

The tested ChatGPT tunnel client rendered native property fields and group
headings but not settings tool-action rows. Adding model visibility removed a
warning without rendering the action; a temporary property did render. This is
observed client behavior, not a universal statement about tool-action support.
The temporary diagnostic property is not part of this server's settings schema.

The documented `SettingsGroup.title` surface is used for both lines, rather than
inventing a text item or disguising a timestamp as an editable setting. The exact
two-title layout, wrapping, and empty-group visibility still need verification
in the target client. If the host suppresses empty groups or truncates the
instructions, report that limitation; do not add an action or fake property.

## State and privacy

The request-scoped authenticated client lists private current files directly
under `/agent/chatgpt/mesh-checks/`. A single configuration supplies its status.
Multiple configurations show **Multiple configurations — ask in chat to choose
one** without downloading or combining them. No account-global maximum is used.

The existing Markdown JSON block is downloaded (up to 1 MB) and validated.
Malformed, inaccessible, oversized or account-mismatched state yields **Status
unavailable**, not **Never checked**. A valid null `last_checked` yields **Never
checked**; an empty successful listing yields **Not set up**. Successful timestamps
are UTC-qualified. Native settings return only status and guidance, not account
references or pending/reported contents. The separate status projection retains
its existing limited reference fields and never returns message contents.

Opening/refreshing settings performs only reads. `last_checked` is the last fully
completed scheduled data check, not a manual test, foreground refresh,
notification-delivery receipt or assertion that the schedule is active. The
existing check skill owns this checkpoint; this server neither advances nor
repairs it.

## Change the schedule in chat

The user types the displayed request. The existing `fulcra-mesh-setup` workflow
verifies the account, locates the private configuration and actual host task,
clarifies ambiguity, asks for the desired cadence, updates that same task with
consent and reads it back. Missing tasks or unavailable cross-chat lookup require
clarification/native task management, never automatic replacement. No pending
contents or checkpoint rewrite is needed. Refresh discovery and reinstall the
plugin with the updated plain-chat guidance.

## Verification and live acceptance

Automated protocol and real-SDK transport tests use synthetic data to verify the
settings contract, all status states, account isolation, repeated read-only
opens, rejected writes and absence of modal/action discovery. Existing Mesh UI
unit/browser suites verify unrelated entrypoints and bridge behavior are intact.
Installed-wheel checks verify the removed modal asset is absent. These tests do
not establish native host rendering, model compliance or scheduler access.

After server refresh and plugin reinstall, record the actual client/mode/plan:

1. Open native settings with no configuration, never-checked, successful,
   unavailable and multiple-configuration state. Verify readable status and
   instructions, no controls, no automatic message or model turn.
2. Reopen/refresh, run a manual check and observe a failed check; none should
   advance `last_checked`. Confirm a successful scheduled check separately.
3. Type the displayed request, verify the setup workflow loads and resolves the
   right task; compare task ID/count and read back a consented cadence change.
4. Verify ambiguous/missing/inaccessible tasks do not create replacements.
5. Separately test unattended execution and notification delivery. Neither is
   implied by a displayed status timestamp.

Source: [OpenAI settings extension](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md).
