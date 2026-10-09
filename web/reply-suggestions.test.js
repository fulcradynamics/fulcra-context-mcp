import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseSuggestions } from './reply-suggestions.js';
const result = (text, rest = {}) => ({ role: 'assistant', content: { type: 'text', text }, ...rest });

test('suggestion parser accepts only one to three bounded plain-text replies and deduplicates', () => {
  assert.deepEqual(parseSuggestions(result('["One","Two","One"]')), ['One', 'Two']);
  assert.deepEqual(parseSuggestions(result('["<img src=x onerror=alert(1)>"]')), ['<img src=x onerror=alert(1)>']);
});
test('suggestion parser rejects malformed, empty, excessive, nonstring and oversized completions', () => {
  for (const text of ['not JSON', '```json\n["One"]\n```', '[]', '[" "]', '{}', '[1]', '["One",null]', '["1","2","3","4"]', JSON.stringify(['x'.repeat(301)]), ' '.repeat(2001), '["line\\nbreak"]']) {
    assert.throws(() => parseSuggestions(result(text)));
  }
});
test('suggestion parser refuses nonassistant, nontext and truncated or tool-use completions', () => {
  for (const extra of [{ role: 'user' }, { content: { type: 'image', data: 'anything' } }, { stopReason: 'maxTokens' }, { stopReason: 'toolUse' }, { content: [{ type: 'text', text: '["One"]' }] }]) {
    assert.throws(() => parseSuggestions(result('["One"]', extra)));
  }
});
