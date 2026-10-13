import test from 'node:test';
import assert from 'node:assert/strict';
import { unreadMessages } from './unread.js';

const now = Date.parse('2026-10-13T12:00:00Z');
const incoming = (id, kind = 'message', start_time = '2026-10-13T10:00:00Z') =>
  ({ direction: 'Incoming', record: { id, kind, start_time, sender: 'peer', body: 'hi' } });
const answer = (in_reply_to, kind = 'ack') =>
  ({ direction: 'Outgoing', record: { id: `a-${in_reply_to}`, kind, in_reply_to, start_time: '2026-10-13T11:00:00Z' } });

test('unanswered incoming messages and replies are unread, oldest first', () => {
  const messages = [incoming('b', 'reply', '2026-10-13T11:00:00Z'), incoming('a'), incoming('c', 'ack')];
  assert.deepEqual(unreadMessages(messages, new Set(), now).map(m => m.record.id), ['a', 'b']);
});

test('own acks and replies mark their targets read', () => {
  const messages = [incoming('a'), incoming('b'), answer('a'), answer('b', 'reply')];
  assert.deepEqual(unreadMessages(messages, new Set(), now), []);
});

test('pending acks, old messages and incoming answers do not count', () => {
  const peerAck = { direction: 'Incoming', record: { id: 'x', kind: 'ack', in_reply_to: 'a', start_time: '2026-10-13T11:00:00Z' } };
  const messages = [incoming('a'), incoming('old', 'message', '2026-09-01T00:00:00Z'), incoming('b'), peerAck];
  assert.deepEqual(unreadMessages(messages, new Set(['b']), now).map(m => m.record.id), ['a']);
});
