import { test, expect } from '@playwright/test';
import { open, peer, other } from './harness.js';

test('unread rows ack their own sender with the full audience; a rejected ack stays unread', async ({ page }) => {
  const ui = await open(page);
  await expect(ui.locator('#messages .message-row.unread')).toHaveCount(6);
  await expect(ui.locator('#mark-all-read')).toHaveText('Mark all 6 read');
  await ui.locator('.message-row.unread', { hasText: 'Broadcast message' }).first().getByRole('button', { name: 'Mark read' }).click();
  await expect(ui.locator('#send-status')).toHaveText('Could not mark 1 message read. Try again.');
  const ack = await page.evaluate(() => window.calls.find(c => c.name === 'mesh_send').arguments);
  expect(ack).toMatchObject({ kind: 'ack', body: 'Read.', expected_peer_userids: [peer, other] });
  expect(ack.in_reply_to).toBe(`${ack.peer_userid}-3`);
  await expect(ui.locator('#messages .message-row.unread')).toHaveCount(6);
});
