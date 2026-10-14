import { test } from 'node:test';
import assert from 'node:assert/strict';
import { discoverThreads, loadConnections, parseConnections } from './connections-discovery.js';
import { channelFixture, shareFixture, incomingFixtures } from './connection-fixtures.js';

test('identifier is display only, outgoing preferred, stable type-ID tie break and fallback', async () => {
  const labeled = (id, owner, label) => ({ ...entry(id, owner), description: `Prose [mesh_identifier: ${JSON.stringify(label)}]` });
  const catalog = [labeled('z', 'me', 'Other own'), labeled('a', 'me', '<b>Trip</b>'),
    labeled('incoming', 'peer', 'Incoming label'), labeled('same', 'other', '<b>Trip</b>'), entry('none', 'unknown')];
  for (const items of [catalog, [...catalog].reverse()]) {
    const result = await load(items, [grant('z'), grant('a')]);
    assert.deepEqual(result.rows.map(r => r.button.textContent), ['<b>Trip</b> (other)', '<b>Trip</b> (peer)', 'unknown']);
    assert.deepEqual(result.selections.map(t => t.peer), ['other', 'peer', 'unknown']);
    assert.equal(result.selections[1].sources.length, 3);
    assert.equal(result.selections[1].sources.find(s => s.id === 'Event/a').name, 'Mesh Outbox same name');
    assert.deepEqual(result.calls.map(c => c.name), ['get_data_catalog', 'list_shares']);
  }
  catalog[1].description = '[mesh_identifier: "Renamed"]';
  const renamed = await load(catalog, [grant('z'), grant('a')]);
  assert.equal(renamed.rows[1].button.textContent, 'Renamed (peer)');
  catalog[1].description = '[mesh_identifier: bad]';
  catalog[0].description = 'no marker';
  assert.equal((await load(catalog, [grant('z'), grant('a')])).rows[1].button.textContent, 'Incoming label (peer)');
});

test('failed discovery drains both requests before releasing the scheduler', async () => {
  let finish, settled = false;
  const pending = discoverThreads({ callServerTool({ name }, options) {
    assert.equal(options.timeout, 30000);
    return name === 'get_data_catalog' ? Promise.reject(new Error('offline'))
      : new Promise(resolve => { finish = resolve; });
  } }).catch(() => { settled = true; });
  for (let i = 0; i < 10; i++) await Promise.resolve();
  assert.equal(settled, false);
  finish({ isError: true }); await pending;
  assert.equal(settled, true);
});

test('sharing account names are labeled without inventing agent names or grouping by name', async () => {
  const result = await discoverThreads({ async callServerTool({ name }) {
    return text(name === 'get_data_catalog' ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': [entry('a', 'peer'), entry('b', 'other'), entry('c', 'unknown')].map(channelFixture) })
      : 'Shares: ' + JSON.stringify({ own_fulcra_userid: 'me', outgoing: [], incoming: [
        ...incomingFixtures([entry('a', 'peer'), entry('b', 'other'), entry('c', 'unknown')]),
        { sharing_fulcra_userid: 'peer', sharing_fulcra_user_name: 'Alex' },
        { sharing_fulcra_userid: 'other', sharing_fulcra_user_name: 'Alex' },
      ] }));
  } });
  assert.deepEqual(result.threads.map(t => [t.peer, t.accountName]), [['other', 'Alex'], ['peer', 'Alex'], ['unknown', undefined]]);
});

const entry = (id, owner) => ({ id: `Event/${id}`, name: 'Mesh Outbox same name', ...(owner ? { fulcra_userid: owner } : {}) });
test('setup links belong only to eligible own outgoing channels', async () => {
  const url = 'codex://threads/00000000-0000-0000-0000-000000000001';
  const linked = (id, owner) => ({ ...entry(id, owner), description: `[connection_setup_session: "${url}"]` });
  const result = await load([linked('own'), linked('incoming', 'peer')], [grant('own')]);
  const sources = result.selections[0].sources;
  assert.equal(sources.find(s => s.direction === 'Outgoing').setupSession, url);
  assert.equal(sources.find(s => s.direction === 'Incoming').setupSession, undefined);
  const multi = (await load([linked('own')], [grant('own'), grant('own', 'other')])).selections[0];
  assert.equal(multi.participants.length, 3);
  assert.equal(multi.sources[0].setupSession, url);
});
const grant = (id, peer = 'peer') => ({ data_types: [`Event/${id}`], with_user_ids: [peer], share_all_data: false });
test('assessment uses only verified own channels, never peer-authored status', async () => {
  const assessed = (id, owner, attention) => ({ ...entry(id, owner), description:
    `[contact_status: ${JSON.stringify({attention, reason:'Decision needed', assessed_at:'2026-10-13T12:00:00Z'})}]` });
  const peerOnly = await load([assessed('incoming', 'peer', true)]);
  assert.equal(peerOnly.selections[0].assessment.attention, null);
  assert.equal(peerOnly.selections[0].sources[0].assessment, undefined);
  const own = await load([assessed('own', 'me', false), assessed('incoming', 'peer', true)], [grant('own')]);
  assert.equal(own.selections[0].assessment.attention, false);
  const mixed = await load([assessed('a', 'me', false), assessed('z', 'me', true), entry('unknown','me')], [grant('a'),grant('z'),grant('unknown')]);
  assert.equal(mixed.selections[0].assessment.attention, true);
  assert.equal(mixed.selections[0].assessment.partial, true);
});
const text = result => ({ structuredContent: { result } });
async function load(catalog, outgoing = [], own = 'me') {
  const rows = [], selections = [], calls = [], status = {};
  const list = { replaceChildren() {}, ownerDocument: { createElement: () => ({ addEventListener(_, fn) { this.click = fn; }, append(button) { this.button = button; } }) }, append: row => rows.push(row) };
  await loadConnections({ async callServerTool(call) {
    calls.push(call);
    return text(call.name === 'get_data_catalog'
      ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': catalog.map(channelFixture) })
      : 'Shares: ' + JSON.stringify({ own_fulcra_userid: own, outgoing:outgoing.map(shareFixture), incoming: incomingFixtures(catalog, own) }));
  } }, status, list, thread => selections.push(thread));
  for (const row of rows) row.button.click();
  return { rows, selections, calls, status: status.textContent };
}

test('one exact peer row deduplicates both sides and multiple narrow channels; names do not group peers', async () => {
  const result = await load([entry('own'), entry('own'), entry('second'), entry('same', 'peer'), entry('same', 'peer'), entry('same', 'other')], [grant('own'), grant('second')]);
  assert.match(result.status, /2 threads/);
  assert.deepEqual(result.rows.map(r => r.button.textContent), ['other', 'peer']);
  assert.deepEqual(result.selections.map(t => t.peer), ['other', 'peer']);
  assert.equal(result.selections[1].sources.length, 3);
  assert.deepEqual(result.calls.map(c => c.name), ['get_data_catalog', 'list_shares']);
});

test('only catalog groups compatible with get_records are readable', () => {
  assert.deepEqual(parseConnections(text('Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types that cannot be queried (used only when recording data)': [entry('x')] }))), []);
});

test('orphans and self do not become threads; broad/mixed grants cannot hide behind a narrow grant', async () => {
  for (const extra of [

    { ...grant('own'), data_types: ['Event/own', 'StepCount'] },
    { share_all_data: true },
    { ...grant('own'), with_group_ids: ['group'] },
    { ...grant('own'), file_paths: ['/'] },

  ]) {
    const result = await load([entry('own'), entry('orphan'), entry('self', 'me'), entry('incoming', 'peer')], [grant('own'), extra, grant('self', 'me')]);
    assert.deepEqual(result.selections.map(t => t.peer), ['peer']);
    assert.equal(result.selections[0].sources.length, 1);
    assert.match(result.status, new RegExp(`${extra.share_all_data ? 3 : 2} own outboxes omitted`));
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
    await loadConnections({ callServerTool: async () => { if (result instanceof Error) throw result; return result; } }, status, { replaceChildren() {} });
    assert.match(status.textContent, /Could not load/);
    assert.doesNotMatch(status.textContent, /0 threads/);
  }
  assert.match((await load([entry('own')], [grant('own')], undefined)).status, /threads/);
  assert.match((await load([entry('own')], [grant('own')], '')).status, /Could not load/);
});
