import { test, expect } from '@playwright/test';
import { open, peer, other, out, incoming } from './harness.js';

const alex = ui => ui.locator('#connections .thread-button').filter({ hasText: 'Alex' }).filter({ hasNotText: 'Weekend' });

test('completed contacts appear while unrelated previews remain loading', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, waitForContacts: false, holdReads: other, direct: true });
  await expect(alex(ui)).toBeVisible();
  await expect(alex(ui).locator('.thread-preview')).toHaveText('Broadcast message');
  await expect(ui.locator('#connections-loading')).toBeVisible();
  await expect(ui.locator('#connections .thread-button').filter({ hasText: 'Weekend' })).toBeHidden();
  await expect(ui.locator('#connection-detail')).toBeHidden();
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  await expect(ui.locator('#connections-loading')).toBeHidden();
  await expect(ui.locator('#connection-detail')).toBeVisible();
});

test('opening a completed contact does not wait for unrelated previews or rediscover', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, waitForContacts: false, holdReads: other, direct: true });
  await expect(alex(ui)).toBeVisible();
  const counts = () => page.evaluate(() => ({
    catalog: window.calls.filter(c => c.name === 'get_data_catalog').length,
    shares: window.calls.filter(c => c.name === 'list_shares').length,
    latest: window.calls.filter(c => c.name === 'get_records' && c.arguments.latest).length,
  }));
  const before = await counts();
  expect(before).toEqual({ catalog: 1, shares: 1, latest: 4 });
  await alex(ui).click();
  await expect(ui.locator('#messages')).toContainText('Broadcast message');
  await expect(ui.locator('#connections-loading')).toBeVisible();
  expect(await counts()).toEqual(before);
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  await expect(ui.locator('#connections-loading')).toBeHidden();
  await ui.locator('#connections .thread-button').filter({ hasText: 'Weekend' }).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await alex(ui).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(3);
  expect(await counts()).toEqual(before);
});

for (const failHistory of [false, true]) test(`ACK-only preview distinguishes no content from read failure: ${failHistory}`, async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, autoSelect: false, failHistory,
    ownRecords: [{ id: 'receipt', kind: 'ack', sender: 'me', body: 'ack', start_time: '2026-10-13T11:30:00Z' }],
    channelRecords: { [JSON.stringify([peer, incoming])]: [], [JSON.stringify([other, incoming])]: [] },
  });
  const row = ui.locator('#connections .thread-button').filter({ hasText: 'Weekend' });
  await expect(row.locator('.thread-preview')).toHaveText(failHistory ? 'Preview unavailable' : 'No message found within 30 days');
  await expect(ui.locator('#connections-loading')).toBeHidden();
  const reads = await page.evaluate(() => window.calls.filter(c => c.name === 'get_records' && !c.arguments.latest));
  expect(reads).toHaveLength(1);
  expect(reads[0].arguments.data_type).toBe(out);
  await row.click();
  await expect.poll(() => page.evaluate(() => window.calls.filter(c => c.name === 'get_records' && !c.arguments.latest).length)).toBe(4);
  const history = await page.evaluate(() => window.calls.filter(c => c.name === 'get_records' && !c.arguments.latest).slice(1));
  expect(history.every(c => c.arguments.start_time === '2026-10-06T11:30:00.000Z')).toBe(true);
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'get_records' && c.arguments.latest).length)).toBe(3);
});

test('failed ACK fallback drains held incoming latest before completing a multiparty preview', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, waitForContacts: false, autoSelect: false,
    holdReads: other, failHistory: true,
    ownRecords: [{ id: 'receipt', kind: 'ack', sender: 'me', body: 'ack', start_time: '2026-10-13T11:30:00Z' }],
  });
  const fallbacks = () => page.evaluate(() => window.calls.filter(c => c.name === 'get_records' && !c.arguments.latest).length);
  await expect.poll(fallbacks).toBe(1);
  await expect.poll(() => page.evaluate(() => window.heldReads.length)).toBe(1);
  await expect(ui.locator('#connections-loading')).toBeVisible();
  const row = ui.locator('#connections .thread-button').filter({ hasText: 'Weekend' });
  await expect(row).toBeHidden();
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  await expect(row.locator('.thread-preview')).toHaveText('Preview unavailable');
  await expect(row).toBeVisible();
  await expect(ui.locator('#connections-loading')).toBeHidden();
  expect(await fallbacks()).toBe(1);
});

test('external discovery failure fences a selected read already using the cached roster', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, autoSelect: false });
  await expect(ui.locator('#connections-loading')).toBeHidden();
  await page.evaluate(() => { window.holdReads = 'history'; window.failDiscovery = true; });
  await ui.locator('#connections .thread-button').filter({ hasText: 'Weekend' }).click();
  await expect.poll(() => page.evaluate(() => window.heldReads.length)).toBe(3);
  await page.clock.runFor(11000);
  await expect(ui.locator('#connection-status')).toContainText('Couldn’t refresh contacts');
  await expect(ui.locator('#message-status')).toContainText('Could not load messages');
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  // Released history must not restore fresh context or acknowledge the contact.
  await expect.poll(() => page.evaluate(() => window.contexts.at(-1)?.content?.[0]?.text ?? '')).toContain('Stale');
  await expect(ui.locator('#message-status')).toContainText('Could not load messages');
  // The list preview remains as stale evidence, not a completed history read.
  await expect(ui.locator('#messages .message-row')).toHaveCount(1);
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message'))).toEqual([]);
});

test('selection after discovery failure waits for fresh discovery before reading records', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, autoSelect: false });
  await expect(ui.locator('#connections-loading')).toBeHidden();
  await page.evaluate(() => { window.failDiscovery = true; });
  await page.clock.runFor(11000);
  await expect(ui.locator('#connection-status')).toContainText('Couldn’t refresh contacts');
  await page.evaluate(() => { window.failDiscovery = false; window.holdDiscovery = true; window.calls = []; });
  await ui.locator('#connections .thread-button').filter({ hasText: 'Weekend' }).click();
  await expect.poll(() => page.evaluate(() => window.heldDiscovery.length)).toBe(2);
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'get_records'))).toEqual([]);
  await page.evaluate(() => { window.holdDiscovery = false; window.releaseDiscovery(); });
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
});

test('ordinary background reads keep visible rows without the initial loading spinner', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, autoSelect: false });
  await expect(ui.locator('#connections-loading')).toBeHidden();
  const row = ui.locator('#connections .thread-button').filter({ hasText: 'Weekend' });
  await expect(row).toBeVisible();
  await page.evaluate(() => { window.holdReads = true; });
  await page.clock.runFor(11000);
  await expect.poll(() => page.evaluate(() => window.heldReads.length)).toBe(3);
  await expect(row).toBeVisible();
  await expect(ui.locator('#connections-loading')).toBeHidden();
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  await expect(row.locator('.thread-preview')).toHaveText('Broadcast message');
  await expect(ui.locator('#connections-loading')).toBeHidden();
});

test('late explicit target reuses the initial roster while unrelated previews are held', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, waitForContacts: false, direct: true,
    holdReads: other, presentation: 'thread', holdLaunch: true, launchPeer: peer });
  await expect(alex(ui)).toBeVisible();
  await page.evaluate(() => window.releaseLaunch());
  await expect(ui.locator('#message-title')).toHaveText('Alex');
  await expect(ui.locator('#messages .message-row')).toHaveCount(3);
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'get_data_catalog').length)).toBe(1);
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'list_shares').length)).toBe(1);
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'get_records' && c.arguments.latest).length)).toBe(4);
});

test('a late exact target missing from the loaded roster is found by a fresh discovery', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, presentation: 'thread', holdLaunch: true, launchPeer: 'navigation-peer' });
  await expect(ui.locator('#connections-loading')).toBeHidden();
  await page.evaluate(() => { window.navigationContact = true; window.releaseLaunch(); });
  await expect(ui.locator('#message-title')).toHaveText('Quiet contact');
});
