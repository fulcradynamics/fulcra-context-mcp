"""Run with an isolated wheel installation's Python, never an editable checkout.

Only metadata, readiness tools and packaged resources are requested. No account
credentials or backend requests are needed. The child receives isolated HOME/XDG.
"""
import asyncio
import os
from pathlib import Path
import sys
import tempfile

import fulcra_mcp
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    installed = Path(fulcra_mcp.__file__).resolve()
    assert 'site-packages' in str(installed), installed
    with tempfile.TemporaryDirectory(prefix='wheel-smoke-') as home:
        env = {**os.environ, 'HOME': home, 'XDG_CONFIG_HOME': home,
               'FULCRA_ENVIRONMENT': 'stdio'}
        params = StdioServerParameters(command=str(Path(sys.executable).parent / 'fulcra-context-mcp'), env=env, cwd=home)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                initialized = await client.initialize()
                assert initialized.serverInfo.version == '1.5.0'
                tools = {t.name:t for t in (await client.list_tools()).tools}
                schema = tools['mesh_send'].inputSchema
                assert {'sender','body','mid','outbox','peer_userid'} <= set(schema['required'])
                assert 'peer_agent' not in schema['properties']
                assert 'send_agent_message' in tools
                status = tools['set_contact_status']
                assert set(status.inputSchema['required']) == {'data_type', 'peer_userid', 'attention', 'reason'}
                assert 'assessed_at' not in status.inputSchema['properties']
                assert status.annotations.readOnlyHint is False
                assert status.meta['ui']['visibility'] == ['model']
                assert 'start_time' not in tools['get_records'].inputSchema['required']
                for name, uri, marker in (
                    ('aicq_open', 'ui://fulcra/mesh/v32.html', 'global'),
                    ('mesh_threads_open', 'ui://fulcra/mesh/threads/v32.html', 'threads'),
                    ('mesh_conversation_open', 'ui://fulcra/mesh/thread/v32.html', 'thread'),
                ):
                    opened = await client.call_tool(name, {})
                    assert not opened.isError
                    text = (await client.read_resource(uri)).contents[0].text
                    assert f'name="mesh-presentation" content="{marker}"' in text
                    for value in ('connect-agents-with-anyone', 'Converted from mesh', 'Convert to Contact', 'chat about old messages',
                                  'connection_setup_session', 'Open original setup session', 'Copy handoff for original session',
                                  'contact_status', 'Not assessed', 'Needs attention'):
                        assert value in text, value
                print(f'Installed wheel stdio smoke passed: {installed}; {len(tools)} tools; Event schema and all three v32 entrypoints/resources verified.')


if __name__ == '__main__':
    asyncio.run(main())
