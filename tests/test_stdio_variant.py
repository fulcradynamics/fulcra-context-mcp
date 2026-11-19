import json
import os
import sys
from unittest.mock import Mock

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import pytest
from pydantic import ValidationError

from fulcra_mcp import main
from fulcra_mcp.settings import Settings


@pytest.mark.parametrize('variant,server', [
    ('standard', 'mcp'), ('openai', 'openai_mcp'), ('claude', 'claude_mcp'),
])
def test_stdio_selects_variant(monkeypatch, variant, server):
    monkeypatch.setenv('FULCRA_MCP_VARIANT', variant)
    monkeypatch.setattr(main, 'settings', Settings())
    runners = {}
    for name in ('mcp', 'openai_mcp', 'claude_mcp'):
        runners[name] = Mock()
        monkeypatch.setattr(main, name, runners[name])
    main.main()
    runners[server].run.assert_called_once_with()
    for name, runner in runners.items():
        if name != server:
            runner.run.assert_not_called()


def test_standard_default_and_invalid_variant(monkeypatch):
    monkeypatch.delenv('FULCRA_MCP_VARIANT', raising=False)
    assert Settings().fulcra_mcp_variant == 'standard'
    monkeypatch.setenv('FULCRA_MCP_VARIANT', 'unknown')
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize('variant', ['standard', 'openai', 'claude'])
async def test_variant_over_stdio(variant, tmp_path):
    # Only the backend is synthetic; exercise the real entrypoint and JSON wire.
    script = """
from unittest.mock import Mock
from fulcra_mcp import credentials, main
credentials.stdio_fulcra = Mock()
credentials.stdio_fulcra.get_user_info.return_value = {'test_account': 'stdio'}
main.main()
"""
    params = StdioServerParameters(
        command=sys.executable, args=['-c', script],
        env={**os.environ, 'FULCRA_ENVIRONMENT': 'stdio',
             'FULCRA_MCP_VARIANT': variant, 'HOME': str(tmp_path),
             'XDG_CONFIG_HOME': str(tmp_path)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {tool.name for tool in (await session.list_tools()).tools}
            assert 'get_user_info' in tools
            assert ('get_location' in tools) == (variant == 'standard')
            resources = (await session.list_resources()).resources
            contacts = next(r for r in resources if '/contacts/' in str(r.uri))
            result = await session.read_resource(contacts.uri)
            assert '<html' in result.contents[0].text.lower()
            account = await session.call_tool('get_user_info', {})
            assert not account.is_error
            assert json.loads(account.content[0].text.removeprefix('User information: ')) == {'test_account': 'stdio'}


@pytest.mark.parametrize('variant', ['standard', 'openai', 'claude'])
def test_http_keeps_all_routes(monkeypatch, tmp_path, variant):
    monkeypatch.setattr(main, 'settings', Settings(
        fulcra_environment='production', fulcra_mcp_variant=variant,
        state_path=tmp_path, port=4499,
    ))
    run = Mock()
    monkeypatch.setattr(main.uvicorn, 'run', run)
    main.main()
    assert run.call_args.args == (main.app,)
    assert {'/mcp', '/openai/mcp', '/claude/mcp'} <= {
        route.path for route in main.app.routes
    }
