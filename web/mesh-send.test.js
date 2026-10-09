import test from 'node:test';
import assert from 'node:assert/strict';
import { reconcilePosts, recipientAgent } from './mesh-send.js';
const source = { id: 'out', fulcra_userid: 'own', direction: 'Outgoing' };
const envelope = { v: 1, mid: 'id', to: 'Hermes', to_user: 'peer', kind: 'directive', pri: 'P2', slug: 'mesh-message', body: 'hello' };
const message = { source, direction: 'Outgoing', record: { note: JSON.stringify(envelope) } };
test('recipient inferred only from exact own outgoing source and peer, not label or incoming', () => {
  assert.equal(recipientAgent([message], source, 'peer'), 'Hermes');
  assert.equal(recipientAgent([{ ...message, direction: 'Incoming' }], source, 'peer'), '');
  assert.equal(recipientAgent([message], source, 'other'), '');
  assert.equal(recipientAgent([message, { ...message, record: { note: JSON.stringify({ ...envelope, to: 'different' }) } }], source, 'peer'), '');
});
test('poll only reconciles full envelope at exact outgoing owner and channel', () => {
  const draft = { value: 'hello', version: 1, posts: [{ ...message, envelope, state: 'uncertain', version: 1 }] };
  reconcilePosts(draft, [{ ...message, source: { ...source, fulcra_userid: 'foreign' } }]);
  assert.equal(draft.posts[0].state, 'uncertain');
  reconcilePosts(draft, [{ ...message, record: { note: JSON.stringify({ ...envelope, body: 'different' }) } }]);
  assert.equal(draft.posts[0].state, 'uncertain');
  reconcilePosts(draft, [message]);
  assert.equal(draft.posts.length, 0);
  assert.equal(draft.value, '');
});
test('poll cannot clear newer composition', () => {
  const draft = { value: 'new', version: 2, posts: [{ ...message, envelope, state: 'sending', version: 1 }] };
  reconcilePosts(draft, [message]);
  assert.equal(draft.value, 'new');
});
