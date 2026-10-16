import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setupInvite } from './invite.js';
import { getContextLifecycle } from './native-context.js';

function ui() {
  return { button: { disabled: true, addEventListener(_, fn) { this.click = fn; } }, status: { textContent: '' } };
}
function host(overrides = {}) {
  return { connect: async () => {}, getHostCapabilities: () => ({ message: { text: {} } }), ...overrides };
}

test('click sends only a user message requesting the invitation action', async () => {
  const { button, status } = ui();
  const calls = [];
  await setupInvite(host({ sendMessage: async (message) => { calls.push(message); return {}; } }), [button], status);
  assert.equal(calls.length, 0);
  assert.equal(button.disabled, false);
  await button.click();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].role, 'user');
  assert.match(calls[0].content[0].text, /use the invite skill/);
  assert.match(calls[0].content[0].text, /invite another user/);
  assert.match(calls[0].content[0].text, /prepare_agent_invitation\(data_type\)/);
  assert.match(calls[0].content[0].text, /copyable invitation prompt/);
  assert.match(calls[0].content[0].text, /returned own_userid and code/);
  assert.match(calls[0].content[0].text, /FIRST message topic must be exactly handshake/);
  assert.match(calls[0].content[0].text, /Do not ask for the other user's ID/);
  assert.match(calls[0].content[0].text, /optional context/);
  assert.match(calls[0].content[0].text, /draft an outgoing message/);
  assert.match(calls[0].content[0].text, /prepare a dedicated unshared outbox/);
  assert.match(calls[0].content[0].text, /my name and the name of the person I am inviting/);
  assert.match(calls[0].content[0].text, /identifier <their name>'s agent \(for example Lucian's agent\).*original setup session URL/);
  assert.match(calls[0].content[0].text, /without another confirmation/);
  assert.match(calls[0].content[0].text, /authorizes match_agent_invitations to share only that prepared outbox/);
  assert.match(calls[0].content[0].text, /unmatched sharing needs my explicit consent/);
  assert.match(status.textContent, /Request sent/);
});

test('disable while pending; rejection allows retry without claiming an invitation', async () => {
  const { button, status } = ui();
  let finish;
  await setupInvite(host({ sendMessage: () => new Promise(resolve => { finish = resolve; }) }), [button], status);
  const pending = button.click();
  assert.equal(button.disabled, true);
  await new Promise(setImmediate);
  finish({ isError: true });
  await pending;
  assert.equal(button.disabled, false);
  assert.match(status.textContent, /Could not send/);
});

for (const denied of [false, true]) test(`invitation requires confirmed clearing of prior context (${denied})`, async () => {
  const {button,status}=ui(), calls=[];
  const app=host({
    updateModelContext:async value=>{calls.push(['context',value]);return {isError:denied&&!value.content.length};},
    sendMessage:async()=>{calls.push(['message']);return {};},
  });
  await setupInvite(app,[button],status);
  const lifecycle=getContextLifecycle(app,status);
  await lifecycle.attach('previous peer history',lifecycle.token());
  await button.click();
  assert.deepEqual(calls[1],['context',{content:[]}]);
  assert.equal(calls.filter(c=>c[0]==='message').length,denied?0:1);
});

test('unsupported host and failed connection leave button disabled', async () => {
  for (const app of [host({ getHostCapabilities: () => ({}) }), host({ connect: async () => { throw Error('offline'); } })]) {
    const { button, status } = ui();
    await setupInvite(app, [button], status);
    assert.equal(button.disabled, true);
    assert.ok(status.textContent);
  }
});

test('unsupported messaging offers the same invitation action', async () => {
  const { button, status } = ui();
  await setupInvite(host({ getHostCapabilities: () => ({}) }), [button], status);
  assert.match(status.textContent, /use the invite skill/);
});
