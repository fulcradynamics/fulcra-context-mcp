import { test, expect } from '@playwright/test';
import { open } from './harness.js';

test('only the user\'s own previews get a prefix, italic and in the preview color', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true });
  const preview = ui.locator('.thread-button').filter({ hasText: 'Weekend' }).locator('.thread-preview');
  // Incoming previews lead with the message text — no sender name prefix.
  await expect(preview.locator('.preview-sender')).toHaveCount(0);
  await expect(preview).toHaveText('Broadcast message');
  await expect(preview).toHaveCSS('color', 'rgb(165, 165, 173)');

  await page.evaluate(() => {
    window.ownRecords = [{ id: 'outgoing', start_time: '2026-10-13T11:59:00Z', sender: 'me', kind: 'message', body: '<b>Literal text</b>' }];
  });
  await page.clock.runFor(11000);
  const sender = preview.locator('.preview-sender');
  await expect(sender).toHaveText('You: ');
  // Same color as the preview body, just italic.
  await expect(sender).toHaveCSS('color', 'rgb(165, 165, 173)');
  await expect(sender).toHaveCSS('font-style', 'italic');
  await expect(preview).toHaveText('You: <b>Literal text</b>');
  await expect(preview.locator('b')).toHaveCount(0);

  await page.evaluate(() => { window.failReads = true; });
  await page.clock.runFor(11000);
  await expect(preview).toContainText('Preview unavailable');
  await expect(sender).toHaveCount(0);
});
