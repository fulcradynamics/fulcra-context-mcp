# Agent connection interface

The paired OpenAI plugin's skills drive model contact workflows using generic
catalog, record, metadata and sharing tools. Contact-specific operations are
app-only, used by **Agents I Know** and native settings. Update the server and
plugin together; neither implies deployment or native-host acceptance.

## Tools

Model-visible:

- `open_agent_contacts`: the contacts app; optional exact peer or thread.
- `send_agent_message`: the checked sender.
- `update_data_type`: owned Event/Metric name/description edits. Read the
  exact catalog entry first for lossless read-modify-write; schemas never change.
- Existing data, file, sharing and `open_file_manager` tools.

App-only:

- `open_agent_contacts_home`: native global entrypoint.
- `search_agent_contacts`: native composer mentions.
- `send_agent_contact_message`, `set_contact_identifier`, `set_contact_status`.
- `prepare_agent_invitation`, `match_agent_invitations`, `create_agent_invitation`, `prepare_standing_agent_invitation`.
- `end_agent_contact`.
- `get_fulcra_settings`, `update_fulcra_settings`, `get_contact_preferences`,
  `set_contact_preferences`, `get_message_check_status` (see [settings](fulcra-settings.md)).

Skills must reproduce the app-only invitation, matching and preference rules with
the generic tools; [Agents I Know](contacts-app.md) describes them.

## Channel prefixes

New channels and shares use the `connect-our-agents` prefix. The server and UI
also accept `connect-agents-with-anyone`, including mixed peers. The pinned SDK's
connection resolver only knows the older name, so `send_agent_message` translates
it in a local discovery copy and rechecks live grants before writing.

## Stored markers

Preserve contact labels and conversion provenance under the [description format](channel-description-format.md), reading both legacy and named fields. Keep the
`/connect-our-agents/connection-checks/` state root and legacy `Mesh Outbox` names
unchanged. They are wire identifiers shared with the plugin and with released
`fulcra-mesh` data.
