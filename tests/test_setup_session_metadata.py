"""Optional description metadata survives catalog and label maintenance."""
from fulcra_mcp.contact_identifier import parse_contact_identifier, write_contact_identifier


def test_setup_session_and_conversion_preserved_by_label_maintenance():
    prefix = ('connect-agents-with-anyone channel: approved context\n'
              '[connection_setup_session: "codex://threads/00000000-0000-0000-0000-000000000001"]\n'
              'converted_from_mesh: []\n')
    description = prefix + '[mesh_identifier: "Trip"]'
    updated = write_contact_identifier(description, 'Offsite')
    assert updated.startswith(prefix)
    assert parse_contact_identifier(updated) == 'Offsite'
    assert write_contact_identifier(updated, 'Offsite') == updated
