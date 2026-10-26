import { test } from 'node:test';
import assert from 'node:assert/strict';
import { discoverThreads } from './connections-discovery.js';
import { channelFixture } from './connection-fixtures.js';

const own = '00000000-0000-4000-8000-000000000001';
const peer = '00000000-0000-4000-8000-000000000002';
const out = 'Event/00000000-0000-4000-8000-000000000010';
const incoming = 'Event/00000000-0000-4000-8000-000000000020';
import { selectedSources } from './incoming-sources.js';

const metadata = value => `[agent_connection: ${JSON.stringify({version: 1, ...value})}]`;
async function discover(description, incomingDescription = '') {
  const entries = [
    {...channelFixture({id: out, name: 'Project', fulcra_userid: own}), description},
    {...channelFixture({id: incoming, name: 'Return', fulcra_userid: peer}), description: incomingDescription},
  ];
  return discoverThreads({async callServerTool({name}) {
    return {content: [{type: 'text', text: name === 'get_data_catalog'
      ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({'data types usable with: get_records': entries})
      : 'Shares: ' + JSON.stringify({own_fulcra_userid: own,
        outgoing: [{data_types: [out], with_user_ids: [peer], share_all_data: false}],
        incoming: [{data_types: [incoming], sharing_fulcra_userid: peer, grant_type: 'user'}]})}]};
  }});
}

test('unmarked usable channels remain discoverable', async () => {
  const result = await discover('Project notes');
  assert.equal(result.threads.length, 1);
  assert.equal(result.threads[0].sources.length, 2);
  assert.equal(selectedSources(result.threads[0]).sources.length, 2);
});

test('own durable pair marks association without reciprocal metadata', async () => {
  const result = await discover(metadata({peers: [{fulcra_userid: peer, data_type: incoming}]}));
  assert.equal(result.threads[0].sources.find(s => s.direction === 'Incoming').association, 'matched');
});

test('saved pairs default to newest outbox and allow explicit incoming overrides', async () => {
  const secondOut = out.slice(0, -1) + '1', secondIn = incoming.slice(0, -1) + '1';
  const entries = [[out, own, incoming], [secondOut, own, secondIn], [incoming, peer], [secondIn, peer]]
    .map(([id, owner, match]) => ({...channelFixture({id, fulcra_userid: owner}),
      description: match ? metadata({peers: [{fulcra_userid: peer, data_type: match}]}) : ''}));
  const {threads: [thread]} = await discoverThreads({async callServerTool({name}) {
    return {content: [{type: 'text', text: name === 'get_data_catalog'
      ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({'data types usable with: get_records': entries})
      : 'Shares: ' + JSON.stringify({own_fulcra_userid: own,
        outgoing: [out, secondOut].map(id => ({data_types: [id], with_user_ids: [peer], share_all_data: false})),
        incoming: [incoming, secondIn].map(id => ({data_types: [id], sharing_fulcra_userid: peer, grant_type: 'user'}))})}]};
  }});
  thread.sources.find(s => s.id === secondOut).sharedAt = 100;
  assert.deepEqual(selectedSources(thread).sources.map(s => s.id).sort(), [secondOut, secondIn]);
  assert.deepEqual(selectedSources(thread, [], out).sources.map(s => s.id).sort(), [out, incoming, secondIn]);
  assert.deepEqual(selectedSources(thread, undefined, out).sources.map(s => s.id).sort(), [out, incoming]);
  assert.deepEqual(selectedSources(thread, undefined, secondOut).sources.map(s => s.id).sort(), [secondOut, secondIn]);
});

test('missing saved match falls back to readable incoming channels', async () => {
  const {threads: [thread]} = await discover(metadata({peers: [{fulcra_userid: peer, data_type: incoming}]}));
  const unrelated = {...thread.sources.find(s => s.direction === 'Incoming'), id: incoming.slice(0, -1)+'1'};
  thread.sources.push(unrelated);
  assert.deepEqual(selectedSources(thread).sources.map(s => s.id), [out, incoming]);
  thread.sources = thread.sources.filter(s => s.id !== incoming);
  assert.deepEqual(selectedSources(thread).sources.map(s => s.id), [out, unrelated.id]);
});

test('unmarked incoming channels remain readable until explicitly excluded', async () => {
  const {threads: [thread]} = await discover('Project');
  const unrelated = {...thread.sources.find(s => s.direction === 'Incoming'), id: incoming.slice(0, -1)+'1'};
  thread.sources.push(unrelated);
  assert.deepEqual(selectedSources(thread).sources.map(s => s.id), [out, incoming, unrelated.id]);
  assert.deepEqual(selectedSources(thread, [JSON.stringify([peer, unrelated.id])]).sources.map(s => s.id), [out, incoming]);
});

for (const broad of [{share_all_data: true}, {data_types: ['Event/*']}, {data_types: [out, incoming]}]) {
  test('broad-only access leaves invitation pending ' + JSON.stringify(broad), async () => {
    const entry = {...channelFixture({id: out, fulcra_userid: own}), description: metadata({invitation: {prefix: 'handshake', state: 'prepared', code: 'a'.repeat(32)}})};
    const result = await discoverThreads({async callServerTool({name}) {
      return {content: [{type: 'text', text: name === 'get_data_catalog'
        ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({'data types usable with: get_records': [entry]})
        : 'Shares: ' + JSON.stringify({own_fulcra_userid: own, incoming: [], outgoing: [{share_all_data: false, with_user_ids: [peer], ...broad}]})}]};
    }});
    assert.deepEqual(result.pending.map(s => s.id), [out]);
    assert.deepEqual(result.warnings, []);
  });
}

test('open invitation template is not a contact even if shared', async () => {
  const result = await discover(metadata({invitation: {prefix: 'open_invitation', code: 'a'.repeat(32), state: 'prepared', responses: {}}}));
  assert.equal(result.threads.flatMap(t => t.sources).some(s => s.id === out), false);
  assert.equal(result.pending.length, 0);
});
