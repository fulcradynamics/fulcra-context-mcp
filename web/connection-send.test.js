import test from 'node:test';
import assert from 'node:assert/strict';
import { reconcilePosts } from './connection-send.js';
const source = { id: 'out', fulcra_userid: 'own', direction: 'Outgoing' };
const envelope = { id: 'id', sender:'Hermes', kind:'message', priority:'P2', topic:'chat', body:'hello' };
const message = { source, direction: 'Outgoing', record: envelope };
test('poll reconciles by mid alone despite different metadata and content', () => {
  const draft = { value: 'hello', version: 1, posts: [{ ...message, envelope, state: 'uncertain', version: 1 }] };
  reconcilePosts(draft, [{ ...message, record: { ...envelope, id: 'different-id' } }]);
  assert.equal(draft.posts.length, 1);
  reconcilePosts(draft, [{ source: { id: 'other', fulcra_userid: 'foreign' }, direction: 'Incoming', record: { id: envelope.id, body: 'different', recipients: null } }]);
  assert.equal(draft.posts.length, 0);
  assert.equal(draft.value, '');
});
test('poll cannot clear newer composition', () => {
  const draft = { value: 'new', version: 2, posts: [{ ...message, envelope, state: 'sending', version: 1 }] };
  reconcilePosts(draft, [message]);
  assert.equal(draft.value, 'new');
});
