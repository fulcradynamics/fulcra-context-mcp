import { test, expect } from '@playwright/test';
import { open, peer } from './harness.js';

test('global launch selects the first contact read-only and polling keeps selection', async ({page}) => {
  const ui = await open(page, 900, {listOnly:true});
  await expect(ui.locator('#message-title')).toHaveText('Weekend');
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await expect(ui.locator('#message-back')).toHaveCount(0);
  await page.clock.runFor(11000);
  await expect(ui.locator('.thread-button[aria-current="true"]')).toContainText('Weekend');
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'agent_connection_send'))).toEqual([]);
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
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'agent_connection_send'))).toEqual([]);
});

test('thread launch without a peer selects the first contact without redundant instructions', async ({page}) => {
  const ui = await open(page,900,{listOnly:true,presentation:'thread'});
  await expect(ui.locator('#message-title')).toHaveText('Weekend');
  await expect(ui.locator('#entrypoint-status')).toHaveText('');
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'agent_connection_send'))).toEqual([]);
});

test('an authorized explicit launch target opens read-only and is stable across list reorder', async ({page}) => {
  const ui = await open(page,900,{listOnly:true,presentation:'thread',launchPeer:peer,direct:true});
  await expect(ui.locator('#message-title')).toHaveText('Alex');
  await expect(ui.locator('#messages .message-row')).toHaveCount(3);
  await ui.locator('#connections').evaluate(el => el.prepend(el.lastElementChild));
  await page.clock.runFor(11000);
  await expect(ui.locator('#message-title')).toHaveText('Alex');
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'agent_connection_send'))).toEqual([]);
});
