import { test, expect } from '@playwright/test';
import { open, peer, other, incoming } from './harness.js';

const weekend = ui => ui.locator('#connections .thread-button').filter({ hasText: 'Weekend' });
const requestCounts = () => ({
  latest: window.calls.filter(c => c.name === 'get_records' && c.arguments.latest).length,
  catalog: window.calls.filter(c => c.name === 'get_data_catalog').length,
  shares: window.calls.filter(c => c.name === 'list_shares').length,
});

test('opening a contact shows its preview while history is pending', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, autoSelect: false });
  await expect(ui.locator('#connections-loading')).toBeHidden();
  const before = await page.evaluate(requestCounts);
  await page.evaluate(() => { window.holdReads = 'history'; });
  await weekend(ui).click();
  await expect.poll(() => page.evaluate(() => window.heldReads.length)).toBe(3);
  await expect(ui.locator('#messages .message-row')).toHaveCount(1);
  await expect(ui.locator('#messages')).toContainText('Broadcast message');
  await expect(ui.locator('#message-loading')).toBeVisible();
  expect(await page.evaluate(requestCounts)).toEqual(before);
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message'))).toEqual([]);
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await expect(ui.locator('#message-loading')).toBeHidden();
});

for (const targeted of [false, true]) test(`${targeted ? 'targeted' : 'automatic'} opening reuses the preview before history arrives`, async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, holdReads: 'history',
    ...(targeted ? { direct: true, presentation: 'thread', launchPeer: peer, holdLaunch: true } : {}) });
  await expect(ui.locator('#connections-loading')).toBeHidden();
  if (targeted) await page.evaluate(() => window.releaseLaunch());
  await expect(ui.locator('#messages .message-row')).toHaveCount(1);
  await expect(ui.locator('#message-loading')).toBeVisible();
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message'))).toEqual([]);
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  await expect(ui.locator('#message-loading')).toBeHidden();
});

test('switching contacts replaces the provisional message and ignores late history', async ({ page }) => {
  const message = (id, body, time) => ({ id, body, kind: 'message', sender: 'Peer', start_time: `2026-10-13T${time}:00Z` });
  const ui = await open(page, 900, { listOnly: true, autoSelect: false, direct: true, channelRecords: {
    [JSON.stringify([peer, incoming])]: [message('alex', 'Alex latest', '11:00')],
    [JSON.stringify([other, incoming])]: [message('chris', 'Chris latest', '11:59')],
  } });
  await expect(ui.locator('#connections-loading')).toBeHidden();
  await page.evaluate(() => { window.holdReads = 'history'; });
  await ui.locator('#connections .thread-button').filter({ hasText: 'Alex' }).filter({ hasNotText: 'Weekend' }).click();
  await expect(ui.locator('#messages')).toContainText('Alex latest');
  await weekend(ui).click();
  await expect(ui.locator('#messages')).toContainText('Chris latest');
  await expect(ui.locator('#messages')).not.toContainText('Alex latest');
  await expect.poll(() => page.evaluate(() => window.heldReads.length)).toBe(5);
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  await expect(ui.locator('#message-title')).toHaveText('Weekend');
  await expect(ui.locator('#messages .message-row')).toHaveCount(2);
});

test('failed history retains the preview as stale without acknowledging', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, autoSelect: false });
  await expect(ui.locator('#connections-loading')).toBeHidden();
  await page.evaluate(() => { window.failHistory = true; });
  await weekend(ui).click();
  await expect(ui.locator('#message-status')).toContainText('Could not load messages');
  await expect(ui.locator('#messages .message-row')).toHaveCount(1);
  await expect.poll(() => page.evaluate(() => window.contexts.at(-1)?.content?.[0]?.text ?? '')).toContain('Stale');
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message'))).toEqual([]);
});

test('fresh history replaces rather than duplicates the provisional message', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, autoSelect: false });
  await expect(ui.locator('#connections-loading')).toBeHidden();
  await page.evaluate(() => { window.emptyRecords = true; window.holdReads = 'history'; });
  await weekend(ui).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(1);
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  await expect(ui.locator('#messages .message-row')).toHaveCount(0);
  await expect(ui.locator('#message-status')).toContainText('No messages');
});
