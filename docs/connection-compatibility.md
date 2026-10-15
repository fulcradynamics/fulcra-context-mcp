# Agent connection compatibility

Server 1.11.0 / UI v46 pairs with plugin 0.14.0. The list is **Agents I Know** and threads are **Agent Contacts**. Refresh server discovery and reinstall together; local support is not deployment.

## Current interface

- `fulcra_open`: global list; `ui://fulcra/contacts/v46.html`.
- `agent_contacts_open`: inline list; `ui://fulcra/contacts/threads/v46.html`.
- `agent_contact_open`: contact/picker; `ui://fulcra/contacts/thread/v46.html`.
- `agent_contacts_search`: app-only native composer mentions, not a model skill dependency.
- `agent_connection_send`, `send_agent_message`, `set_contact_identifier`: checked sends and metadata operations.
- `fulcra_settings_read`, `fulcra_settings_update`, `fulcra_check_status`: settings/check status.
- Existing model-visible `open_file_manager`, file and sharing tools support the plugin's new files/send entry skills; no additional file server or upload mechanism.

## Renamed connection skill

The adapted plugin workflow is now `connect-our-agents`, tracking the upstream rename at c419b169128effbbb8d74fb775a5f960655cf959. New channel/share names use that prefix. Server and UI accept both it and `connect-agents-with-anyone`, including mixed peer generations, without changing stored descriptions or grants. Schema, ownership, exact audience, target-owner, retry and readback rules remain unchanged.

The pinned SDK's canonical connection resolver understands only historical share names. `send_agent_message` translates the new name in a local discovery copy; the common send implementation rechecks untouched live grants before writing. No API mutation or permission widening is involved.

Existing tool-name translations still apply to historical references inside the adapted skill. Initialization and the plugin compatibility reference explain them without granting extra permission or lower-level fallback. Existing task prompts need consented same-task dependency updates/readback, preserving task identity, permissions and checkpoints. Reinstalling alone does not update schedules.

## Preserved data

Keep `[mesh_identifier: ...]`, `converted_from_mesh: ...`, and legacy `Mesh Outbox` names unchanged. Do not rename channels, rewrite descriptions, reset notification/acknowledgement state, recreate connections or move files for this update.

Automated prefix tests cover send/readback, grants, discovery, schema projection and revocation. Native host/model/file-sharing acceptance remains separate from synthetic protocol and package verification.
