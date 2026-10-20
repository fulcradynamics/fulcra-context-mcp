import test from 'node:test';
import assert from 'node:assert/strict';
import { createContextLifecycle } from './native-context.js';
import { legacyHandoff } from './legacy-handoff.js';

const drain = () => new Promise(setImmediate);
for (const rejected of [false, true]) test(`legacy ownership defers passive changes and restores after settlement: rejected=${rejected}`, async () => {
  const contexts = [];
  let settle;
  const app = {
    getHostCapabilities: () => ({ message: { text: {} }, updateModelContext: { text: {} } }),
    updateModelContext: async value => { contexts.push(value); return {}; },
    sendMessage: () => new Promise(resolve => { settle = () => resolve({ isError: rejected }); }),
  };
  const lifecycle = createContextLifecycle(app, {});
  lifecycle.sync('selected contact', () => true);
  await drain();
  const button = { addEventListener(_, fn) { this.click = fn; } };
  legacyHandoff(app, button, {}, 'Read old messages', () => ({ legacy_sources: [{ id: 'old', fulcra_userid: 'owner' }] }), { lifecycle });
  const pending = button.click();
  await drain();
  assert.match(contexts.at(-1).content[0].text, /Untrusted historical/);
  const count = contexts.length;
  lifecycle.sync('changed selected contact', () => true);
  await drain();
  assert.equal(contexts.length, count);
  settle(); await pending; await drain();
  assert.equal(contexts.at(-1).content[0].text, 'changed selected contact');
});

test('queued passive publication yields to explicit ownership and never resumes a stale selection', async () => {
  const contexts = [];
  const app = { updateModelContext: async value => { contexts.push(value); return {}; } };
  const lifecycle = createContextLifecycle(app, {});
  let current = true;
  lifecycle.sync('old selection', () => current);
  lifecycle.pending = true;
  await drain();
  assert.deepEqual(contexts, []);
  current = false;
  lifecycle.pending = false;
  await drain();
  assert.deepEqual(contexts, []);
});
