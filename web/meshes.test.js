import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadMeshes, parseMeshes } from './meshes.js';

test('only catalog groups compatible with get_records are readable', () => {
  const entry = { id: 'MomentAnnotation/id', name: 'Mesh Outbox' };
  assert.deepEqual(parseMeshes({ structuredContent: { result: 'Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types that cannot be queried (used only when recording data)': [entry] }) } }), []);
});

test('renders distinct returned outboxes as text with owner labels', async () => {
  const entry = { id: 'MomentAnnotation/00000000-0000-0000-0000-000000000001', name: 'Mesh Outbox <script>', fulcra_userid: 'peer' };
  const status = {};
  const rows = [];
  const list = { replaceChildren() {}, ownerDocument: { createElement: () => ({ addEventListener() {}, append(...parts) { this.textContent = parts.map(p => typeof p === 'string' ? p : p.textContent).join(''); } }) }, append: row => rows.push(row) };
  await loadMeshes({ callServerTool: async () => ({ structuredContent: { result: 'Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': [entry, entry] }) } }) }, status, list);
  assert.match(status.textContent, /1 mesh outbox/);
  assert.equal(rows.length, 1);
  assert.match(rows[0].textContent, /Mesh Outbox <script>.*peer/);
});

test('failed, malformed, and timed-out reads show errors, never zero', async () => {
  for (const result of [{ isError: true }, { content: [{ type: 'text', text: 'Error: unauthorized' }] }, { content: [{ type: 'text', text: 'Available data types, grouped by compatible tool: []' }] }, new Error('timeout')]) {
    const status = {};
    await loadMeshes({ callServerTool: async () => { if (result instanceof Error) throw result; return result; } }, status, { replaceChildren() {} });
    assert.match(status.textContent, /Could not load/);
    assert.doesNotMatch(status.textContent, /0 mesh/);
  }
});

test('opening loads real catalog tool result, including zero', async () => {
  const status = { textContent: '' };
  const list = { replaceChildren() {} };
  let resolve;
  const app = { callServerTool(request) {
    assert.deepEqual(request, { name: 'get_data_catalog', arguments: { name: 'Mesh Outbox' } });
    return new Promise(r => { resolve = r; });
  } };
  const pending = loadMeshes(app, status, list);
  assert.match(status.textContent, /Loading.*get_data_catalog/);
  resolve({ content: [{ type: 'text', text: 'Available data types, grouped by compatible tool: {}' }] });
  await pending;
  assert.match(status.textContent, /0 mesh outboxes/);
});
