"""Shared suffix boundaries, including actual Python catalog -> JS UI flow."""
import json
from pathlib import Path
import subprocess

import pytest

from fulcra_mcp.contact_identifier import parse_contact_identifier, write_contact_identifier
from fulcra_mcp.tools import _slim_entry

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / 'tests/fixtures/contact-identifier-whitespace.json').read_text())


@pytest.mark.parametrize('case', CASES, ids=lambda c: repr(c['suffix']))
def test_suffix_boundaries(case):
    for suffix in [case['suffix'], ' \t' + case['suffix'] + '\r\n']:
        raw = 'Prose\n  folded. [mesh_identifier: "Trip"]' + suffix
        if case['valid']:
            assert parse_contact_identifier(raw) == 'Trip'
            assert write_contact_identifier(raw, 'Trip') == raw
        else:
            with pytest.raises(ValueError):
                parse_contact_identifier(raw)
            with pytest.raises(ValueError):
                write_contact_identifier(raw, 'New')


def test_normalized_catalog_reaches_ui():
    rows = []
    for case in [c for c in CASES if c['valid']]:
        raw = 'connect-agents-with-anyone channel\nProse\n  folded. [mesh_identifier: "Trip"]' + case['suffix']
        entry = {'id': 'Event/test', 'name': 'Connection',
                 'fulcra_userid': 'peer', 'categories': ['shared_type'], 'description': raw}
        rows.append({'entry': _slim_entry(entry), 'valid': case['valid']})
    script = r'''
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { discoverThreads } from './web/connections-discovery.js';
for (const { entry, valid } of JSON.parse(readFileSync(0, 'utf8'))) {
  Object.assign(entry, JSON.parse(readFileSync('./tests/fixtures/connection-schema.json', 'utf8')));
  const { threads } = await discoverThreads({ async callServerTool({ name }) {
    return { structuredContent: { result: name === 'get_data_catalog'
      ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': [entry] })
      : 'Shares: ' + JSON.stringify({ own_fulcra_userid: 'own', incoming: [{sharing_fulcra_userid:'peer',grant_type:'user',datashare_name:'connect-agents-with-anyone: test',file_paths:[],file_history_paths:[],data_types:[entry.id]}], outgoing: [] }) } };
  } });
  assert.equal(threads.length, 1);
  assert.equal(threads[0].identifier, valid ? 'Trip' : undefined);
  assert.equal(threads[0].peer, 'peer');
  assert.equal(threads[0].sources[0].id, entry.id);
}
'''
    subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT,
                   input=json.dumps(rows), text=True, check=True, capture_output=True)


@pytest.mark.parametrize('raw,expected', [
    ('  Ordinary\n\t description  ', 'Ordinary description'),
    ('  Ordinary\n [mesh_identifier: "Trip"]  ', 'Ordinary [mesh_identifier: "Trip"]'),
])
def test_generic_catalog_description_normalization(raw, expected):
    # The same folding applies to every catalog type, connection channels included.
    assert _slim_entry({'id': 'heart_rate', 'description': raw})['description'] == expected
