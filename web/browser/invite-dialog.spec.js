import { test, expect } from '@playwright/test';
import { open, own, peer } from './harness.js';

async function dialog(page) {
  const ui = await open(page, 900, {listOnly: true});
  await ui.getByRole('button', {name: 'Invite someone'}).click();
  return [ui, ui.getByRole('dialog', {name: 'Invite someone'})];
}

test('creates an invitation without the model and shows the copyable template', async ({page}) => {
  const [ui, modal] = await dialog(page);
  await modal.getByLabel('Your name').fill('Leif');
  await modal.getByLabel('Their name').fill('Lucian');
  await modal.getByLabel(/Their Fulcra user ID/).fill(peer.toUpperCase());
  await page.screenshot({path: `${process.env.TMPDIR ?? '../test-results'}/invite-dialog.png`});
  await modal.getByRole('button', {name: 'Create invitation'}).click();
  const template = ui.getByRole('dialog', {name: 'Invitation for Lucian'}).getByLabel('Invitation');
  await expect(template).toHaveValue(new RegExp(`connect with Leif's synthetic, Fulcra user ${own}\\.`));
  await expect(template).toHaveValue(/topic exactly `handshake 0123456789abcdef0123456789abcdef`/);
  await page.screenshot({path: `${process.env.TMPDIR ?? '../test-results'}/invite-template.png`});
  const calls = await page.evaluate(() => window.calls.filter(c => c.name === 'create_agent_invitation').map(c => c.arguments));
  expect(calls).toEqual([{inviter_name: 'Leif', recipient_name: 'Lucian', recipient_userid: peer}]);
  expect(await page.evaluate(() => window.hostMessages.length)).toBe(0);
});

test('Continue in chat carries what was entered', async ({page}) => {
  const [ui, modal] = await dialog(page);
  await modal.getByLabel('Their name').fill('Lucian');
  await modal.getByRole('button', {name: 'Continue in chat'}).click();
  await expect.poll(() => page.evaluate(() => window.hostMessages.length)).toBe(1);
  const text = JSON.stringify(await page.evaluate(() => window.hostMessages));
  expect(text).toContain('use the invite skill');
  expect(text).toContain('Details I already entered: their name: Lucian.');
  await expect(ui.getByRole('dialog')).toHaveCount(0);
  expect(await page.evaluate(() => window.calls.some(c => c.name === 'create_agent_invitation'))).toBe(false);
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
