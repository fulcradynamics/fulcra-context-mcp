import { test } from 'node:test';
import assert from 'node:assert/strict';
import { invitationPrompt, requestInChat } from './invite.js';
import { invitationTemplate } from './invite-template.js';
import { getContextLifecycle } from './native-context.js';

const status = () => ({ textContent: '' });
const host = (overrides = {}) => ({ getHostCapabilities: () => ({ message: { text: {} } }), ...overrides });

test('chat handoff never asks the model to call app-only invitation tools', async () => {
  const sent = [];
  await requestInChat(host({ sendMessage: async m => { sent.push(m); return {}; } }), status(), invitationPrompt, 'sent');
  assert.doesNotMatch(sent[0].content[0].text, /prepare_agent_invitation|match_agent_invitations|create_agent_invitation/);
});

test('chat handoff asks the invite skill for the same invitation flow', () => {
  for (const clause of [/use the invite skill/, /open invitation.*group/, /open_invitation followed by one space/, /template.*never shared/,
    /available generic tools/, /copyable invitation prompt/, /verified Fulcra user ID and persisted code/,
    /FIRST message topic must be exactly handshake/, /Do not ask for the other user's ID; if I already gave it, share the prepared outbox with exactly that user/,
    /optional context/, /prepare a dedicated unshared outbox/, /my name and the name of the person I am inviting/,
    /identifier <their name>'s agent \(for example Lucian's agent\).*original setup session URL/,
    /verified matching procedure to share only that prepared outbox/, /unmatched sharing needs my explicit consent/]) {
    assert.match(invitationPrompt, clause);
  }
});

test('no secure execution has no new open-invitation fallback loop', () => {
  assert.match(invitationPrompt, /single-person only/);
  assert.match(invitationPrompt, /new open invitations are unavailable/);
  assert.match(invitationPrompt, /existing prepared open codes/);
  assert.match(invitationPrompt, /Do not loop.*silently downgrade/);
});

test('request in chat sends one user message and reports rejection', async () => {
  const calls = [], s = status();
  assert.equal(await requestInChat(host({ sendMessage: async m => { calls.push(m); return {}; } }), s, 'hi', 'Request sent'), true);
  assert.deepEqual(calls, [{ role: 'user', content: [{ type: 'text', text: 'hi' }] }]);
  assert.equal(await requestInChat(host({ sendMessage: async () => ({ isError: true }) }), s, 'hi', 'sent'), false);
  assert.match(s.textContent, /Couldn’t send your request/);
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
