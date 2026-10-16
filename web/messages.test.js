import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseRecords, messageText } from './messages.js';

const id = 'MomentAnnotation/00000000-0000-0000-0000-000000000001';
const result = (rows, suffix = '') => ({ content: [{ type: 'text', text: `Records for ${id} from 2026-01-01 00:00:00+00:00 to 2026-02-01 00:00:00+00:00${suffix}: ${JSON.stringify(rows)}` }] });

test('records parser accepts actual tool format and preserves truncated status', () => {
  assert.deepEqual(parseRecords(result([]), id), { records: [], truncated: false });
  assert.deepEqual(parseRecords(result([{ note: 'hi' }], ' (showing the first 1 of 2; narrow the time range for the rest, or use get_time_series for per-interval aggregates)'), id), { records: [{ note: 'hi' }], truncated: true });
  const wrapped = result([{ note: 'hi' }]);
  assert.equal(parseRecords({ structuredContent: { result: wrapped.content[0].text } }, id).records.length, 1);
});

test('errors and malformed results are not empty history', () => {
  for (const value of [{ isError: true }, { content: [{ type: 'text', text: 'Could not retrieve records' }] }, result([null]), result({})]) {
    assert.throws(() => parseRecords(value, id));
  }
});

test('Event messages display only literal body, without generated metadata', () => {
  const body = '  <b>Hello</b>\nkind: literal body text\n';
  assert.equal(messageText({sender:'peer',kind:'message',body}), body);
  assert.equal(messageText({sender:'peer',kind:'ack',body:''}), '');
});

test('legacy notes are not rendered by connection UI', () => {
  for (const note of ['not JSON', '  kind: note\n\nraw body  ', '{"v":2,"body":"future"}', '{"v":1,"body":42}', 'null']) {
    assert.equal(messageText({ note }), 'Unrecognized connection record.');
  }
  assert.equal(messageText({}), 'Unrecognized connection record.');
});
