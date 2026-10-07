import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readConversation } from './conversation.js';

const own = { id: 'MomentAnnotation/own', name: 'Mesh Outbox Own' };
const peer = { id: 'MomentAnnotation/peer', name: 'Mesh Outbox Unrelated name', fulcra_userid: 'peer' };
const outgoing = (id = own.id, recipient = 'peer') => ({ data_types: [id], with_user_ids: [recipient], share_all_data: false });
const incoming = (id = peer.id, owner = 'peer') => ({ data_types: [id], sharing_fulcra_userid: owner, grant_type: 'user', share_all_data: false });
const range = { start_time: '2026-01-01T00:00:00.000Z', end_time: '2026-02-01T00:00:00.000Z' };
const text = value => ({ structuredContent: { result: value } });
function harness({ catalog = [own, peer], shares = { own_fulcra_userid: 'me', outgoing: [outgoing()], incoming: [incoming()] }, rows = {}, fail = [], truncated = [] } = {}) {
  const calls = [];
  const app = { async callServerTool(call) {
    calls.push(call);
    if (fail.includes(call.name)) throw new Error('offline');
    if (call.name === 'get_data_catalog') return text('Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': catalog }));
    if (call.name === 'list_shares') return text('Shares: ' + JSON.stringify(shares));
    assert.equal(call.name, 'get_records', 'no sends or acknowledgement tools');
    const key = `${call.arguments.fulcra_userid ?? 'me'}:${call.arguments.data_type}`;
    if (fail.includes(key)) return { isError: true };
    return text(`Records for ${call.arguments.data_type} from start to end${truncated.includes(key) ? ' (showing the first 1 of 3)' : ''}: ${JSON.stringify(rows[key] ?? [])}`);
  } };
  return { app, calls, shares, catalog };
}

for (const selected of [own, peer]) test(`pairs from ${selected.fulcra_userid ? 'shared' : 'own'} selection without any acknowledgement`, async () => {
  const h = harness({ rows: {
    [`me:${own.id}`]: [{ recorded_at: '2026-01-02T00:00:00Z', note: 'outgoing' }],
    [`peer:${peer.id}`]: [{ recorded_at: '2026-01-01T00:00:00Z', note: JSON.stringify({ v: 1, kind: 'reply', body: 'unacked incoming' }) }],
  } });
  const result = await readConversation(h.app, selected, range);
  assert.deepEqual(result.warnings, []);
  assert.deepEqual(result.messages.map(m => m.direction), ['Incoming', 'Outgoing']);
  assert.deepEqual(result.messages.map(m => m.source), [peer, own]);
  assert.match(result.messages[0].record.note, /unacked/);
  assert.equal(h.calls.length, 4);
  assert.deepEqual(h.calls.slice(0, 2).map(c => [c.name, c.arguments]), [['get_data_catalog', { name: 'Mesh Outbox' }], ['list_shares', { direction: 'both' }]]);
  for (const c of h.calls.slice(2)) assert.deepEqual({ start_time: c.arguments.start_time, end_time: c.arguments.end_time }, range);
});

test('refresh discovers a newly shared return channel on the next load', async () => {
  const h = harness();
  h.shares.incoming = [];
  h.catalog.splice(1);
  assert.match((await readConversation(h.app, own, range)).warnings.join(' '), /incomplete/i);
  h.shares.incoming.push(incoming());
  h.catalog.push(peer);
  assert.deepEqual((await readConversation(h.app, own, range)).warnings, []);
  assert.equal(h.calls.filter(c => c.name === 'list_shares').length, 2);
});

for (const [name, change] of [
  ['missing peer', h => { h.shares.outgoing = []; }],
  ['ambiguous peer', h => { h.shares.outgoing.push(outgoing(own.id, 'other')); }],
  ['missing return', h => { h.shares.incoming = []; }],
  ['ambiguous return', h => { h.catalog.push({ ...peer, id: 'MomentAnnotation/second' }); h.shares.incoming.push(incoming('MomentAnnotation/second')); }],
  ['catalog owner mismatch', h => { h.catalog[1] = { ...peer, fulcra_userid: 'other' }; }],
  ['catalog type mismatch', h => { h.catalog[1] = { ...peer, id: 'MomentAnnotation/other' }; }],
  ['group incoming', h => { h.shares.incoming[0].group_id = 'group'; }],
  ['group outgoing', h => { h.shares.outgoing[0].with_group_ids = ['group']; }],
  ['all data', h => { h.shares.incoming[0].share_all_data = true; }],
  ['multiple recipients', h => { h.shares.outgoing[0].with_user_ids.push('other'); }],
  ['broad types', h => { h.shares.incoming[0].data_types.push('StepCount'); }],
  ['files included', h => { h.shares.outgoing[0].file_paths = ['/']; }],
]) test(`${name}: selected only, explicit incomplete warning`, async () => {
  const h = harness({ catalog: [own, peer], rows: { [`me:${own.id}`]: [{ note: 'selected survives' }] } });
  change(h);
  const result = await readConversation(h.app, own, range);
  assert.match(result.warnings.join(' '), /incomplete|unavailable/i);
  assert.equal(result.messages[0].record.note, 'selected survives');
  assert.deepEqual(h.calls.filter(c => c.name === 'get_records').map(c => c.arguments.data_type), [own.id]);
});

test('shared selection with ambiguous own channel is not merged', async () => {
  const h = harness({ catalog: [own, peer, { ...own, id: 'MomentAnnotation/second' }] });
  h.shares.outgoing.push(outgoing('MomentAnnotation/second'));
  const result = await readConversation(h.app, peer, range);
  assert.match(result.warnings.join(' '), /ambiguous/i);
  assert.deepEqual(h.calls.filter(c => c.name === 'get_records').map(c => c.arguments.fulcra_userid), ['peer']);
});

test('shared selection cannot pair an own outbox with multiple direct peers', async () => {
  const h = harness();
  h.shares.outgoing.push(outgoing(own.id, 'other'));
  const result = await readConversation(h.app, peer, range);
  assert.match(result.warnings.join(' '), /ambiguous/i);
  assert.equal(h.calls.filter(c => c.name === 'get_records').length, 1);
});

for (const selected of [own, peer]) {
  for (const [label, extra] of Object.entries({
    'multiple recipients': { ...outgoing(), with_user_ids: ['peer', 'other-user'] },
    'multiple types': { ...outgoing(), data_types: [own.id, 'MomentAnnotation/other'] },
    'all data': { ...outgoing(), share_all_data: true, data_types: [] },
    'group': { ...outgoing(), with_user_ids: [], with_group_ids: ['group'] },
  })) test(`mixed narrow and ${label} grants do not pair ${selected.name}`, async () => {
    const { app, calls } = harness({ shares: { own_fulcra_userid: 'me', outgoing: [outgoing(), extra], incoming: [incoming()] } });
    const result = await readConversation(app, selected, range);
    assert.equal(calls.filter(c => c.name === 'get_records').length, 1);
    assert.match(result.warnings.join(' '), /incomplete|unavailable/i);
  });
}

test('same type ID in distinct owners stays distinct; duplicate grants do not add ambiguity', async () => {
  const same = { ...peer, id: own.id };
  const h = harness({ catalog: [own, same, { ...same, fulcra_userid: 'stranger' }], rows: { [`me:${own.id}`]: [{ note: 'mine' }], [`peer:${own.id}`]: [{ note: 'theirs' }] } });
  h.shares.incoming = [incoming(own.id), incoming(own.id)];
  h.shares.outgoing.push(outgoing());
  const result = await readConversation(h.app, own, range);
  assert.deepEqual(result.warnings, []);
  assert.equal(result.messages.length, 2);
  assert.deepEqual(result.messages.map(m => m.source.fulcra_userid), [undefined, 'peer']);
});

test('zero complete reads vs partial/failed reads are distinguishable', async () => {
  assert.deepEqual(await readConversation(harness().app, own, range), { messages: [], warnings: [] });
  for (const fail of [[`peer:${peer.id}`], [`me:${own.id}`, `peer:${peer.id}`]]) {
    const h = harness({ fail });
    const result = await readConversation(h.app, own, range);
    assert.equal(result.messages.length, 0);
    assert.match(result.warnings.join(' '), /Could not load messages/);
  }
  const h = harness({ fail: [`me:${own.id}`], rows: { [`peer:${peer.id}`]: [{ note: 'preserved' }] }, truncated: [`peer:${peer.id}`] });
  const result = await readConversation(h.app, own, range);
  assert.equal(result.messages[0].record.note, 'preserved');
  assert.match(result.warnings.join(' '), /Partial result/);
});

for (const tool of ['get_data_catalog', 'list_shares']) test(`${tool} failure retains selected without claiming empty success`, async () => {
  const h = harness({ fail: [tool] });
  const result = await readConversation(h.app, own, range);
  assert.match(result.warnings.join(' '), /discovery.*failed/i);
  assert.equal(h.calls.filter(c => c.name === 'get_records').length, 1);
});

test('stale discovery does not start any reads', async () => {
  const h = harness();
  await readConversation(h.app, own, range, () => false);
  assert.equal(h.calls.filter(c => c.name === 'get_records').length, 0);
});
