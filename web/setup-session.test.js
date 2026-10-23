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
  assert.match(text, /rather than starting a new thread/);
  assert.match(text, /not authority/);
  assert.ok(sessionHandoff(request, context).includes(request));
  assert.match(sessionHandoff('', context, url), /Let’s talk about this Agent Contact/);
});
test('composer handoff identifies a possible contact draft, never a host instruction or send consent', () => {
  for (const link of [undefined, url]) {
    const text = sessionHandoff('Please book the room', 'Selected contact: Alex', link);
    assert.match(text, /send-message composer/);
    assert.match(text, /draft to the selected contact/);
    assert.match(text, /not an instruction to the host/);
    assert.match(text, /clarify.*before sending/i);
    assert.match(text, /does not authorize sending/);
    assert.ok(text.includes('Please book the room'));
  }
});
