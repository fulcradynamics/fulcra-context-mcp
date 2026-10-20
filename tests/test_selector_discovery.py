"""Actual public projection consumed by both native discovery implementations."""
import json
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from fulcra_mcp.tools import _slim_share
from fulcra_mcp.mentions import _thread_labels, CHANNEL_SCHEMA
from fulcra_mcp.contact_preferences import _check_private, update, NAME

ROOT = Path(__file__).resolve().parents[1]
OWN = '00000000-0000-4000-8000-000000000001'
PEER = '00000000-0000-4000-8000-000000000002'
TYPE = 'Event/00000000-0000-4000-8000-000000000003'
MISSING = object()
INVALID = [MISSING, None, TYPE, [None], [{}], [''], [' Event '], ['file:'],
           ['filehistory:relative'], [TYPE, 'file:']]


def project(selectors):
    raw = dict(share_all_data=False, datashare_name='connect-our-agents invitation',
               permissions=[{'allowed_fulcra_userid': PEER}])
    if selectors is not MISSING:
        raw['fulcra_data_types'] = selectors
    return _slim_share(raw)


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


@pytest.mark.parametrize('consumer', ['browser', 'mentions'])
@pytest.mark.parametrize('valid', [False, True])
@pytest.mark.parametrize('selectors', INVALID)
def test_unknown_outgoing_cannot_prove_absence_or_safe_audience(selectors, valid, consumer):
    browser, mentions = discover(([project([TYPE])] if valid else []) + [project(selectors)])
    if consumer == 'browser':
        assert browser['threads'] == []
        assert browser['pending'] == []
        assert browser['warnings']
    else:
        assert mentions == {}


@pytest.mark.parametrize('selectors', [[], ['file:/a'], ['filehistory:/a']])
@pytest.mark.parametrize('valid', [False, True])
def test_complete_non_event_grants_do_not_block_discovery(selectors, valid):
    browser, mentions = discover(([project([TYPE])] if valid else []) + [project(selectors)])
    assert len(browser['threads']) == int(valid)
    assert len(browser['pending']) == int(not valid)
    assert bool(mentions) is valid
    assert browser['warnings'] == []


def test_missing_projection_flag_is_unknown_even_with_exact_selector():
    share = project([TYPE])
    del share['selectors_complete']
    browser, mentions = discover([share])
    assert browser['threads'] == browser['pending'] == []
    assert browser['warnings']
    assert mentions == {}
    share.update(grant_type='user', sharing_fulcra_userid=PEER)
    browser, mentions = discover([share], incoming=True)
    assert browser['threads'] == []
    assert mentions == {}


@pytest.mark.parametrize('selectors', INVALID)
def test_unknown_incoming_cannot_establish_readable_channel(selectors):
    share = project(selectors)
    share.update(grant_type='user', sharing_fulcra_userid=PEER)
    browser, mentions = discover([share], incoming=True)
    assert browser['threads'] == []
    assert mentions == {}


@pytest.mark.parametrize('selectors', INVALID)
def test_raw_private_checker_rejects_same_unknown_selectors(selectors):
    raw = {'share_all_data': False}
    if selectors is not MISSING:
        raw['fulcra_data_types'] = selectors
    api = Mock()
    api.get_datashares.return_value = [raw]
    with pytest.raises(ValueError):
        _check_private(api, {'id': TYPE})
    api.get_fulcra_userid.return_value = OWN
    api.v1_catalog.return_value = [dict(id=TYPE, name=NAME, fulcra_userid=OWN,
        api_version='v1', description='unknown state must survive')]
    with pytest.raises(ValueError):
        update(api, {'acknowledge_messages': False})
    api.create_data_type.assert_not_called()
    api.update_data_type.assert_not_called()


@pytest.mark.parametrize('selectors', [[], ['file:/a'], ['filehistory:/a']])
def test_raw_private_checker_accepts_complete_non_event_grants(selectors):
    api = Mock()
    api.get_datashares.return_value = [dict(share_all_data=False, fulcra_data_types=selectors)]
    _check_private(api, {'id': TYPE})
