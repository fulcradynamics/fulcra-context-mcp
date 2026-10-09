"""Shared suffix boundaries, including actual Python catalog -> JS UI flow."""
import json
from pathlib import Path
import subprocess

import pytest

from fulcra_mcp.mesh_identifier import parse_mesh_identifier, write_mesh_identifier
from fulcra_mcp.tools import _slim_entry

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / 'tests/fixtures/mesh-identifier-whitespace.json').read_text())


@pytest.mark.parametrize('case', CASES, ids=lambda c: repr(c['suffix']))
def test_suffix_boundaries(case):
    for suffix in [case['suffix'], ' \t' + case['suffix'] + '\r\n']:
        raw = 'Prose\n  folded. [mesh_identifier: "Trip"]' + suffix
        normalized = _slim_entry({'id': 'MomentAnnotation/test', 'description': raw})['description']
        if case['valid']:
            assert parse_mesh_identifier(raw) == 'Trip'
            assert parse_mesh_identifier(normalized) == 'Trip'
            assert write_mesh_identifier(raw, 'Trip') == raw
        else:
            assert normalized == raw  # Never repair malformed reserved metadata.
            for description in [raw, normalized]:
                with pytest.raises(ValueError):
                    parse_mesh_identifier(description)
                with pytest.raises(ValueError):
                    write_mesh_identifier(description, 'New')


def test_normalized_catalog_reaches_ui_without_repair():
    rows = []
    for case in CASES:
        raw = 'Prose\n  folded. [mesh_identifier: "Trip"]' + case['suffix']
        entry = {'id': 'MomentAnnotation/test', 'name': 'Mesh Outbox',
                 'fulcra_userid': 'peer', 'categories': ['shared_type'], 'description': raw}
        rows.append({'entry': _slim_entry(entry), 'valid': case['valid']})
    script = r'''
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { loadMeshes } from './web/meshes.js';
for (const { entry, valid } of JSON.parse(readFileSync(0, 'utf8'))) {
  const rows = [], selected = [];
  const list = { replaceChildren() {}, append(row) { rows.push(row); },
    ownerDocument: { createElement: () => ({
      addEventListener(_, fn) { this.click = fn; }, append(button) { this.button = button; }
    }) } };
  await loadMeshes({ async callServerTool({ name }) {
    return { structuredContent: { result: name === 'get_data_catalog'
      ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': [entry] })
      : 'Shares: ' + JSON.stringify({ own_fulcra_userid: 'own', incoming: [], outgoing: [] }) } };
  } }, {}, list, thread => selected.push(thread));
  assert.equal(rows.length, 1);
  assert.equal(rows[0].button.textContent, valid ? 'Trip (peer)' : 'peer');
  rows[0].button.click();
  assert.equal(selected[0].peer, 'peer');
  assert.equal(selected[0].sources[0].id, entry.id);
}
'''
    subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT,
                   input=json.dumps(rows), text=True, check=True, capture_output=True)


@pytest.mark.parametrize('raw,expected', [
    ('  Ordinary\n\t description  ', 'Ordinary description'),
    ('  Ordinary\n [mesh_identifier: bad]  ', '  Ordinary\n [mesh_identifier: bad]  '),
    ('  Ordinary\n [mesh_identifier "Trip"]  ', '  Ordinary\n [mesh_identifier "Trip"]  '),
])
def test_generic_catalog_description_normalization(raw, expected):
    # This normalization applies to all catalog types, not just mesh outboxes.
    assert _slim_entry({'id': 'heart_rate', 'description': raw})['description'] == expected
