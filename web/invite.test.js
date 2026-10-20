import { test } from 'node:test';
import assert from 'node:assert/strict';
import { invitationPrompt, requestInChat } from './invite.js';
import { invitationTemplate } from './invite-template.js';
import { getContextLifecycle } from './native-context.js';

const status = () => ({ textContent: '' });
const host = (overrides = {}) => ({ getHostCapabilities: () => ({ message: { text: {} } }), ...overrides });

test('chat handoff asks the invite skill for the same invitation flow', () => {
  for (const clause of [/use the invite skill/, /open invitation.*group/, /open_invitation=true/, /template.*never shared/,
    /prepare_agent_invitation\(data_type\)/, /copyable invitation prompt/, /returned own_userid and code/,
    /FIRST message topic must be exactly handshake/, /Do not ask for the other user's ID; if I already gave it, share the prepared outbox with exactly that user/,
    /optional context/, /prepare a dedicated unshared outbox/, /my name and the name of the person I am inviting/,
    /identifier <their name>'s agent \(for example Lucian's agent\).*original setup session URL/,
    /authorizes match_agent_invitations to share only that prepared outbox/, /unmatched sharing needs my explicit consent/]) {
    assert.match(invitationPrompt, clause);
  }
});

test('request in chat sends one user message and reports rejection', async () => {
  const calls = [], s = status();
  assert.equal(await requestInChat(host({ sendMessage: async m => { calls.push(m); return {}; } }), s, 'hi', 'Request sent'), true);
  assert.deepEqual(calls, [{ role: 'user', content: [{ type: 'text', text: 'hi' }] }]);
  assert.equal(await requestInChat(host({ sendMessage: async () => ({ isError: true }) }), s, 'hi', 'sent'), false);
  assert.match(s.textContent, /Could not send/);
});

for (const denied of [false, true]) test(`chat request requires confirmed clearing of prior context (${denied})`, async () => {
  const calls = [], s = status();
  const app = host({
    updateModelContext: async value => { calls.push(['context', value]); return { isError: denied && !value.content.length }; },
    sendMessage: async () => { calls.push(['message']); return {}; },
  });
  const lifecycle = getContextLifecycle(app, s);
  await lifecycle.attach('previous peer history', lifecycle.token());
  await requestInChat(app, s, 'invite', 'sent');
  assert.deepEqual(calls[1], ['context', { content: [] }]);
  assert.equal(calls.filter(c => c[0] === 'message').length, denied ? 0 : 1);
});

test('template substitutes inviter, own ID and exact topic', () => {
  const text = invitationTemplate({ inviterAgent: "Leif's ChatGPT", ownUserid: 'own-id', topic: 'handshake abc' });
  assert.match(text, /^I'd like to connect our agents through Fulcra\.\nPlease help me connect with Leif's ChatGPT, Fulcra user own-id\./);
  assert.match(text, /topic exactly `handshake abc`/);
  assert.doesNotMatch(text, /</);
});
