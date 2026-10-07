import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadMeshes, parseMeshes } from './meshes.js';

const entry = (id, owner) => ({ id: `MomentAnnotation/${id}`, name: 'Mesh Outbox same name', ...(owner ? { fulcra_userid: owner } : {}) });
const grant = (id, peer = 'peer') => ({ data_types: [`MomentAnnotation/${id}`], with_user_ids: [peer], share_all_data: false });
const text = result => ({ structuredContent: { result } });
async function load(catalog, outgoing = [], own = 'me') {
  const rows = [], selections = [], calls = [], status = {};
  const list = { replaceChildren() {}, ownerDocument: { createElement: () => ({ addEventListener(_, fn) { this.click = fn; }, append(button) { this.button = button; } }) }, append: row => rows.push(row) };
  await loadMeshes({ async callServerTool(call) {
    calls.push(call);
    return text(call.name === 'get_data_catalog'
      ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': catalog })
      : 'Shares: ' + JSON.stringify({ own_fulcra_userid: own, outgoing, incoming: [] }));
  } }, status, list, thread => selections.push(thread));
  for (const row of rows) row.button.click();
  return { rows, selections, calls, status: status.textContent };
}

test('one exact peer row deduplicates both sides and multiple narrow channels; names do not group peers', async () => {
  const result = await load([entry('own'), entry('own'), entry('second'), entry('same', 'peer'), entry('same', 'peer'), entry('same', 'other')], [grant('own'), grant('own'), grant('second')]);
  assert.match(result.status, /2 threads/);
  assert.deepEqual(result.rows.map(r => r.button.textContent), ['other', 'peer']);
  assert.deepEqual(result.selections.map(t => t.peer), ['other', 'peer']);
  assert.equal(result.selections[1].sources.length, 3);
  assert.deepEqual(result.calls.map(c => c.name), ['get_data_catalog', 'list_shares']);
});

test('only catalog groups compatible with get_records are readable', () => {
  assert.deepEqual(parseMeshes(text('Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types that cannot be queried (used only when recording data)': [entry('x')] }))), []);
});

test('orphans and self do not become threads; broad/mixed grants cannot hide behind a narrow grant', async () => {
  for (const extra of [
    { ...grant('own'), with_user_ids: ['peer', 'other'] },
    { ...grant('own'), data_types: ['MomentAnnotation/own', 'StepCount'] },
    { share_all_data: true },
    { ...grant('own'), with_group_ids: ['group'] },
    { ...grant('own'), file_paths: ['/'] },
    grant('own', 'other'),
  ]) {
    const result = await load([entry('own'), entry('orphan'), entry('self', 'me'), entry('incoming', 'peer')], [grant('own'), extra, grant('self', 'me')]);
    assert.deepEqual(result.selections.map(t => t.peer), ['peer']);
    assert.equal(result.selections[0].sources.length, 1);
    assert.match(result.status, /3 own outboxes omitted/);
    assert.match(result.selections[0].warnings.join(' '), /missing outgoing/i);
  }
});

test('outgoing-only and incoming-only are usable, with explicit missing-side notices', async () => {
  const result = await load([entry('own'), entry('incoming', 'other')], [grant('own')]);
  assert.deepEqual(result.selections.map(t => t.peer), ['other', 'peer']);
  assert.match(result.selections[0].warnings.join(' '), /missing outgoing/i);
  assert.match(result.selections[1].warnings.join(' '), /missing incoming/i);
  assert.equal((await load([])).status, 'get_data_catalog/list_shares completed — 0 threads returned.');
});

test('failed, malformed, and timed-out discovery shows errors, never zero', async () => {
  for (const result of [{ isError: true }, text('Error: unauthorized'), text('Available data types, grouped by compatible tool: []'), new Error('timeout')]) {
    const status = {};
    await loadMeshes({ callServerTool: async () => { if (result instanceof Error) throw result; return result; } }, status, { replaceChildren() {} });
    assert.match(status.textContent, /Could not load/);
    assert.doesNotMatch(status.textContent, /0 threads/);
  }
  assert.match((await load([entry('own')], [grant('own')], undefined)).status, /threads/);
  assert.match((await load([entry('own')], [grant('own')], '')).status, /Could not load/);
});
