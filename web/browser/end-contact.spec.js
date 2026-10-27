import { test, expect } from '@playwright/test';
import { open, peer, out } from './harness.js';

async function oneToOne(page) {
  const ui = await open(page, 900, {listOnly: true});
  await page.evaluate(peer => { window.audience = [peer]; }, peer);
  await page.clock.runFor(11000);
  await ui.locator('.thread-button').filter({hasText: 'Weekend'}).click();
  await ui.getByRole('button', {name: 'Advanced'}).click();
  return ui;
}

for (const archive of [false, true]) test(`End contact confirms in a modal, archive ${archive}`, async ({page}) => {
  const ui = await oneToOne(page);
  await page.evaluate(() => { window.remainingBroadAccess = true; });
  await ui.getByRole('button', {name: 'End contact'}).click();
  const dialog = ui.getByRole('dialog', {name: 'End contact with Weekend?'});
  await expect(dialog).toContainText('What they share with you is not changed.');
  await expect(dialog).toContainText('Broader shares remain unchanged and may still allow access');
  await expect(dialog).not.toContainText('will no longer be able to read');
  if (archive) await dialog.getByLabel(/archive your messages/).check();
  await page.screenshot({path: `${process.env.TMPDIR ?? '../test-results'}/end-contact-${archive}.png`});
  await dialog.getByRole('button', {name: 'End contact'}).click();
  await expect(ui.locator('#status')).toContainText('Ended contact with Weekend.');
  await expect(ui.locator('#status')).toContainText('Broader shares remain and may still allow access');
  const calls = await page.evaluate(() => window.calls.filter(c => c.name === 'end_agent_contact').map(c => c.arguments));
  expect(calls).toEqual([{data_type: out, peer_userid: peer, archive}]);
  await expect(ui.locator('#connection-detail')).toBeHidden();
});

test('Cancel ends nothing', async ({page}) => {
  const ui = await oneToOne(page);
  await ui.getByRole('button', {name: 'End contact'}).click();
  await ui.getByRole('dialog').getByRole('button', {name: 'Cancel'}).click();
  await expect(ui.getByRole('dialog')).toHaveCount(0);
  expect(await page.evaluate(() => window.calls.some(c => c.name === 'end_agent_contact'))).toBe(false);
});

test('group conversations do not offer End contact', async ({page}) => {
  const ui = await open(page);
  await ui.getByRole('button', {name: 'Advanced'}).click();
  await expect(ui.locator('#end-contact')).toBeHidden();
});
