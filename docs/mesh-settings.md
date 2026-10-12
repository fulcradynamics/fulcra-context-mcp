# Mesh check settings

The server advertises `openai/settings` alongside mentions using the existing
FastMCP experimental capabilities on MCP 2025-11-25. No dependency upgrade or
scheduler service is involved.

- `aicq_settings_read({})` declares and returns `{schema, values, layout}`. The
  schema/values are empty: there is no editable timestamp, cadence or enabled
  preference. A same-server tool action describes **Last mesh check**.
- `aicq_settings_update({set: ...})` rejects edits, including an empty update.
- `aicq_schedule_settings({})` opens `ui://fulcra/mesh/settings/v1.html` with status.
  `aicq_check_status({configuration_id?: ...})` supplies read-only refresh/selection.
  All four tools are app-only; the host model uses the existing setup skill/tools.
- `web/settings.html` and `web/settings.js` build into the committed, self-contained
  `fulcra_mcp/ui/mesh-settings.html`. Wheels and sdists package the resource.

## State and privacy

The request-scoped authenticated Fulcra client lists current files directly under
`/agent/chatgpt/mesh-checks/`. This is the existing ChatGPT setup/check namespace,
not a portable scheduler contract. One configuration is selected automatically;
multiple configurations require explicit selection. No account-global last-check
maximum or combined task is synthesized. No writes occur on open or refresh.

The existing Markdown file's JSON block is downloaded (up to 1 MB) and validated
server-side. Only status and account/configuration/path/task references leave the
server; pending/reported message contents are never returned to the app. There is
no separate status file or checkpoint-write API. A larger, malformed, inaccessible
or account-mismatched state produces **Status unavailable**, not **Never checked**.
A valid configuration with null `last_checked` shows **Never checked**; an empty
successful listing shows **Not set up**. Successful times are qualified in UTC.

`last_checked` means the last fully completed scheduled data check, not a manual
test, foreground refresh, notification delivery or current enabled state. The
existing check skill owns this checkpoint. The server does not infer or repair it.

## Explicit chat handoff

**Reschedule checks in Chat** sends a starter request only after a click. The
request names the packaged `fulcra-mesh-setup` workflow and selected references,
not message history. It asks the model to inspect the existing task, obtain the
interval, update the same task and read it back. Missing/ambiguous tasks and
unavailable cross-chat access require clarification/native task management, not
automatic replacement creation. Pair with plugin 0.2.10 or later.

New-chat sending requires advertised `experimental["openai/message"]`, text
messaging and a known desktop/web host platform; it uses
`_meta["openai/message"] = {"target":"new","send":true}`. Mobile and unknown
platforms use a disclosed active-chat fallback. Without text messaging, the app
exposes a copyable request. Capability changes are checked at click time. Unknown
capabilities are not inferred from branding or browser user-agent strings.

The action stays locked after a send attempt, including rejection/timeout, and
never retries automatically. A transport failure may still have delivered the
message. Feedback distinguishes an accepted request from a changed schedule and
asks the user to check chat before copying/sending again.

## Verification and live acceptance

Automated protocol, SDK-transport and sandboxed-iframe tests use synthetic data.
They verify emitted capability/tool schemas, read-only state projection and
isolation, configuration selection, resource packaging, explicit single sends,
mobile/unsupported fallbacks and rejected/uncertain delivery. They do not prove
native settings rendering, model compliance, cross-chat task access or alerts.

After refreshing the server connection and reinstalling the paired plugin:

1. Open native plugin settings. Verify the action/status description and modal
   with no configuration, a never-run configuration and a successful timestamp.
2. With multiple configurations, select one and verify only its status/reference
   is used. Refresh and a failed/manual check must not advance the checkpoint.
3. Click **Reschedule checks in Chat** once. Observe the actual visible starter
   message, new-chat transition on supported desktop/web, and mobile fallback.
4. Inspect the actual task ID and task count before and after a consented cadence
   change. Verify the same task's saved recurrence/destination/enabled state.
5. Test missing/ambiguous task and unavailable cross-chat access: no replacement.
6. Separately observe a scheduled run with the widget closed, incoming-message
   summary, notification delivery and empty-check alerts. These remain separate
   acceptance gates, not consequences of successful settings tests.

Record host/mode/plan and connection with the results. Do not count a bridge
acknowledgement as completion or leave a test schedule running without consent.

Source: [OpenAI settings and message extensions](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md).
