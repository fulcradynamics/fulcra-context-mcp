import { test } from 'node:test';
import assert from 'node:assert/strict';
import { contactPreview } from './contact-preview.js';
const message = (id, direction, kind = 'message', in_reply_to) => ({ direction, source: { fulcra_userid: direction }, record: { id, kind, body: id, sender: 'agent', in_reply_to } });
test('latest content retains its acknowledgement from the opposite direction', () => {
  const incoming = message('hello', 'Incoming');
  assert.deepEqual(contactPreview([incoming]), { message: incoming, acknowledged: false });
  assert.deepEqual(contactPreview([message('read', 'Outgoing', 'ack', 'hello'), incoming]), { message: incoming, acknowledged: true });
  const outgoing = message('sent', 'Outgoing');
  assert.deepEqual(contactPreview([message('read', 'Incoming', 'ack', 'sent'), outgoing]), { message: outgoing, acknowledged: true });
  assert.equal(contactPreview([message('read', 'Incoming', 'ack')]), undefined);
});
