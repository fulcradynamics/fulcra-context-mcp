import { test, expect } from '@playwright/test';
import { open } from './harness.js';

for (const launch of ['global', 'thread', 'resource']) {
  test(`full-panel ${launch} preserves launch selection and drafts across host modes`, async ({ page }) => {
    const ui = await open(page, 900, {
      listOnly: true, presentation: launch === 'global' ? 'global' : 'thread',
      resourceStartup: launch === 'resource', holdLaunch: launch === 'resource',
    });
    await expect(ui.locator('#connection-detail')).toBeVisible();
    await expect(ui.locator('body')).not.toContainText('Waiting for the initial conversation result');
    await page.clock.runFor(11000);
    expect(await page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message'))).toEqual([]);
    await ui.locator('.thread-button').filter({ hasText: 'Weekend' }).click();
    await expect(ui.locator('#connection-detail')).toBeVisible();
    await ui.locator('.composer-input').fill('Preserve my draft');
    await page.evaluate(() => document.querySelector('iframe').contentWindow.postMessage({
      jsonrpc: '2.0', method: 'ui/notifications/host-context-changed',
      params: { displayMode: 'inline' },
    }, '*'));
    await expect(ui.locator('html')).toHaveAttribute('data-display-mode', 'inline');
    await expect(ui.locator('#connection-detail')).toBeVisible();
    await expect(ui.locator('.composer-input')).toHaveValue('Preserve my draft');
    await expect(ui.locator('html')).not.toHaveClass(/compact-threads/);
  });
}
