import { test, expect } from '@playwright/test';
import { open } from './harness.js';

for (const held of ['incoming', 'outgoing', 'history']) {
  test(`badge spinner waits for ${held} reads before publishing either side`, async ({ page }) => {
    const ownRecords = [{ id: 'sent', kind: 'message', sender: 'chatgpt', body: 'Newest content', start_time: '2026-10-13T11:30:00Z' }];
    if (held === 'history') ownRecords.push({ id: 'receipt', kind: 'ack', sender: 'chatgpt', body: 'ack', in_reply_to: 'older', start_time: '2026-10-13T11:45:00Z' });
    const ui = await open(page, 900, { listOnly: true, holdReads: held, ownRecords });
    const row = ui.locator('.thread-button').filter({ hasText: 'Weekend' });
    await expect.poll(() => page.evaluate(() => window.heldReads.length)).toBeGreaterThan(0);
    await expect.poll(() => page.evaluate(() => new Set(window.calls.filter(c => c.name === 'get_records' && c.arguments.latest)
      .map(c => JSON.stringify([c.arguments.data_type, c.arguments.fulcra_userid]))).size)).toBe(3);
    await expect(row.locator('.thread-time .refresh-spinner')).toBeVisible();
    await expect(row.locator('.thread-time')).toHaveText('');
    await expect(row.locator('.unread-dot')).toBeHidden();
    await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
    await expect(row.locator('.thread-time')).toHaveText('30m');
    await expect(row.locator('.thread-time .refresh-spinner')).toHaveCount(0);
    await expect(row.locator('.thread-preview')).toHaveText('You: Newest content');
    await expect(row.locator('.unread-dot')).toBeHidden();
    expect(await page.evaluate(() => window.calls.filter(c => c.name === 'agent_connection_send'))).toEqual([]);
  });
}
