import { test, expect } from '@playwright/test';
import { open } from './harness.js';

const names = ui => ui.locator('#connections .thread-name').allTextContents();

for (const [attention, expected] of [[false, ['Alex', 'Weekend']], [true, ['Weekend', 'Alex']]]) {
  test(`a contact needing attention sorts first (attention ${attention})`, async ({ page }) => {
    const ui = await open(page, 900, { listOnly: true, direct: true,
      status: { attention, reason: attention ? 'Waiting on you' : 'Up to date', assessed_at: '2026-10-13T11:00:00Z' } });
    await expect(ui.locator('#connections .thread-time .refresh-spinner')).toHaveCount(0);
    await expect.poll(() => names(ui)).toEqual(expected);
  });
}
