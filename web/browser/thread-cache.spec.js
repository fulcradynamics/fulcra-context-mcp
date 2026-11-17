import { test, expect } from '@playwright/test';
import { open, out, peer, incoming } from './harness.js';

const weekend = ui => ui.locator('#connections .thread-button').filter({ hasText: 'Weekend' });
const alex = ui => ui.locator('#connections .thread-button').filter({ hasText: 'Alex' }).filter({ hasNotText: 'Weekend' });

test('returning to a thread immediately restores its loaded messages and expanded window', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, autoSelect: false, direct: true });
  await expect(ui.locator('#connections-loading')).toBeHidden();
  await weekend(ui).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await expect(ui.locator('#message-loading')).toBeHidden();
  const initial = await page.evaluate(() => window.calls.filter(c => c.name === 'get_records' && !c.arguments.latest).at(-1).arguments.start_time);
  await ui.locator('#message-more').click();
  await expect(ui.locator('#more-spinner')).toHaveCSS('visibility', 'hidden');
  const expanded = await page.evaluate(() => window.calls.filter(c => c.name === 'get_records' && !c.arguments.latest).at(-1).arguments.start_time);
  expect(Date.parse(initial) - Date.parse(expanded)).toBe(14 * 86400000);
  await alex(ui).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(3);
  await expect(ui.locator('#message-loading')).toBeHidden();
  const before = await page.evaluate(() => ({
    latest: window.calls.filter(c => c.name === 'get_records' && c.arguments.latest).length,
    writes: window.calls.filter(c => c.name === 'send_agent_contact_message').length,
    catalog: window.calls.filter(c => c.name === 'get_agent_contact_catalog').length,
    shares: window.calls.filter(c => c.name === 'list_shares').length,
  }));
  await page.evaluate(() => { window.holdReads = 'history'; window.calls = window.calls.filter(c => c.name !== 'get_records' || c.arguments.latest); });
  await weekend(ui).click();
  await expect.poll(() => page.evaluate(() => window.heldReads.length)).toBe(3);
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await expect(ui.locator('#message-loading')).toBeVisible();
  const reads = await page.evaluate(() => window.calls.filter(c => c.name === 'get_records' && !c.arguments.latest));
  expect(reads.every(c => c.arguments.start_time === expanded)).toBe(true);
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'get_records' && c.arguments.latest).length)).toBe(before.latest);
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message').length)).toBe(before.writes);
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'get_agent_contact_catalog').length)).toBe(before.catalog);
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'list_shares').length)).toBe(before.shares);
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  await expect(ui.locator('#message-loading')).toBeHidden();
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
});

test('fresh history replaces cached records, including an empty result', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, autoSelect: false, direct: true });
  await weekend(ui).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await alex(ui).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(3);
  await page.evaluate(() => { window.emptyRecords = true; window.holdReads = 'history'; });
  await weekend(ui).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await expect.poll(() => page.evaluate(() => window.heldReads.length)).toBe(3);
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  await expect(ui.locator('#message-loading')).toBeHidden();
  await expect(ui.locator('#messages .message-row')).toHaveCount(0);
  await alex(ui).click();
  await expect(ui.locator('#message-loading')).toBeHidden();
  await page.evaluate(() => { window.holdReads = 'history'; });
  await weekend(ui).click();
  await expect.poll(() => page.evaluate(() => window.heldReads.length)).toBe(3);
  await expect(ui.locator('#messages .message-row')).toHaveCount(0);
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
});

test('a failed refresh keeps cached history as stale without acknowledging it', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, autoSelect: false, direct: true });
  await weekend(ui).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await alex(ui).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(3);
  const writes = await page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message').length);
  await page.evaluate(() => { window.failHistory = true; });
  await weekend(ui).click();
  await expect(ui.locator('#message-status')).toContainText('Could not load messages');
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await expect.poll(() => page.evaluate(() => window.contexts.at(-1)?.content?.[0]?.text ?? '')).toContain('Stale');
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message').length)).toBe(writes);
});

test('revocation removes a cached thread from the contact list', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, autoSelect: false, direct: true });
  await weekend(ui).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await alex(ui).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(3);
  await page.evaluate(() => { window.excludeIncoming = true; });
  await page.clock.runFor(11000);
  await expect(ui.locator('#messages .message-row')).toHaveCount(0);
  await expect(weekend(ui)).toBeHidden();
});

test('cached read warnings cannot restore a subsequently revoked source to context', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, autoSelect: false, direct: true, second: true });
  await weekend(ui).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await page.evaluate(() => { window.failHistory = true; });
  await page.clock.runFor(11000);
  await expect(ui.locator('#message-status')).toContainText('Could not load messages');
  await alex(ui).click();
  await expect(ui.locator('#message-status')).toContainText('Could not load messages');
  await page.evaluate(() => { window.failHistory = false; window.excludeOut = true; });
  await page.clock.runFor(45000);
  await expect(ui.locator('#messages .message-row')).toHaveCount(3);
  await page.evaluate(() => { window.holdReads = 'history'; });
  await weekend(ui).click();
  await expect.poll(() => page.evaluate(() => window.heldReads.length)).toBe(3);
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await expect.poll(() => page.evaluate(() => window.contexts.at(-1)?.content?.[0]?.text ?? '')).toContain('cached history');
  expect(await page.evaluate(() => window.contexts.at(-1).content[0].text)).not.toContain(out);
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
});

test('only fresh completed history can acknowledge a new message on returning to a cached thread', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, autoSelect: false, direct: true });
  await weekend(ui).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await alex(ui).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(3);
  const before = await page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message').length);
  await page.evaluate(({ peer, incoming }) => {
    window.channelRecords = { [JSON.stringify([peer, incoming])]: [
      { id: 'fresh-incoming', sender: 'Peer', kind: 'message', body: 'New incoming message', start_time: '2026-10-13T12:00:00Z' },
    ] };
    window.holdReads = 'history';
  }, { peer, incoming });
  await weekend(ui).click();
  await expect.poll(() => page.evaluate(() => window.heldReads.length)).toBe(3);
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message').length)).toBe(before);
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  await expect(ui.locator('#messages')).toContainText('New incoming message');
  await expect.poll(() => page.evaluate(n => window.calls.filter(c => c.name === 'send_agent_contact_message').slice(n).map(c => c.arguments.in_reply_to), before)).toEqual(['fresh-incoming']);
});
