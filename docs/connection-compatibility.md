# Agent connection compatibility

Server 1.17.1 / UI v67 requires the skill-first plugin (0.17.2 describes the chat-only
instructions) for model-driven contact workflows.
The list remains **Agents I Know**, with an **Agent Chats** section. Stored relationships
and private configuration schemas are unchanged. Refresh server discovery and install
the compatible plugin together; local support is not deployment or native-host acceptance.

## Current interface

Native invitation operations retain app-only `prepare_agent_invitation(data_type, open_invitation=true)`
and `match_agent_invitations()`. Skills use generic primitives over the same state.
The returned first-message topic uses the distinct
`open_invitation <code>` prefix. Existing single-person invitations retain
`handshake <code>` (missing stored prefix means an existing individual invitation).
The private persisted code and prefix select the correct invitation before any
outbox is chosen. Open templates are never shared: the server copies their schema
and description into a dedicated individual outbox per authenticated responding owner.
Bindings survive checks; uncertain creation/share attempts are not automatically
retried. Completed responders are not re-shared after revocation, while the open
template remains available to new owners. Ambiguous same-owner channels stay pending.
Sender is display-only, with `<sender> via <open invitation identifier>` as the
fallback label, bounded by the existing 80-character identifier limit. Invalid or
missing sender uses `Agent`; a missing template label uses its exact type ID.
UI load/refresh uses the deterministic matcher under persisted-invitation authorization.
Skills must preserve its validation and state transitions. Ordinary discovery/message polls
remain read-only; matching adds no model turns or arbitrary shares.
Worker-local locking is not a distributed transaction or cross-worker CAS guarantee.

- `fulcra_open`: app-only global full-panel list; `ui://fulcra/contacts/v67.html`.
- `agent_contact_open`: sole model-visible contact opener, optional exact peer/thread;
  `ui://fulcra/contacts/thread/v67.html`. Empty arguments show the full list without selection.
  Direct-resource startup adds `?startup=resource`. The compact opener and resource are removed.
- `agent_contacts_search`: app-only native composer mentions, not a model skill dependency.
- `send_agent_message`: canonical model-visible checked sender.
- `agent_connection_send`, `set_contact_identifier`, `set_contact_status`: app-only checked operations.
- `update_data_type_metadata`: generic owned active Event/Metric name/description update;
  exact catalog reads provide raw metadata for lossless read-modify-write. No schema mutation.
- `create_agent_invitation`: app-only Invite someone dialog; creates a `<recipient>'s agent` outbox, prepares its single-person code and, with an optional recipient ID, shares it with exactly that user. Same template and matching as the plugin's invite procedure.
- `end_agent_contact`: app-only End contact; deletes our covering shares for one single-peer channel, verifies none remain and optionally archives it, as the plugin's Ending connections step does.
- `fulcra_settings_read`, `fulcra_settings_update`, `get_contact_preferences`,
  `set_contact_preferences`, `fulcra_check_status`: app-only settings/check status;
  native settings registration is preserved.
- Existing model-visible `open_file_manager`, file and sharing tools support the plugin's new files/send entry skills; no additional file server or upload mechanism.

## Renamed connection skill

The adapted plugin workflow is now `connect-our-agents`, tracking the upstream rename at c419b169128effbbb8d74fb775a5f960655cf959. New channel/share names use that prefix. Server and UI accept both it and `connect-agents-with-anyone`, including mixed peer generations, without changing stored descriptions or grants. Schema, ownership, exact audience, target-owner, retry and readback rules remain unchanged.

The pinned SDK's canonical connection resolver understands only historical share names. `send_agent_message` translates the new name in a local discovery copy; the common send implementation rechecks untouched live grants before writing. No API mutation or permission widening is involved.

No compatibility aliases are added for obsolete unreleased tools. Current prompt
templates must use generic primitives, not app-only operations. This release does
not migrate or edit existing schedules; reinstalling does not update host tasks.

## Preserved data

Keep `[mesh_identifier: ...]`, `converted_from_mesh: ...`, and legacy `Mesh Outbox` names unchanged. Do not rename channels, rewrite descriptions, reset notification/acknowledgement state, recreate connections or move files for this update.

Automated prefix tests cover send/readback, grants, discovery, schema projection and revocation. Native host/model/file-sharing acceptance remains separate from synthetic protocol and package verification.
