import { test } from 'node:test';
import assert from 'node:assert/strict';
import { endContact } from './end-contact.js';

const thread = { peer: 'p', sources: [{ id: 'Event/out', direction: 'Outgoing' }, { id: 'Event/in', direction: 'Incoming', fulcra_userid: 'p' }] };
const app = results => ({ calls: [], async callServerTool(req) { this.calls.push(req.arguments); return { structuredContent: results.shift() }; } });

test('ends only own channels and passes the archive choice', async () => {
  const host = app([{ ended: true, archived: true }]);
  assert.deepEqual(await endContact(host, thread, true), { archived: 1 });
  assert.deepEqual(host.calls, [{ data_type: 'Event/out', peer_userid: 'p', archive: true }]);
});

test('unverified ending or archive is an error', async () => {
  await assert.rejects(endContact(app([{ ended: false, reason: 'A covering share remains.' }]), thread, false), /covering share remains/);
  await assert.rejects(endContact(app([{ ended: true, archived: false }]), thread, true), /archiving was not verified/);
});

test('ending reports remaining broader access without another approval', async () => {
  assert.deepEqual(await endContact(app([{ ended: true, broader_access_remains: true }]), thread, false),
    { archived: 0, broaderAccessRemains: true });
});
