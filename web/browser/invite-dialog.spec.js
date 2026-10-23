import { test, expect } from '@playwright/test';
import { open, own, peer } from './harness.js';

async function dialog(page) {
  const ui = await open(page, 900, {listOnly: true});
  // Fit the frame to the viewport so the centered modal is on screen.
  await page.locator('iframe').evaluate(el => el.style.height = '1100px');
  await ui.locator('#invite').click();
  return [ui, ui.getByRole('dialog', {name: 'Invite someone'})];
}

test('creates an invitation without the model and shows the copyable template', async ({page}) => {
  const [ui, modal] = await dialog(page);
  await modal.getByLabel('Your name').fill('Leif');
  await modal.getByLabel('Their name').fill('Lucian');
  await modal.getByLabel(/Fulcra User ID/).fill(peer.toUpperCase());
  await page.screenshot({path: `${process.env.TMPDIR ?? '../test-results'}/invite-dialog.png`});
  await modal.getByRole('button', {name: 'Create invitation'}).click();
  const template = ui.getByRole('dialog', {name: 'Send Invitation to Lucian'}).getByLabel('Invitation');
  await expect(template).toHaveValue(new RegExp(`connect with Leif's synthetic, Fulcra user ${own}\\.`));
  await expect(template).toHaveValue(/topic exactly `handshake 0123456789abcdef0123456789abcdef`/);
  await page.screenshot({path: `${process.env.TMPDIR ?? '../test-results'}/invite-template.png`});
  const calls = await page.evaluate(() => window.calls.filter(c => c.name === 'create_agent_invitation').map(c => c.arguments));
  expect(calls).toEqual([{inviter_name: 'Leif', recipient_name: 'Lucian', recipient_userid: peer}]);
  expect(await page.evaluate(() => window.hostMessages.length)).toBe(0);
});

test('the footer points to chat for more invitations, with no handoff button', async ({page}) => {
  const [, modal] = await dialog(page);
  await expect(modal.locator('.dialog-alt')).toContainText('create more invitations later by asking');
  await expect(modal.getByRole('button', {name: /Continue in /})).toHaveCount(0);
});

test('names are required and failures stay in the dialog', async ({page}) => {
  const [, modal] = await dialog(page);
  await modal.getByRole('button', {name: 'Create invitation'}).click();
  expect(await page.evaluate(() => window.calls.some(c => c.name === 'create_agent_invitation'))).toBe(false);
  await page.evaluate(() => { window.failInvite = true; });
  await modal.getByLabel('Your name').fill('Leif');
  await modal.getByLabel('Their name').fill('Lucian');
  await modal.getByRole('button', {name: 'Create invitation'}).click();
  await expect(modal.getByRole('alert')).toContainText('Synthetic denial.');
  await expect(modal.getByRole('button', {name: 'Create invitation'})).toBeEnabled();
});
