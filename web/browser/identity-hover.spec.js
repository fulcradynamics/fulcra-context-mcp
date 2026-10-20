import { test, expect } from '@playwright/test';
import { open } from './harness.js';

test.use({hasTouch:true});

test('touch can open and dismiss identity without hover', async ({page}) => {
  const ui = await open(page,390);
  const info = ui.locator('.identity-info');
  await info.tap();
  await expect(ui.locator('#contact-identity')).toBeVisible();
  await expect(ui.locator('#contact-identity input').first()).toBeFocused();
  await ui.locator('#message-title').tap();
  await expect(ui.locator('#contact-identity')).toBeHidden();
});

test('identity disclosure bridges hover, focus, and click without stealing focus', async ({page}) => {
  const ui = await open(page);
  const info = ui.getByRole('button', {name:'Contact information',exact:true});
  const panel = ui.getByRole('dialog', {name:'Fulcra User ID'});
  await info.hover();
  await expect(panel).toBeVisible();
  await expect(panel.locator('input').first()).not.toBeFocused();
  await panel.locator('input').first().hover();
  await page.clock.runFor(500);
  await expect(panel).toBeVisible();
  await panel.getByRole('button',{name:'Copy ID'}).first().click();
  await expect(panel).toContainText('Select and copy');
  await page.keyboard.press('Escape');
  await expect(panel).toBeHidden();
  await expect(info).toBeFocused();
  await ui.locator('#message-title').click();
  await info.focus();
  await expect(panel).toBeVisible();
  await page.keyboard.press('Escape');
  await info.dispatchEvent('click');
  await expect(panel).toBeVisible();
  await ui.locator('#message-title').click();
  await expect(panel).toBeHidden();
});
