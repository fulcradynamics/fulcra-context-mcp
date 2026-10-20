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
                assert initialized.serverInfo.version == '1.16.3'
                icons = initialized.serverInfo.icons
                assert icons and icons[0].src == 'https://mcp.fulcradynamics.com/icon.png'
                assert icons[0].mimeType == 'image/png' and icons[0].sizes == ['256x256']
                tools = {t.name:t for t in (await client.list_tools()).tools}
                assert {'get_contact_preferences', 'set_contact_preferences'} <= tools.keys()
                for name in ('prepare_agent_invitation', 'match_agent_invitations'):
                    assert tools[name].meta['ui']['visibility'] == ['app', 'model']
                    assert tools[name].annotations.readOnlyHint is False
                assert tools['prepare_agent_invitation'].inputSchema['required'] == ['data_type']
                assert tools['prepare_agent_invitation'].inputSchema['properties']['open_invitation']['default'] is False
                assert tools['match_agent_invitations'].inputSchema['properties'] == {}
                assert tools['fulcra_settings_update'].annotations.readOnlyHint is False
                assert tools['fulcra_settings_read'].meta['ui']['visibility'] == ['app', 'model']
                rejected = await client.call_tool('fulcra_settings_update', {'set': {'interval': 30}})
                assert rejected.isError
                schema = tools['agent_connection_send'].inputSchema
                assert {'sender','body','mid','outbox','peer_userid'} <= set(schema['required'])
                assert 'peer_agent' not in schema['properties']
                assert 'expected_peer_userids' in schema['properties']
                assert 'target_peer_userid' in tools['send_agent_message'].inputSchema['properties']
                assert 'expected_peer_userids' in tools['get_contact_preferences'].inputSchema['properties']
                assert 'send_agent_message' in tools
                end_contact = tools['end_agent_contact']
                assert end_contact.meta['ui']['visibility'] == ['app']
                assert end_contact.annotations.readOnlyHint is False
                assert end_contact.annotations.destructiveHint is True
                assert end_contact.inputSchema['properties']['archive']['default'] is False
                assert 'fulcra_userid' in tools['open_file_manager'].inputSchema['properties']
                files_uri = tools['open_file_manager'].meta['ui']['resourceUri']
                assert files_uri == 'ui://fulcra/file-manager/v3.html'
                files_html = (await client.read_resource(files_uri)).contents[0].text
                assert 'currentOwner' in files_html and 'Shared files — read-only' in files_html
                status = tools['set_contact_status']
                assert set(status.inputSchema['required']) == {'data_type', 'peer_userid', 'attention', 'reason'}
                assert 'assessed_at' not in status.inputSchema['properties']
                assert status.annotations.readOnlyHint is False
                assert status.meta['ui']['visibility'] == ['model']
                assert 'start_time' not in tools['get_records'].inputSchema['required']
                for name, uri, marker in (
                    ('fulcra_open', 'ui://fulcra/contacts/v65.html', 'global'),
                    ('agent_contacts_open', 'ui://fulcra/contacts/threads/v65.html', 'threads'),
                    ('agent_contact_open', 'ui://fulcra/contacts/thread/v65.html', 'thread'),
                ):
                    assert tools[name].icons == icons
                    opened = await client.call_tool(name, {})
                    assert not opened.isError
                    text = (await client.read_resource(uri)).contents[0].text
                    assert f'name="connection-presentation" content="{marker}"' in text
                    assert 'selected_contact' in text and 'Messages loading; displayed history is not yet available.' in text
                    assert 'id="message-back"' not in text
                    assert 'conversation-pane' in text and 'rail-content' in text and '--composer-clearance: 48px' in text
                    for value in ('id="onboarding-thread"', 'id="onboarding-advanced"', 'fulcra_check_status',
                                  'Set up automatic checking', 'set-up-agent-contacts'):
                        assert value in text, value
                    for value in ('ack-status', r'Couldn\u2019t confirm messages read',
                                  'The read state is kept and no duplicate will be sent.'):
                        assert value in text, value
                    for value in ('open_invitation=true', 'template is never shared', 'use the invite skill', 'connect-agents-with-anyone', 'connect-our-agents', 'Converted from legacy connection', 'Update connection', 'chat about old messages',
                                  'connection_setup_session', 'Open original setup session', 'Copy handoff for original session',
                                  'contact_status', 'Not assessed', 'Needs attention', 'match_agent_invitations', 'pending-assist',
                                  'Load more history', 'Showing messages through', 'thread-preview', '--message-scroll-clearance: 50dvh',
                                  'end-contact-dialog', 'End contact', 'Also archive your messages',
                                  'debug-preview', 'Reset to live', 'Debug preview active',
                                  'association unverified', 'viewing-agent', 'expected_peer_userids',
                                  'Open file in ', 'Referenced version (unverified)'):
                        assert value in text, value
                assert not any('mesh' in name or 'aicq' in name for name in tools)
                print(f'Installed wheel stdio smoke passed: {installed}; {len(tools)} tools; Event schema and all three v65 entrypoints/resources verified.')


if __name__ == '__main__':
    asyncio.run(main())
