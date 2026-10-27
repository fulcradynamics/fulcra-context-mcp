"""Exact single-type invitation guards apply independently of grant names."""
import json

import pytest
from fastmcp import Client

from test_agent_invitations import api, handshake, invitations, OUT, STATE, PEER


@pytest.mark.parametrize('target', [OUT])
@pytest.mark.parametrize('name', ['ordinary export', 'connect-our-agents invitation'])
def test_exact_targeted_grants_stop_preparation_without_writes(api, target, name):
    invitations.prepare(api, OUT)
    api.update_data_type.reset_mock()
    api.get_datashares.return_value = [dict(
        share_all_data=False, fulcra_data_types=[target], datashare_name=name,
        permissions=[{'allowed_fulcra_userid': PEER}])]
    with pytest.raises(ValueError, match='targeted'):
        invitations.prepare(api, OUT)
    api.update_data_type.assert_not_called()
    api.create_datashare.assert_not_called()


@pytest.mark.parametrize('open_invitation', [False, True])
def test_non_protocol_exact_outbox_grant_stops_matching(api, open_invitation):
    code = invitations.prepare(api, OUT, open_invitation=open_invitation)['code']
    handshake(api, code)
    if open_invitation:
        for rows in api.rows.values():
            rows[0]['topic'] = 'open_invitation ' + code
    before = api.catalog[0]['description']
    api.get_datashares.return_value = [dict(
        share_all_data=False, fulcra_data_types=[OUT], datashare_name='ordinary export',
        permissions=[{'allowed_fulcra_userid': PEER}])]
    api.update_data_type.reset_mock()
    assert not any(r['status'] == 'matched' for r in invitations.match(api)['results'])
    assert api.catalog[0]['description'] == before
    api.update_data_type.assert_not_called()
    api.create_datashare.assert_not_called()


async def test_check_configuration_advertised_as_owned():
    from fulcra_mcp.main import mcp
    async with Client(mcp) as client:
        tool = next(t for t in await client.list_tools() if t.name == 'get_message_check_status')
    assert tool.description is not None
    assert 'owned check configuration' in tool.description
    assert 'private check configuration' not in tool.description
