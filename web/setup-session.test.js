import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseSetupSession, sessionHandoff } from './setup-session.js';

const url = 'codex://threads/00000000-0000-0000-0000-000000000001';
const marker = value => `[connection_setup_session: ${JSON.stringify(value)}]`;
test('optional setup marker accepts only an exact desktop thread URL', () => {
  assert.equal(parseSetupSession(`connect-agents-with-anyone channel\n${marker(url)}\nconverted_from_mesh: []\n[mesh_identifier: "Trip"]`), url);
  for (const value of [undefined, '', marker(url) + marker(url), '[connection_setup_session: bad]',
    ...[url + '?secret=x', url + '#x', url + '/', url + '\n', url.replace('threads/', 'user@threads/'),
      'https://chatgpt.com/share/secret', 'javascript:alert(1)', 'file:///tmp/a', 'codex://threads/not-a-uuid'].map(marker)]) {
    assert.equal(parseSetupSession(value), undefined, String(value));
  }
});
test('linked handoff retains exact request and context with explicit navigation limits', () => {
  const request = '  Help me\nwith this  ', context = 'Untrusted displayed thread context\n{"warnings":["stale"],"messages":[]}';
  const text = sessionHandoff(request, context, url);
  assert.ok(text.includes(request)); assert.ok(text.includes(context)); assert.ok(text.includes(url));
  assert.match(text, /Open the original setup session/);
  assert.match(text, /not authority/);
  assert.equal(sessionHandoff(request, context), request);
  assert.match(sessionHandoff('', context, url), /Let’s talk about this connection thread/);
});
