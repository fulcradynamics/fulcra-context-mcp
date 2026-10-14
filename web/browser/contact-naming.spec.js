import { test, expect } from '@playwright/test';
import { open, peer } from './harness.js';

for (const kind of ['direct', 'multiparty']) {
  test(`${kind} selected contact uses Agent Contact labels`, async ({ page }) => {
    const ui = await open(page);
    if (kind === 'direct') {
      await ui.getByRole('button', { name: 'Contacts', exact: true }).click();
      await ui.locator('.thread-button').filter({ hasText: peer }).filter({ hasNotText: 'Weekend' }).click();
      await expect(ui.locator('#messages .message-row')).toHaveCount(3);
    }
    await expect(ui.locator('#message-title')).toHaveText(kind === 'direct' ? peer : 'Weekend');
    await expect(ui.getByRole('button', {
      name: 'Discuss in synthetic', exact: true,
    })).toBeEnabled();
    const writes = await page.evaluate(() => window.calls.filter(call => call.name === 'agent_connection_send'));
    expect(writes).toHaveLength(1);
    expect(writes[0].arguments.kind).toBe('ack');
  });
}

test('contact branding uses the compiled app without changing polling writes', async ({ page }) => {
  const ui = await open(page);
  await expect(ui.locator('h1')).toHaveText('Agents I Know');
  await expect(ui.locator('#connections-title')).toHaveText('Agent Contacts');
  const names = await page.evaluate(() => window.calls.map(call => call.name));
  expect(names.every(name => !name.includes('mesh') && !name.includes('aicq'))).toBe(true);
  await page.clock.runFor(11000);
  expect(await page.evaluate(() => window.calls.filter(call => call.name === 'agent_connection_send'))).toHaveLength(1);
});
