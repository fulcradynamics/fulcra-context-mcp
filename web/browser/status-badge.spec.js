import { test, expect } from '@playwright/test';
import { open } from './harness.js';

for (const [attention, reason] of [[true, 'Waiting on you'], [false, 'Up to date']]) {
  test(`list shows the saved assessment under the preview (attention ${attention})`, async ({ page }) => {
    const ui = await open(page, 900, { listOnly: true, status: { attention, reason, assessed_at: '2026-10-13T11:00:00Z' } });
    const row = ui.locator('.thread-button').filter({ hasText: 'Weekend' });
    const badge = row.locator('.status-badge');
    await expect(badge).toBeVisible();
    await expect(badge.locator('.status-kind')).toHaveText('Status');
    await expect(badge.locator('.status-reason')).toHaveText(reason);
    await expect(badge).toHaveClass(attention ? /attention/ : /^status-badge$/);
    const order = await row.locator('.thread-text > *').evaluateAll(els => els.map(e => e.className));
    expect(order.indexOf('thread-preview')).toBeLessThan(order.findIndex(c => c.startsWith('status-badge')));
  });
}

test('list hides the status pill when no assessment was saved', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true });
  await expect(ui.locator('.thread-button').filter({ hasText: 'Weekend' }).locator('.status-badge')).toHaveCount(0);
});
