# Agent connection compatibility

The top-level list is **Agents I Know**; threads are **Agent Contacts**. Underlying channels are agent connections. Server 1.8.0 / UI v41 pairs with plugin 0.11.0.

## Current interface

- `fulcra_open`: global list; `ui://fulcra/contacts/v41.html`.
- `agent_contacts_open`: inline list; `ui://fulcra/contacts/threads/v41.html`.
- `agent_contact_open`: selected contact; `ui://fulcra/contacts/thread/v41.html`.
- `agent_contacts_search`: composer actions; `contacts://threads` descriptors.
- `agent_connection_send`, `set_contact_identifier`: existing checked send and display-label operations, with unchanged arguments.
- `fulcra_settings_read`, `fulcra_settings_update`, `fulcra_check_status`: general settings and check status.

Refresh discovery and reinstall together. Old tool registrations and UI resource names are not advertised as aliases. No storage migration is performed.

## Deliberate exceptions

`connection_compatibility.py` and `web/connection-compatibility.js` isolate persisted identifiers:

- `[mesh_identifier: ...]` remains the display-label description suffix.
- `converted_from_mesh: ...` remains historical owner/type provenance. The UI says **Converted from legacy connection**.
- Legacy `Mesh Outbox` names still identify existing MomentAnnotation channels.
- `/agent/chatgpt/mesh-checks/` remains the private schedule/checkpoint root.

Synthetic fixtures retain these strings to exercise compatibility, not new branding. Do not rename user-owned catalog entries, rewrite existing descriptions, reset notification or acknowledgement state, or move files for terminology changes.

The plugin's packaged `connect-agents-with-anyone` directory is deliberately unchanged, including its source pins and historical language. Initialization instructions translate its old send/label/settings references to the current tools. The plugin's callers load a matching compatibility reference outside that directory. This is a tool-name translation only: no extra permission, lower-level fallback, acknowledgement, message, share or schedule is authorized. Existing scheduled prompts require consented updates on the same task with every permission ceiling and checkpoint preserved.

New resources and renamed tools keep existing authorization, exact-audience checks, acknowledgement and polling behavior. Live host rendering and model interpretation still require acceptance; local tests are not deployment evidence.
