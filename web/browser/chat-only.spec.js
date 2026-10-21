import { test, expect } from '@playwright/test';
import { open, readOnlyThread } from './harness.js';

const contexts = page => page.evaluate(() => window.contexts.map(c => c.content?.[0]?.text ?? ''));

test('chat-only replaces controls with copyable instructions and keeps context', async ({ page }) => {
  const ui = await open(page, 900, { controls: 'chat', checkStatus: { status: 'not_set_up' } });
  const instruction = text => ui.locator('.chat-instruction').filter({ hasText: text });

  // No composer, chat handoff, invite or setup buttons.
  for (const name of [/^Invite someone/, /^Send/, /^Continue in/, /^Set up automatic checking/]) {
    await expect(ui.getByRole('button', { name })).toHaveCount(0);
  }
  await expect(ui.locator('#thread-composer textarea')).toHaveCount(0);
  await expect(instruction('Ask synthetic to reply to Weekend')).toBeVisible();
  await expect(instruction('Ask synthetic to invite someone’s agent').first()).toBeVisible();
  await expect(instruction('Ask synthetic to show my open invitation').first()).toBeVisible();
  await expect(instruction('Ask synthetic to set up automatic checking').first()).toBeVisible();
  // Monospace and purple, but not a button.
  const style = await instruction('reply to Weekend').evaluate(el => ({
    font: getComputedStyle(el).fontFamily, color: getComputedStyle(el).color, role: el.getAttribute('role') }));
  expect(style.font).toMatch(/mono/i); expect(style.color).toBe('rgb(123, 97, 255)'); expect(style.role).toBeNull();

  // The copy button copies the request without "Ask <host> to".
  const reply = instruction('reply to Weekend');
  await reply.evaluate(el => Object.defineProperty(el.ownerDocument.defaultView.navigator, 'clipboard',
    { configurable: true, value: { writeText: async text => { el.ownerDocument.defaultView.copied = text; } } }));
  await reply.getByRole('button', { name: 'Copy “Reply to Weekend”' }).click();
  await expect(reply.getByRole('button', { name: 'Copied' })).toBeVisible();
  expect(await reply.evaluate(el => el.ownerDocument.defaultView.copied)).toBe('Reply to Weekend');

  // General app context plus the selected thread are published; nothing is sent to chat.
  await expect.poll(async () => (await contexts(page)).at(-1)).toContain('Broadcast message');
  const latest = (await contexts(page)).at(-1);
  expect(latest).toContain('Fulcra Agents I Know');
  expect(latest).toContain('set-up-agent-contacts');
  expect(await page.evaluate(() => window.hostMessages)).toEqual([]);
  await page.screenshot({ path: 'test-results/chat-only.png' });
  // Opening still acknowledges as before.
  expect(await page.evaluate(() => window.calls.some(c => c.name === 'agent_connection_send' && c.arguments.kind === 'ack'))).toBe(true);
});

test('chat-only publishes general context before any contact loads', async ({ page }) => {
  await open(page, 900, { controls: 'chat', listOnly: true, holdReads: true });
  await expect.poll(async () => (await contexts(page))[0]).toContain('Fulcra Agents I Know');
  expect((await contexts(page))[0]).not.toContain('Selected connection thread');
});

test('chat-only thread panel shows the reply instruction', async ({ page }) => {
  const ui = await open(page, 900, { ...readOnlyThread, controls: 'chat' });
  await expect.poll(async () => (await contexts(page)).at(-1)).toContain('Broadcast message');
  await expect(ui.locator('#thread-composer .chat-instruction')).toHaveText('Ask synthetic to reply to Weekend');
});
