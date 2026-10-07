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

test('mesh envelope body and metadata are readable; invalid notes remain visible', () => {
  assert.match(messageText({ note: JSON.stringify({ v: 1, mid: 'm', to: 'chatgpt', to_user: 'peer', kind: 'directive', slug: 'hello', body: '<b>Hello</b>' }) }), /<b>Hello<\/b>/);
  assert.match(messageText({ note: 'not JSON' }), /Unrecognized.*not JSON/s);
  assert.match(messageText({}), /no note/i);
});
