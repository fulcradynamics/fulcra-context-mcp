import { test, expect } from '@playwright/test';
import { open, peer } from './harness.js';

for (const kind of ['direct', 'multiparty']) {
  test(`${kind} selected contact uses Agent Contact labels`, async ({ page }) => {
    const ui = await open(page);
    if (kind === 'direct') {
      await page.evaluate(() => { window.direct = true; });
      await page.clock.runFor(11000);
      await ui.locator('.thread-button').filter({ hasText: 'Alex' }).click();
      await expect(ui.locator('#messages .message-row')).toHaveCount(3);
    }
    await expect(ui.locator('#message-title')).toHaveText(kind === 'direct' ? 'Alex' : 'Weekend');
    await expect(ui.getByRole('button', {
      name: 'Continue in synthetic', exact: true,
    })).toBeEnabled();
    const writes = await page.evaluate(() => window.calls.filter(call => call.name === 'send_agent_contact_message'));
    expect(writes).toHaveLength(kind === 'direct' ? 2 : 1);
    expect(writes.every(write => write.arguments.kind === 'ack')).toBe(true);
  });
}

test('contact branding uses the compiled app without changing polling writes', async ({ page }) => {
  const ui = await open(page);
  await expect(ui.locator('h1')).toHaveText('Agents I Know');
  await expect(ui.locator('#connections-title')).toHaveText('Agent Chats');
  const names = await page.evaluate(() => window.calls.map(call => call.name));
  expect(names.every(name => !name.includes('mesh') && !name.includes('aicq'))).toBe(true);
  await page.clock.runFor(11000);
  expect(await page.evaluate(() => window.calls.filter(call => call.name === 'send_agent_contact_message'))).toHaveLength(1);
});
