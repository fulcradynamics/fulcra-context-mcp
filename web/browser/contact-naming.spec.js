import { test, expect } from '@playwright/test';
import { open } from './harness.js';

test('contact branding uses the compiled app without changing polling writes', async ({ page }) => {
  const ui = await open(page);
  await expect(ui.locator('h1')).toHaveText('Agents I Know');
  await expect(ui.locator('#connections-title')).toHaveText('Agent Contacts');
  const names = await page.evaluate(() => window.calls.map(call => call.name));
  expect(names.every(name => !name.includes('mesh') && !name.includes('aicq'))).toBe(true);
  expect(names).not.toContain('agent_connection_send');
});
