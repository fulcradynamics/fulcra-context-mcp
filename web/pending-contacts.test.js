import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pendingContacts, matchInvitations } from './pending-contacts.js';

const incoming = { id: 'Event/in', fulcra_userid: 'peer', direction: 'Incoming', name: 'Peer' };
const outgoing = { id: 'Event/out', fulcra_userid: 'own', direction: 'Outgoing', name: 'Own' };
const discovery = sources => ({ threads: [{ peer: 'peer', sources }], pending: [], legacy: [], warnings: [] });

test('one-way contacts stay pending until both directions exist', () => {
  for (const source of [incoming, outgoing]) {
    const result = pendingContacts(discovery([source]));
    assert.equal(result.threads.length, 0);
    assert.equal(result.pending[0].peer, 'peer');
    assert.equal(result.pending[0].direction, source.direction);
  }
  assert.equal(pendingContacts(discovery([incoming, outgoing])).threads.length, 1);
});

test('pending prepared outbox does not borrow another same-peer channel', () => {
  const other = { ...outgoing, id: 'Event/other' };
  const discovered = discovery([incoming, other]);
  discovered.pending = [outgoing]; // Unshared channels are not outgoing grant sources.
  const result = pendingContacts(discovered, [{data_type: outgoing.id, status: 'pending'}]);
  assert.deepEqual(result.threads[0].sources, [incoming, other]);
  assert.equal(result.pending[0].id, outgoing.id);
});

test('multiparty needs every outgoing recipient to have an incoming source', () => {
  const multi = discovery([incoming, outgoing]);
  multi.threads[0].expectedPeerUserids = ['peer', 'other'];
  multi.threads[0].participants = [{id: 'own'}, {id: 'peer'}, {id: 'other'}];
  assert.equal(pendingContacts(multi).threads.length, 0);
  multi.threads[0].sources.push({...incoming, fulcra_userid: 'other'});
  assert.equal(pendingContacts(multi).threads.length, 1);
});

test('invitation outcomes cannot veto independently verified reciprocal grants', () => {
  for (const matches of [[{data_type: outgoing.id, status:'matched'}], [], [{data_type: outgoing.id, status:'pending'}]]) {
    const result = pendingContacts(discovery([incoming, outgoing]), matches);
    assert.equal(result.threads.length, 1);
    assert.equal(result.pending.length, 0);
    const multi = discovery([incoming, outgoing, {...incoming, id:'Event/other', fulcra_userid:'other'}]);
    multi.threads[0].expectedPeerUserids = ['peer', 'other'];
    assert.equal(pendingContacts(multi, matches).threads.length, 1);
  }
});

test('automatic matching is a narrow tool call, never a model turn; unavailable results fail closed', async () => {
  const calls = [];
  const app = {callServerTool: async call => { calls.push(call); return {structuredContent:{results:[]}}; }};
  assert.deepEqual(await matchInvitations(app), []);
  assert.deepEqual(calls, [{name:'match_agent_invitations', arguments:{}}]);
  for (const result of [{isError:true}, {structuredContent:{status:'unavailable',results:[]}}, {content:[]}]) {
    await assert.rejects(matchInvitations({callServerTool:async () => result}));
  }
});
