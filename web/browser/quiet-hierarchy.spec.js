import { test, expect } from '@playwright/test';
import { open } from './harness.js';

test('quiet contact hierarchy keeps assessment in Advanced and name beside info', async ({page}) => {
  const ui = await open(page,390,{listOnly:true});
  await expect(ui.locator('#message-title')).toHaveText('Weekend');
  await expect(ui.locator('.relationship-state')).toBeHidden();
  await expect(ui.locator('#contact-assessment')).toBeHidden();
  const name = await ui.locator('#message-title').boundingBox();
  const info = await ui.locator('.identity-info').boundingBox();
  expect(Math.abs(name.y + name.height/2 - info.y - info.height/2)).toBeLessThan(2);
  expect(await ui.locator('.contact-header').evaluate(el => getComputedStyle(el).backgroundColor)).toBe('rgba(0, 0, 0, 0)');
  await ui.locator('#advanced-toggle').click();
  await expect(ui.locator('#contact-assessment')).toContainText('Not assessed');
});
