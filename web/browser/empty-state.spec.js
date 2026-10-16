import { test, expect } from '@playwright/test';
import { open } from './harness.js';

const emptyText = 'Contacts that you’ve invited (or that have invited you) will show here when the connection is complete.';

for (const presentation of ['global', 'threads']) test(`empty contacts offer an invitation without panel guidance: ${presentation}`, async ({page}) => {
  const ui = await open(page, 390, {listOnly: true, presentation});
  await expect(ui.locator('#connections-empty')).toBeHidden();
  await page.evaluate(() => { window.excludeOwn = true; window.excludeOut = true; window.excludeIncoming = true; });
  await page.clock.runFor(11000);
  await expect(ui.locator('#connections-empty')).toBeVisible();
  await expect(ui.locator('#connections-empty')).toHaveText(new RegExp(emptyText.replace(/[()]/g, '\\$&')));
  await expect(ui.locator('#connections')).toBeHidden();
  await expect(ui.locator('body')).not.toContainText('conversation panel');
  await page.screenshot({path: `${process.env.TMPDIR ?? '../test-results'}/empty-state-${presentation}.png`});
  const invite = ui.getByRole('button', {name: 'Invite a new contact'});
  await expect(invite).toBeEnabled();
  await invite.click();
  await expect.poll(() => page.evaluate(() => window.hostMessages.length)).toBe(1);
  expect(JSON.stringify(await page.evaluate(() => window.hostMessages))).toContain('use the invite skill');
  await expect(ui.locator('#status')).toContainText('Request sent');
  await page.evaluate(() => { window.excludeOwn = false; window.excludeOut = false; window.excludeIncoming = false; });
  await page.clock.runFor(11000);
  await expect(ui.locator('#connections-empty')).toBeHidden();
  await expect(ui.locator('#connections .thread-row')).toHaveCount(1);
});

test('failed first discovery does not claim an empty contact list', async ({page}) => {
  const ui = await open(page, 900, {listOnly: true});
  await page.evaluate(() => { window.failDiscovery = true; window.excludeOwn = true; window.excludeOut = true; window.excludeIncoming = true; });
  await page.clock.runFor(11000);
  await expect(ui.locator('#connection-status')).toContainText('Couldn’t refresh contacts');
  await expect(ui.locator('#connections-empty')).toBeHidden();
});

for (const width of [390, 1100]) test(`pending Ask my agent is right-aligned like Convert to Contact at ${width}`, async ({page}) => {
  const ui = await open(page, width, {listOnly: true});
  await page.evaluate(() => { window.excludeOut = true; });
  await page.clock.runFor(11000);
  const row = ui.locator('#pending-connections > li').first();
  const box = await row.boundingBox(), button = await row.locator('.pending-assist').boundingBox();
  const label = await row.locator('.pending-label').boundingBox();
  expect(Math.abs(box.x + box.width - 16 - (button.x + button.width))).toBeLessThan(1);
  expect(button.x).toBeGreaterThan(label.x + label.width);
  expect(Math.abs(box.y + box.height / 2 - (button.y + button.height / 2))).toBeLessThan(1);
});
