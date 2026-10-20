import { test, expect } from '@playwright/test';
import { open } from './harness.js';

test('no schedule shows the onboarding card and sets up checking in chat', async ({page}) => {
  const ui = await open(page, 900, {listOnly: true, checkStatus: {status: 'not_set_up'}});
  // The first contact auto-opens, so the sticky onboarding card shows atop the thread.
  const card = ui.locator('#onboarding-thread');
  await expect(card).toBeVisible();
  await expect(card).toContainText('automatically check for new messages');
  await card.getByRole('button', {name: 'Set up automatic checking'}).click();
  await expect.poll(() => page.evaluate(() => window.hostMessages.length)).toBe(1);
  expect(JSON.stringify(await page.evaluate(() => window.hostMessages))).toContain('set-up-agent-contacts');
  await expect(ui.locator('.toast')).toContainText('Request sent');
  await page.screenshot({path: `${process.env.TMPDIR ?? '../test-results'}/onboarding-card.png`});
});

test('dismissing the card moves setup into the Advanced panel', async ({page}) => {
  const ui = await open(page, 900, {listOnly: true, checkStatus: {status: 'not_set_up'}});
  const card = ui.locator('#onboarding-thread');
  await expect(card).toBeVisible();
  await expect(ui.locator('#onboarding-advanced')).toBeHidden();
  await card.getByRole('button', {name: 'Dismiss'}).click();
  await expect(card).toBeHidden();
  // The setup offer is still reachable from Advanced.
  await ui.locator('#advanced-toggle').click();
  await expect(ui.locator('#onboarding-advanced')).toBeVisible();
  await ui.locator('#onboarding-advanced').getByRole('button', {name: 'Set up automatic checking'}).click();
  await expect.poll(() => page.evaluate(() => window.hostMessages.length)).toBe(1);
  expect(JSON.stringify(await page.evaluate(() => window.hostMessages))).toContain('set-up-agent-contacts');
});

test('once a schedule exists, no onboarding card is shown', async ({page}) => {
  const ui = await open(page, 900, {listOnly: true, checkStatus: {status: 'checked', last_checked: '2026-10-13T11:40:00Z'}});
  await page.clock.runFor(11000);
  await expect(ui.locator('#onboarding-thread')).toBeHidden();
  await expect(ui.locator('#onboarding-advanced')).toBeHidden();
});
