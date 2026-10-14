"""Stable persisted names, not current product or tool terminology.

Keep historical channels/checkpoints readable alongside the renamed skill.
"""

IDENTIFIER_TOKEN = "[mesh_identifier"
LEGACY_OUTBOX_PATTERN = r"\bmesh outbox\b"
CHECK_STATE_ROOT = "/agent/chatgpt/mesh-checks/"
SHARE_NAME_PREFIX = ("connect-agents-with-anyone", "connect-our-agents")
CHANNEL_PREFIXES = tuple(f"{name} channel" for name in SHARE_NAME_PREFIX)

# Translate tool references, never consent, audience, retry or acknowledgement rules.
FROZEN_SKILL_GUIDANCE = """
The packaged connect-our-agents skill retains historical tool references.
Use these currently advertised equivalents with unchanged arguments and safety rules:
mesh_send -> agent_connection_send; set_mesh_identifier -> set_contact_identifier;
aicq_settings_read -> fulcra_settings_read; aicq_settings_update -> fulcra_settings_update;
aicq_check_status -> fulcra_check_status. These are reference translations, not
additional tools or permission to send, retry, share, acknowledge or schedule.
Keep persisted mesh_identifier and converted_from_mesh markers and the
/agent/chatgpt/mesh-checks/ checkpoint path unchanged. Do not migrate user data.
"""
