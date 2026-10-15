import { test, expect } from '@playwright/test';
import { open } from './harness.js';

for (const presentation of ['global', 'thread', 'threads']) {
  for (const sampling of [false, true]) {
    test(`${presentation} has no reply suggestions with sampling=${sampling}`, async ({ page }) => {
      const ui = await open(page, 900, { presentation, sampling });
      await expect(ui.locator('.composer-input')).toBeVisible();
      await expect(ui.getByRole('button', { name: 'Suggest replies' })).toHaveCount(0);
      await expect(ui.locator('#suggestion-status, #reply-suggestions')).toHaveCount(0);
      await ui.locator('.composer-input').fill('A manual reply');
      await expect(ui.getByRole('button', { name: 'Send', exact: true })).toBeEnabled();
      await ui.getByRole('button', { name: 'Discuss in synthetic', exact: true }).click();
      await expect.poll(() => page.evaluate(() => window.hostMessages.length)).toBe(1);
      await page.clock.runFor(11000);
      expect(await page.evaluate(() => window.samplingCalls ?? 0)).toBe(0);
    });
  }
}
