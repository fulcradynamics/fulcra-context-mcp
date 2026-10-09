import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setupInvite } from './invite.js';

function ui() {
  return { button: { disabled: true, addEventListener(_, fn) { this.click = fn; } }, status: { textContent: '' } };
}
function host(overrides = {}) {
  return { connect: async () => {}, getHostCapabilities: () => ({ message: { text: {} } }), ...overrides };
}

test('click sends only a user message requesting the mesh skill', async () => {
  const { button, status } = ui();
  const calls = [];
  await setupInvite(host({ sendMessage: async (message) => { calls.push(message); return {}; } }), button, status);
  assert.equal(calls.length, 0);
  assert.equal(button.disabled, false);
  await button.click();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].role, 'user');
  assert.match(calls[0].content[0].text, /fulcra-mesh/);
  assert.match(calls[0].content[0].text, /invite another user/);
  assert.match(calls[0].content[0].text, /First show me a copyable invitation prompt/);
  assert.match(calls[0].content[0].text, /my own verified Fulcra user ID/);
  assert.match(calls[0].content[0].text, /Do not ask for the other user's ID/);
  assert.match(calls[0].content[0].text, /optional context/);
  assert.match(calls[0].content[0].text, /draft an outgoing message/);
  assert.match(calls[0].content[0].text, /Get my go-ahead before creating/);
  assert.match(status.textContent, /Request sent/);
});

test('disable while pending; rejection allows retry without claiming an invitation', async () => {
  const { button, status } = ui();
  let finish;
  await setupInvite(host({ sendMessage: () => new Promise(resolve => { finish = resolve; }) }), button, status);
  const pending = button.click();
  assert.equal(button.disabled, true);
  finish({ isError: true });
  await pending;
  assert.equal(button.disabled, false);
  assert.match(status.textContent, /Could not send/);
});

test('unsupported host and failed connection leave button disabled', async () => {
  for (const app of [host({ getHostCapabilities: () => ({}) }), host({ connect: async () => { throw Error('offline'); } })]) {
    const { button, status } = ui();
    await setupInvite(app, button, status);
    assert.equal(button.disabled, true);
    assert.ok(status.textContent);
  }
});
