import { test, expect } from '@playwright/test';
import { open } from './harness.js';

test('preview sender follows incoming and outgoing messages without coloring the body', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true });
  const preview = ui.locator('.thread-button').filter({ hasText: 'Weekend' }).locator('.thread-preview');
  const sender = preview.locator('.preview-sender');
  await expect(sender).toHaveText('Weekend: ');
  await expect(sender).toHaveCSS('color', 'rgb(86, 214, 183)');
  await expect(preview).toHaveText('Weekend: Broadcast message');
  await expect(preview).toHaveCSS('color', 'rgb(122, 122, 130)');

  await page.evaluate(() => {
    window.ownRecords = [{ id: 'outgoing', start_time: '2026-10-13T11:59:00Z', sender: 'me', kind: 'message', body: '<b>Literal text</b>' }];
  });
  await page.clock.runFor(11000);
  await expect(sender).toHaveText('You: ');
  await expect(sender).toHaveCSS('color', 'rgb(156, 136, 255)');
  await expect(preview).toHaveText('You: <b>Literal text</b>');
  await expect(preview.locator('b')).toHaveCount(0);

  await page.evaluate(() => { window.failReads = true; });
  await page.clock.runFor(11000);
  await expect(preview).toContainText('Preview unavailable');
  await expect(sender).toHaveCount(0);
});
