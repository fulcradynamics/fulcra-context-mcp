"""Actual public share projection consumed by both native discovery implementations."""
import json
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from fulcra_mcp.tools import _slim_share
from fulcra_mcp.mentions import _thread_labels, CHANNEL_SCHEMA
from fulcra_mcp.contact_preferences import _check_state_shares

ROOT = Path(__file__).resolve().parents[1]
OWN = '00000000-0000-4000-8000-000000000001'
PEER = '00000000-0000-4000-8000-000000000002'
TYPE = 'Event/00000000-0000-4000-8000-000000000003'


def project(selectors):
    raw = dict(share_all_data=False, datashare_name='connect-our-agents invitation',
               permissions=[{'allowed_fulcra_userid': PEER}])
    return _slim_share({**raw, 'fulcra_data_types': selectors})


def discover(outgoing, incoming=False):
    entry = dict(id=TYPE, name='Contact', description='connect-our-agents channel', **CHANNEL_SCHEMA)
    if incoming:
        entry['fulcra_userid'] = PEER
    catalog = {'data types usable with: get_records': [entry]}
    shares = dict(own_fulcra_userid=OWN, outgoing=[] if incoming else outgoing,
                  incoming=outgoing if incoming else [])
    script = """
import { discoverThreads } from './web/connections-discovery.js';
let input = ''; for await (const chunk of process.stdin) input += chunk;
const {catalog, shares} = JSON.parse(input);
const result = await discoverThreads({callServerTool: async ({name}) => ({
  content: [{type: 'text', text: name === 'get_data_catalog'
    ? 'Available data types, grouped by compatible tool: ' + JSON.stringify(catalog)
    : 'Shares: ' + JSON.stringify(shares)}]})});
console.log(JSON.stringify(result));
"""
    result = subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT,
                            input=json.dumps(dict(catalog=catalog, shares=shares)),
                            text=True, capture_output=True, check=True)
    return json.loads(result.stdout), _thread_labels(catalog, shares)


@pytest.mark.parametrize('selectors', [[], ['file:/a'], ['filehistory:/a']])
@pytest.mark.parametrize('valid', [False, True])
def test_non_event_grants_do_not_block_discovery(selectors, valid):
    browser, mentions = discover(([project([TYPE])] if valid else []) + [project(selectors)])
    assert len(browser['threads']) == int(valid)
    assert len(browser['pending']) == int(not valid)
    assert bool(mentions) is valid
    assert browser['warnings'] == []


@pytest.mark.parametrize('selectors', [[], ['file:/a'], ['filehistory:/a']])
def test_raw_private_checker_accepts_non_event_grants(selectors):
    api = Mock()
    api.get_datashares.return_value = [dict(share_all_data=False, fulcra_data_types=selectors)]
    _check_state_shares(api, {'id': TYPE})
