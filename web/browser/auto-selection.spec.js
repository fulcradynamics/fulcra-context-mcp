import { test, expect } from '@playwright/test';
import { open, peer } from './harness.js';

test('initial selection waits for previews and chooses attention over discovery order', async ({page}) => {
  const ui = await open(page, 900, {listOnly:true, direct:true, holdReads:true,
    status:{attention:true,reason:'Decision needed',assessed_at:'2026-10-13T12:00:00Z'}});
  await expect(ui.locator('#connection-detail')).toBeHidden();
  await page.clock.runFor(11000);
  await expect(ui.locator('#connection-detail')).toBeHidden();
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  await expect(ui.locator('#message-title')).toHaveText('Weekend');
  await expect(ui.locator('#connections .thread-row').first()).toContainText('Weekend');
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message'))).toEqual([]);
  await ui.locator('.thread-button').filter({hasText:'Alex'}).click();
  await page.clock.runFor(11000);
  await expect(ui.locator('#message-title')).toHaveText('Alex');
  await expect(ui.locator('#connections .thread-row').first()).toContainText('Weekend');
});

test('global launch auto-selects the first contact without acknowledging or sending', async ({page}) => {
  const ui = await open(page, 900, {listOnly:true});
  await page.clock.runFor(11000);
  // The top contact opens on its own so the two-pane layout is never empty.
  await expect(ui.locator('.thread-button[aria-current="true"]')).toHaveCount(1);
  await expect(ui.locator('#selection-empty')).toBeHidden();
  await expect(ui.locator('#connection-detail')).toBeVisible();
  // Auto-selection only views; it must not acknowledge messages or hand off to chat.
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message'))).toEqual([]);
  expect(await page.evaluate(() => window.hostMessages)).toEqual([]);
});

test('delayed launch result cannot replace a user choice', async ({page}) => {
  const ui = await open(page, 900, {listOnly:true, presentation:'thread', holdLaunch:true, launchPeer:peer, direct:true});
  await expect(ui.locator('#connection-detail')).toBeHidden();
  await ui.locator('.thread-button').filter({hasText:'Weekend'}).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await page.evaluate(() => window.releaseLaunch());
  await page.clock.runFor(11000);
  await expect(ui.locator('#message-title')).toHaveText('Weekend');
});

test('missing explicit launch identity never falls back to the first contact', async ({page}) => {
  const ui = await open(page, 900, {listOnly:true, presentation:'thread', launchPeer:peer});
  await expect(ui.locator('#entrypoint-status')).toContainText('no other peer was selected');
  await page.clock.runFor(11000);
  await expect(ui.locator('#connection-detail')).toBeHidden();
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message'))).toEqual([]);
});

test('thread launch without a peer selects the highest sorted contact once', async ({page}) => {
  const ui = await open(page,900,{listOnly:true,presentation:'thread'});
  await expect(ui.locator('#selection-empty')).toBeHidden();
  await expect(ui.locator('#connections .thread-row').first().locator('.thread-button')).toHaveAttribute('aria-current', 'true');
  const title = await ui.locator('#message-title').textContent();
  await page.evaluate(() => { window.navigationContact = true; });
  await page.clock.runFor(11000);
  await expect(ui.locator('#message-title')).toHaveText(title);
  await expect(ui.locator('#entrypoint-status')).toHaveText('');
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message'))).toEqual([]);
});

test('an authorized explicit launch target opens read-only and is stable across list reorder', async ({page}) => {
  const ui = await open(page,900,{listOnly:true,presentation:'thread',launchPeer:peer,direct:true});
  await expect(ui.locator('#message-title')).toHaveText('Alex');
  await expect(ui.locator('#messages .message-row')).toHaveCount(3);
  await ui.locator('#connections').evaluate(el => el.prepend(el.lastElementChild));
  await page.clock.runFor(11000);
  await expect(ui.locator('#message-title')).toHaveText('Alex');
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message'))).toEqual([]);
});
