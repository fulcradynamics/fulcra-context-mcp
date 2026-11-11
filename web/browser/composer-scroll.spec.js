import { test, expect } from '@playwright/test';
import { open, readOnlyThread } from './harness.js';

for (const width of [320, 900]) test(`typing without resizing keeps the conversation still at ${width}`, async ({ page }) => {
  const ui = await open(page, width, readOnlyThread);
  await expect(ui.locator('#messages li')).toHaveCount(6);
  await page.locator('iframe').evaluate(el => el.style.height = '600px');
  await page.clock.runFor(100);
  const input = ui.locator('.composer-input');
  await input.click();
  await input.fill('Hi');
  await page.clock.runFor(100);
  const geometry = () => ui.locator('#message-area').evaluate(el => ({
    scroll: el.scrollTop,
    inputTop: el.querySelector('.composer-input').getBoundingClientRect().top,
    inputHeight: el.querySelector('.composer-input').getBoundingClientRect().height,
  }));
  const before = await geometry();
  for (const character of 'hello') {
    await input.pressSequentially(character);
    await page.clock.runFor(100);
    expect(await geometry()).toEqual(before);
  }
});
