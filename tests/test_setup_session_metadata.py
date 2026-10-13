"""Optional description metadata survives catalog and label maintenance."""
from fulcra_mcp.mesh_identifier import (
    normalize_catalog_description, parse_mesh_identifier, write_mesh_identifier,
)


def test_setup_session_and_conversion_preserved_by_label_maintenance():
    prefix = ('connect-agents-with-anyone channel: approved context\n'
              '[connection_setup_session: "codex://threads/00000000-0000-0000-0000-000000000001"]\n'
              'converted_from_mesh: []\n')
    description = prefix + '[mesh_identifier: "Trip"]'
    assert normalize_catalog_description(description) == description
    updated = write_mesh_identifier(description, 'Offsite')
    assert updated.startswith(prefix)
    assert parse_mesh_identifier(updated) == 'Offsite'
    assert write_mesh_identifier(updated, 'Offsite') == updated
