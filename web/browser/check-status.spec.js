import { test, expect } from '@playwright/test';
import { open } from './harness.js';

test('no schedule offers Start Checking, which asks the agent to set one up', async ({page}) => {
  const ui = await open(page, 900, {listOnly: true, checkStatus: {status: 'not_set_up', label: 'Not set up'}});
  const row = ui.locator('#check-status');
  await expect(row).toContainText('Your agent is not automatically checking for messages.');
  await row.getByRole('button', {name: 'Start Checking'}).click();
  await expect.poll(() => page.evaluate(() => window.hostMessages.length)).toBe(1);
  expect(JSON.stringify(await page.evaluate(() => window.hostMessages))).toContain('set-up-agent-contacts');
  await expect(ui.locator('#status')).toContainText('Request sent');
  await page.screenshot({path: `${process.env.TMPDIR ?? '../test-results'}/check-status-start.png`});
});

test('a schedule shows the last check and Check Now runs a check in chat', async ({page}) => {
  const ui = await open(page, 390, {listOnly: true, checkStatus: {status: 'checked', last_checked: '2026-10-13T11:40:00Z'}});
  const row = ui.locator('#check-status');
  await expect(row).toContainText('Your agent last checked for messages');
  await row.getByRole('button', {name: 'Check Now'}).click();
  await expect.poll(() => page.evaluate(() => window.hostMessages.length)).toBe(1);
  expect(JSON.stringify(await page.evaluate(() => window.hostMessages))).toContain('check-messages skill');
  await page.screenshot({path: `${process.env.TMPDIR ?? '../test-results'}/check-status-checked.png`});
});

test('unavailable status hides the row', async ({page}) => {
  const ui = await open(page, 900, {listOnly: true});
  await expect(ui.locator('#check-status')).toBeHidden();
});
