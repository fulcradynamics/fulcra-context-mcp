import { test, expect } from '@playwright/test';
import { open, own, other } from './harness.js';

test('message artifacts list exact references and open the existing browser through explicit chat', async ({ page }) => {
  const ui = await open(page, 420, {listOnly:true, ownRecords:[{id:'with-file',kind:'message',sender:'chatgpt',body:'See attached',start_time:'2026-10-13T11:05:00Z',artifacts:[{path:'/shared/<report>.txt'},{path:'/shared/other.txt',owner:other,version:'sha-1'}]}]});
  await ui.locator('.thread-button').filter({hasText:'Weekend'}).click();
  await expect(ui.locator('.artifact')).toHaveCount(2);
  expect(await page.evaluate(() => window.hostMessages)).toEqual([]);
  const row = ui.locator('.artifact').first();
  await expect(row).toContainText('/shared/<report>.txt');
  await row.getByRole('button', {name:'Open file in synthetic'}).click();
  await expect(row.getByRole('status')).toContainText('Request sent to chat');
  const messages = await page.evaluate(() => window.hostMessages);
  expect(messages).toHaveLength(1);
  expect(messages[0].content[0].text).toContain(JSON.stringify({path:'/shared/<report>.txt',fulcra_userid:own}));
  await expect(row.getByRole('button')).toBeDisabled();
  expect(await page.evaluate(() => window.calls.some(c => ['list_files','read_file','create_share','write_file'].includes(c.name)))).toBe(false);
  await page.screenshot({path:'test-results/artifacts-narrow.png',fullPage:true});
  await page.setViewportSize({width:1000,height:1100});
  await expect(row.getByText('/shared/<report>.txt', {exact:true})).toBeVisible();
  await page.screenshot({path:'test-results/artifacts-wide.png',fullPage:true});
});

for (const navigate of [false, true]) test(`uncertain file handoff locks duplicate sends; navigation=${navigate}`, async ({page}) => {
  const ui = await open(page, 900, {listOnly:true, ownRecords:[{id:'file',kind:'message',body:'File',sender:'chatgpt',start_time:'2026-10-13T11:05:00Z',artifacts:[{path:'/shared/file.txt'}]}]});
  await ui.locator('.thread-button').filter({hasText:'Weekend'}).click();
  await page.evaluate(() => {window.holdMessages=true; window.rejectMessages=true;});
  const button = ui.getByRole('button', {name:'Open file in synthetic'});
  await button.click();
  await expect(button).toBeDisabled();
  await expect.poll(() => page.evaluate(() => window.hostMessages.length)).toBe(1);
  if (navigate) {
    await page.evaluate(() => { window.direct = true; });
    await page.clock.runFor(11000);
    await ui.locator('.thread-button').filter({hasText:'Alex'}).click();
  }
  await page.evaluate(() => window.releaseMessage());
  if (navigate) {
    await expect(ui.locator('#connection-list')).toBeVisible();
    await expect(ui.locator('#connection-list')).not.toContainText('Could not confirm the handoff');
    await expect(ui.locator('#message-title')).toHaveText('Alex');
  } else {
    await expect(ui.locator('.artifact [role=status]')).toContainText('Check chat before retrying');
    await expect(button).toBeDisabled();
    await page.clock.runFor(11000);
    await expect(button).toBeDisabled();
  }
  expect(await page.evaluate(() => window.hostMessages.length)).toBe(1);
});
