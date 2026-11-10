"""Stable persisted names, not current product or tool terminology.

Keep historical channels readable alongside the renamed skill.
"""

IDENTIFIER_TOKEN = "[mesh_identifier"
LEGACY_OUTBOX_PATTERN = r"\bmesh outbox\b"
SHARE_NAME_PREFIX = ("connect-agents-with-anyone", "connect-our-agents")
CHANNEL_PREFIXES = tuple(f"{name} channel" for name in SHARE_NAME_PREFIX)

# Preserve stored provenance; current tools are advertised without historical aliases.
CONNECTION_GUIDANCE = (
    "Preserve contact labels and conversion provenance; read legacy and named fields. "
    "Do not migrate user data without explicit consent."
)
