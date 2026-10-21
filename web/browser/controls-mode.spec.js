import { test, expect } from '@playwright/test';
import { open } from './harness.js';

for (const controls of ['full', 'chat', 'none']) {
  test(`${controls} preserves reading and debug gating`, async ({ page }) => {
    const ui = await open(page, 900, { controls, debug: false, checkStatus: { status: 'not_set_up' } });
    await expect(ui.locator('#messages .message-row')).toHaveCount(6);
    if (controls !== 'none') {
      await expect.poll(() => page.evaluate(() => window.contexts.at(-1)?.content?.[0]?.text ?? '')).toContain('Broadcast message');
    }
    await expect(ui.locator('#thread-composer')).toBeVisible({ visible: controls !== 'none' });
    await expect(ui.getByRole('button', { name: 'Invite someone’s agent', exact: true })).toHaveCount(controls === 'full' ? 1 : 0);
    await expect(ui.getByRole('button', { name: 'Copy open invitation', exact: true })).toHaveCount(controls === 'full' ? 1 : 0);
    await ui.getByRole('button', { name: 'Advanced', exact: true }).click();
    await expect(ui.getByText('Debug', { exact: true })).toHaveCount(0);
    if (controls === 'none') {
      await expect(ui.locator('.chat-instruction')).toHaveCount(0);
      await expect(ui.getByRole('button', { name: /^(End contact|Set up automatic checking|Send|Continue in)/ })).toHaveCount(0);
    }
    expect(await page.evaluate(() => window.hostMessages)).toEqual([]);
    if (controls !== 'none') {
      expect(await page.evaluate(() => window.calls.some(c => c.name === 'agent_connection_send' && c.arguments.kind === 'ack'))).toBe(true);
    }
  });
}
