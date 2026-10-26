import { test, expect } from '@playwright/test';
import { open, peer, out, incoming } from './harness.js';

test('ordinary descriptions and share names retain usable contacts after refresh', async ({page}) => {
  const ui = await open(page, 900, {listOnly: true, autoSelect: false});
  await page.evaluate(peer => {
    window.unmarkedChannels = true;
    window.audience = [peer];
  }, peer);
  await page.clock.runFor(11000);
  await expect(ui.locator('#connections .thread-row')).toHaveCount(1);
  expect(await page.evaluate(() => window.calls.some(c => ['create_share', 'update_data_type', 'send_agent_contact_message'].includes(c.name)))).toBe(false);
  await ui.locator('#connections .thread-row').click();
  await expect(ui.locator('#messages')).toContainText('Broadcast message');
});

test('two saved pairs select exact history and reply through the corresponding outbox', async ({page}) => {
  const ui = await open(page, 900, {listOnly: true, autoSelect: false});
  await page.evaluate(() => { window.pairedChannels = true; });
  await page.clock.runFor(11000);
  await ui.locator('#connections .thread-row').click();
  await ui.locator('#advanced-toggle').click();
  await ui.locator('.delivery-address summary').click();
  const selector = ui.locator('.delivery-address select');
  await expect(selector).toHaveValue('');
  await expect(ui.locator('.composer-hint')).toContainText('Choose an outbox');
  await expect(ui.locator('#messages')).not.toContainText('paired message');
  await selector.selectOption(out);
  await expect(ui.locator('#messages')).toContainText('First paired message');
  await expect(ui.locator('#messages')).not.toContainText('Second paired message');
  await expect(ui.locator('.incoming-sources')).toBeVisible();
  await page.clock.runFor(11000);
  await expect(selector).toHaveValue(out);
  expect(await page.evaluate(secondIn => window.calls.some(c => c.name === 'get_records' && c.arguments.data_type === secondIn), incoming.slice(0,-1)+'9')).toBe(false);
  await ui.locator('.composer-input').fill('Reply to first');
  await ui.locator('.send-to-peer').click();
  await expect.poll(() => page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message' && c.arguments.kind === 'reply').map(c => c.arguments))).toEqual([
    expect.objectContaining({outbox: out, in_reply_to: incoming+'-message'}),
  ]);
  await selector.selectOption(out.slice(0,-1)+'8');
  await expect(ui.locator('#messages')).toContainText('Second paired message');
  await expect(ui.locator('#messages')).not.toContainText('First paired message');
  await ui.locator('.composer-input').fill('Reply to second');
  await ui.locator('.send-to-peer').click();
  await expect.poll(() => page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message' && c.arguments.kind === 'reply').map(c => c.arguments))).toEqual([
    expect.objectContaining({outbox: out, in_reply_to: incoming+'-message'}),
    expect.objectContaining({outbox: out.slice(0,-1)+'8', in_reply_to: incoming.slice(0,-1)+'9-message'}),
  ]);
});
