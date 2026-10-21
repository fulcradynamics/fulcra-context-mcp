import { test, expect } from '@playwright/test';
import { open, own } from './harness.js';

async function standing(page, options = {listOnly: true}) {
  const ui = await open(page, 900, options);
  await page.locator('iframe').evaluate(el => el.style.height = '1100px');
  return ui;
}
const calls = page => page.evaluate(() => window.calls.filter(c => c.name === 'standing_agent_invitation').map(c => c.arguments));

test('Copy open invitation shows the standing invitation with a live, saved name', async ({page}) => {
  const ui = await standing(page);
  await ui.locator('#open-invite').click();
  const modal = ui.getByRole('dialog', {name: 'Share this with anyone'});
  await expect(modal).toContainText('isn’t for anyone in particular');
  const text = modal.getByLabel('Open invitation');
  await expect(text).toHaveValue(new RegExp(`connect with Fulcra user ${own}\\.`));
  await expect(text).toHaveValue(/topic exactly `open_invitation f{32}`/);
  await modal.getByLabel('Your name in this invitation').fill('Leif');
  await expect(text).toHaveValue(new RegExp(`connect with Leif's synthetic, Fulcra user ${own}\\.`));
  await page.screenshot({path: `${process.env.TMPDIR ?? '../test-results'}/standing-invitation.png`});
  await modal.getByRole('button', {name: 'Done'}).click();
  await expect(modal).toHaveCount(0);
  expect(await calls(page)).toEqual([{}, {inviter_name: 'Leif'}]);
  expect(await page.evaluate(() => window.hostMessages.length)).toBe(0);
});

test('Escape discards name edits', async ({page}) => {
  const ui = await standing(page);
  await page.evaluate(() => { window.standingName = 'Leif'; });
  await ui.locator('#open-invite').click();
  const name = ui.getByRole('dialog', {name: 'Share this with anyone'}).getByLabel('Your name in this invitation');
  await expect(name).toHaveValue('Leif');
  await name.fill('');
  await page.keyboard.press('Escape');
  await expect(ui.getByRole('dialog')).toHaveCount(0);
  expect(await calls(page)).toEqual([{}]);
});

test('Invite someone pre-fills the saved name', async ({page}) => {
  const ui = await standing(page);
  await page.evaluate(() => { window.standingName = 'Leif'; });
  await ui.locator('#invite').click();
  await expect(ui.getByRole('dialog', {name: 'Invite someone'}).getByLabel('Your name')).toHaveValue('Leif');
});

test('empty state shows both invite actions', async ({page}) => {
  const ui = await standing(page, {listOnly: true, autoSelect: false});
  const invite = ui.locator('#invite-welcome'), openInvite = ui.locator('#open-invite-welcome');
  await expect(openInvite).toBeVisible();
  await expect(invite).toBeVisible();
});
