import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readConversation } from './conversation.js';
import { discoverThreads } from './meshes.js';

test('refresh reuses discovery, retains failed-source last-good records as stale and removes revoked sources', async () => {
  const h = harness({ rows: { [`me:${own.id}`]: [{ id: 'one', note: 'good' }], [`peer:${peer.id}`]: [{ id: 'two', note: 'peer good' }] } });
  let discovery = await discoverThreads(h.app);
  const previous = await readConversation(h.app, { peer: 'peer' }, range, () => true, { discovery, now: '2026-01-10T12:00:00Z' });
  const failing = { callServerTool: async call => {
    assert.equal(call.name, 'get_records', 'refresh must reuse supplied discovery');
    if (call.arguments.fulcra_userid) throw new Error('offline');
    return text(`Records for ${own.id} from start to end: []`);
  } };
  const result = await readConversation(failing, { peer: 'peer' }, range, () => true, { discovery, previous });
  assert.equal(result.messages.length, 1);
  assert.equal(result.messages[0].record.note, 'peer good');
  assert.equal(result.messages[0].stale, true);
  assert.equal(result.messages[0].last_success_at, '2026-01-10T12:00:00Z');
  assert.match(result.warnings.join(' '), /Stale.*not verified current/);
  discovery = { ...discovery, threads: discovery.threads.map(t => ({ ...t, sources: t.sources.filter(s => s.direction === 'Outgoing') })) };
  const revoked = await readConversation(failing, { peer: 'peer' }, range, () => true, { discovery, previous: result });
  assert.deepEqual(revoked.messages, []);
});

const own = { id: 'MomentAnnotation/own', name: 'Mesh Outbox Same name' };
const peer = { id: 'MomentAnnotation/peer', name: 'Mesh Outbox Same name', fulcra_userid: 'peer' };
const outgoing = (id = own.id, recipient = 'peer') => ({ data_types: [id], with_user_ids: [recipient], share_all_data: false });
const range = { start_time: '2026-01-01T00:00:00.000Z', end_time: '2026-02-01T00:00:00.000Z' };
const text = result => ({ structuredContent: { result } });
function harness({ catalog = [own, peer], shares = { own_fulcra_userid: 'me', outgoing: [outgoing()], incoming: [] }, rows = {}, fail = [], truncated = [] } = {}) {
  const calls = [];
  const app = { async callServerTool(call) {
    calls.push(call);
    if (fail.includes(call.name)) throw new Error('offline');
    if (call.name === 'get_data_catalog') return text('Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': catalog }));
    if (call.name === 'list_shares') return text('Shares: ' + JSON.stringify(shares));
    assert.equal(call.name, 'get_records', 'no writes, sends or acknowledgement tools');
    const key = `${call.arguments.fulcra_userid ?? 'me'}:${call.arguments.data_type}`;
    if (fail.includes(key)) return { isError: true };
    return text(`Records for ${call.arguments.data_type} from start to end${truncated.includes(key) ? ' (showing the first 1 of 3)' : ''}: ${JSON.stringify(rows[key] ?? [])}`);
  } };
  return { app, calls, shares, catalog };
}

test('loads all deduplicated channels for exact peer, not other peers; chronological with original source', async () => {
  const second = { ...own, id: 'MomentAnnotation/second' };
  const h = harness({ catalog: [own, peer, peer, second, { ...peer, fulcra_userid: 'other' }], rows: {
    [`me:${own.id}`]: [{ recorded_at: '2026-01-02T00:00:00Z', note: 'outgoing' }],
    [`me:${second.id}`]: [{ recorded_at: '2026-01-03T00:00:00Z', note: 'second outgoing' }],
    [`peer:${peer.id}`]: [{ recorded_at: '2026-01-01T00:00:00Z', note: '{"v":1,"body":"unacked incoming","to_user":"other"}' }],
  } });
  h.shares.outgoing.push(outgoing(second.id), outgoing());
  const result = await readConversation(h.app, { peer: 'peer' }, range);
  assert.deepEqual(result.warnings, []);
  assert.deepEqual(result.messages.map(m => m.direction), ['Incoming', 'Outgoing', 'Outgoing']);
  assert.deepEqual(result.messages.map(m => m.source), [
    { id: peer.id, name: peer.name, fulcra_userid: 'peer' }, { id: own.id, name: own.name, fulcra_userid: 'me' }, { id: second.id, name: second.name, fulcra_userid: 'me' },
  ]);
  assert.equal(h.calls.length, 5);
  for (const c of h.calls.slice(2)) assert.deepEqual({ start_time: c.arguments.start_time, end_time: c.arguments.end_time }, range);
});

test('every load refreshes discovery, adding new channels and removing newly unsafe own channels', async () => {
  const h = harness({ catalog: [own] });
  assert.match((await readConversation(h.app, { peer: 'peer' }, range)).warnings.join(' '), /missing incoming/i);
  h.catalog.push(peer);
  assert.deepEqual((await readConversation(h.app, { peer: 'peer' }, range)).warnings, []);
  h.shares.outgoing.push(outgoing(own.id, 'other'));
  const result = await readConversation(h.app, { peer: 'peer' }, range);
  assert.match(result.warnings.join(' '), /omitted.*missing outgoing/is);
  assert.equal(h.calls.at(-1).arguments.fulcra_userid, 'peer');
  assert.equal(h.calls.filter(c => c.name === 'list_shares').length, 3);
});

test('incoming-only/outgoing-only and empty complete reads remain usable', async () => {
  assert.deepEqual(await readConversation(harness().app, { peer: 'peer' }, range), { messages: [], warnings: [] });
  for (const catalog of [[own], [peer]]) {
    const result = await readConversation(harness({ catalog }).app, { peer: 'peer' }, range);
    assert.deepEqual(result.messages, []);
    assert.match(result.warnings.join(' '), /Conversation incomplete — missing/);
  }
});

test('same type under different owners remains distinct', async () => {
  const h = harness({ catalog: [own, { ...peer, id: own.id }, { ...peer, id: own.id, fulcra_userid: 'other' }], rows: {
    [`me:${own.id}`]: [{ note: 'mine' }], [`peer:${own.id}`]: [{ note: 'theirs' }],
  } });
  const result = await readConversation(h.app, { peer: 'peer' }, range);
  assert.equal(result.messages.length, 2);
  assert.deepEqual(result.messages.map(m => m.source.fulcra_userid), ['me', 'peer']);
});

test('per-source failure and truncation retain other results and provenance in warnings', async () => {
  const h = harness({ fail: [`me:${own.id}`], rows: { [`peer:${peer.id}`]: [{ note: 'preserved' }] }, truncated: [`peer:${peer.id}`] });
  const result = await readConversation(h.app, { peer: 'peer' }, range);
  assert.equal(result.messages[0].record.note, 'preserved');
  assert.match(result.warnings.join(' '), /Could not load messages — Outgoing \(me \/ MomentAnnotation\/own\)/);
  assert.match(result.warnings.join(' '), /Partial result — Incoming \(peer \/ MomentAnnotation\/peer\)/);
  const failed = await readConversation(harness({ fail: [`me:${own.id}`, `peer:${peer.id}`] }).app, { peer: 'peer' }, range);
  assert.equal(failed.messages.length, 0);
  assert.equal(failed.warnings.length, 2);
});

for (const tool of ['get_data_catalog', 'list_shares']) test(`${tool} failure never reads cached channels`, async () => {
  const h = harness({ fail: [tool] });
  await assert.rejects(readConversation(h.app, { peer: 'peer' }, range), /discovery/i);
  assert.equal(h.calls.filter(c => c.name === 'get_records').length, 0);
});

test('disappeared peer does not fall back to stale channels', async () => {
  const h = harness({ catalog: [] });
  await assert.rejects(readConversation(h.app, { peer: 'peer' }, range), /no longer available/i);
  assert.equal(h.calls.filter(c => c.name === 'get_records').length, 0);
});

test('stale discovery starts no reads; stale records return no context', async () => {
  const h = harness();
  assert.equal(await readConversation(h.app, { peer: 'peer' }, range, () => false), undefined);
  assert.equal(h.calls.filter(c => c.name === 'get_records').length, 0);
  let checks = 0;
  assert.equal(await readConversation(h.app, { peer: 'peer' }, range, () => ++checks === 1), undefined);
});
