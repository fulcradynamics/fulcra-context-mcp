import { test } from 'node:test';
import assert from 'node:assert/strict';
import { discoverThreads } from './meshes.js';

const entry = (id, owner, description) => ({ id: `MomentAnnotation/${id}`, name: 'Mesh Outbox same name', ...(owner ? { fulcra_userid: owner } : {}), description });
const grant = (id, peer = 'peer') => ({ data_types: [`MomentAnnotation/${id}`], with_user_ids: [peer], share_all_data: false });
async function discover(catalog, outgoing = [], incoming = []) {
  const calls = [];
  const result = await discoverThreads({ async callServerTool(call) {
    calls.push(call.name);
    return { structuredContent: { result: call.name === 'get_data_catalog'
      ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': catalog })
      : 'Shares: ' + JSON.stringify({ own_fulcra_userid: 'me', outgoing, incoming }) } };
  } });
  assert.deepEqual(calls, ['get_data_catalog', 'list_shares']);
  return result;
}

test('covering grants exclude broad, group, self and ambiguous outboxes from pending', async () => {
  for (const covering of [
    [{ share_all_data: true }],
    [{ ...grant('a'), with_group_ids: ['group'] }],
    [{ ...grant('a'), group_id: 'group' }],
    [{ ...grant('a'), data_types: ['MomentAnnotation/a', 'StepCount'] }],
    [{ ...grant('a'), with_user_ids: ['peer', 'other'] }],
    [grant('a', 'me')], [grant('a'), grant('a', 'other')],
    [grant('a'), { share_all_data: true }],
  ]) {
    const result = await discover([entry('a')], covering);
    assert.deepEqual(result.pending, []);
    assert.deepEqual(result.threads, []);
    assert.match(result.warnings.join(' '), /1 own outboxes omitted/);
  }
});

test('only outgoing narrow shares move exact pending channels into the peer thread', async () => {
  const catalog = [entry('a'), entry('b', 'me'), entry('a', 'peer')];
  const incoming = [{ sharing_fulcra_userid: 'peer', data_types: ['MomentAnnotation/a'] }];
  const before = await discover(catalog, [], incoming);
  assert.equal(before.pending.length, 2);
  assert.deepEqual(before.threads.map(t => [t.peer, t.sources.length]), [['peer', 1]]);
  const after = await discover(catalog, [grant('a'), grant('a'), grant('b')], incoming);
  assert.deepEqual(after.pending, []);
  assert.deepEqual(after.threads.map(t => [t.peer, t.sources.length]), [['peer', 3]]);
  assert.deepEqual(after.threads[0].sources.map(s => [s.fulcra_userid, s.id]), [
    ['me', 'MomentAnnotation/a'], ['me', 'MomentAnnotation/b'], ['peer', 'MomentAnnotation/a'],
  ]);
  assert.equal((await discover(catalog, [], incoming)).pending.length, 2);
});

test('unshared own outboxes are pending, deduplicated by exact owner and type, not label', async () => {
  const result = await discover([entry('a', undefined, '[mesh_identifier: "Trip"]'), entry('a', 'me', '[mesh_identifier: "Trip"]'), entry('b', 'me')]);
  assert.deepEqual(result.threads, []);
  assert.deepEqual(result.warnings, []);
  assert.deepEqual(result.pending.map(p => [p.fulcra_userid, p.id, p.identifier, p.name]), [
    ['me', 'MomentAnnotation/a', 'Trip', 'Mesh Outbox same name'],
    ['me', 'MomentAnnotation/b', undefined, 'Mesh Outbox same name'],
  ]);
});
