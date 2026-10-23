from fulcra_mcp.main import mcp


def test_bare_mention_routes_to_onboarding_without_write_consent():
    assert 'Bare @Fulcra: use set-up-agent-contacts' in mcp.instructions
    assert "The user's explicit task wins" in mcp.instructions
    assert 'not sends/shares/edits' in mcp.instructions
