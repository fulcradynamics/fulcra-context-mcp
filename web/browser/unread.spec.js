import { test, expect } from '@playwright/test';
import { open, peer, other } from './harness.js';

test('contacts render before message reads and show latest preview read state without writes', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, holdReads: true });
  await expect.poll(() => page.evaluate(() => window.heldReads.length)).toBeGreaterThan(0);
  const row = ui.locator('.thread-row').filter({ hasText: 'Weekend' });
  await expect(row.locator('.thread-preview')).toBeHidden();
  expect(await page.evaluate(() => window.calls.some(c => c.name === 'agent_connection_send'))).toBe(false);
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  await expect(row.locator('.thread-preview')).toContainText('Broadcast message');
  await expect(row.locator('.unread-dot')).toBeVisible();
  await expect(row.locator('.thread-time')).toHaveText('58m');
  expect(await page.evaluate(() => window.calls.some(c => c.name === 'agent_connection_send'))).toBe(false);
});

test('opening acknowledges only the latest incoming message once, without detail read badges', async ({ page }) => {
  const ui = await open(page);
  await expect.poll(() => page.evaluate(() => window.calls.filter(c => c.name === 'agent_connection_send').length)).toBe(1);
  const ack = await page.evaluate(() => window.calls.find(c => c.name === 'agent_connection_send').arguments);
  expect(ack).toMatchObject({ kind: 'ack', body: 'ack', expected_peer_userids: [peer, other] });
  expect(ack.in_reply_to).toBe(`${ack.peer_userid}-3`);
  await expect(ui.locator('.unread-badge, .mark-read, #mark-all-read')).toHaveCount(0);
  await expect(ui.locator('#messages .message-row.unread')).toHaveCount(0);
  await page.clock.runFor(11000);
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'agent_connection_send').length)).toBe(1);
});

test('opening a contact whose last message is outgoing does not acknowledge an older incoming message', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, ownRecords: [{ id: 'sent', kind: 'message', sender: 'chatgpt', body: 'Latest outgoing', start_time: '2026-10-13T11:30:00Z' }] });
  const row = ui.locator('.thread-row').filter({ hasText: 'Weekend' });
  await expect(row.locator('.thread-preview')).toHaveText('You: Latest outgoing');
  await expect(row.locator('.unread-dot')).toBeHidden();
  await expect(row.locator('.thread-time')).toHaveText('30m');
  await row.locator('.thread-button').click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(7);
  expect(await page.evaluate(() => window.calls.some(c => c.name === 'agent_connection_send'))).toBe(false);
});

test('previews survive metadata-only refreshes while their reads are pending', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, holdReads: true });
  await expect.poll(() => page.evaluate(() => window.heldReads.length)).toBeGreaterThan(0);
  await page.clock.runFor(11000);
  await expect.poll(() => page.evaluate(() => window.calls.filter(c => c.name === 'get_data_catalog').length)).toBe(2);
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  await expect(ui.locator('.thread-row').filter({ hasText: 'Weekend' }).locator('.thread-preview')).toContainText('Broadcast message');
});

test('slow list previews do not hold up opening a contact', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, holdReads: true });
  await expect.poll(() => page.evaluate(() => window.heldReads.length)).toBeGreaterThan(0);
  await page.evaluate(() => { window.holdReads = false; });
  await ui.locator('.thread-button').filter({ hasText: 'Weekend' }).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  expect(await page.evaluate(() => window.heldReads.length)).toBeGreaterThan(0);
  await page.evaluate(() => window.releaseReads());
});

test('failed opening reads do not turn a later poll into an acknowledgement', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true });
  await page.evaluate(() => { window.failReads = true; });
  await ui.locator('.thread-button').filter({ hasText: 'Weekend' }).click();
  await expect(ui.locator('#message-status')).toContainText('Could not load messages');
  await page.evaluate(() => { window.failReads = false; });
  await page.clock.runFor(21000);
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  expect(await page.evaluate(() => window.calls.some(c => c.name === 'agent_connection_send'))).toBe(false);
});

test('leaving before reads finish cancels acknowledgement', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, holdReads: true });
  await ui.locator('.thread-button').filter({ hasText: 'Weekend' }).click();
  await expect(ui.locator('#connection-detail')).toBeVisible();
  await ui.locator('#message-back').click();
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  await page.clock.runFor(11000);
  expect(await page.evaluate(() => window.calls.some(c => c.name === 'agent_connection_send'))).toBe(false);
});

test('verified acknowledgement clears the list dot and is not sent again on reopening', async ({ page }) => {
  const ui = await open(page, 390, { acceptAck: true });
  await expect.poll(() => page.evaluate(() => window.calls.filter(c => c.name === 'agent_connection_send').length)).toBe(1);
  await ui.locator('#message-back').click();
  await page.clock.runFor(11000);
  const row = ui.locator('.thread-row').filter({ hasText: 'Weekend' });
  await expect(row.locator('.thread-preview')).toContainText('Broadcast message');
  await expect(row.locator('.unread-dot')).toBeHidden();
  await row.locator('.thread-button').click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'agent_connection_send').length)).toBe(1);
});

test('malformed ack bodies retain safe rows alongside valid messages', async ({ page }) => {
  const ownRecords = [123, { text: 'ack' }].map((body, i) => ({
    id: `malformed-${i}`, kind: 'ack', sender: 'chatgpt', body, start_time: '2026-10-13T11:30:00Z',
  }));
  const ui = await open(page, 900, { ownRecords, listOnly: true });
  await ui.locator('.thread-button').filter({ hasText: 'Weekend' }).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(8);
  await expect(ui.locator('#messages')).toContainText('Broadcast message');
  await expect(ui.locator('#messages')).toContainText('Unrecognized connection record.');
  await expect(ui.locator('#message-status')).toHaveText('');
});

test('preview recovers newer outgoing content behind a receipt', async ({ page }) => {
  const ownRecords = [
    { id: 'sent', kind: 'message', sender: 'chatgpt', body: 'Hidden outgoing', start_time: '2026-10-13T11:30:00Z' },
    { id: 'receipt', kind: 'ack', body: 'ack', in_reply_to: 'older', start_time: '2026-10-13T11:45:00Z' },
  ];
  const ui = await open(page, 900, { ownRecords, listOnly: true });
  const row = ui.locator('.thread-row').filter({ hasText: 'Weekend' });
  await expect(row.locator('.thread-preview')).toHaveText('You: Hidden outgoing');
  await expect(row.locator('.thread-time')).toHaveText('30m');
  await expect(row.locator('.unread-dot')).toBeHidden();
  expect(await page.evaluate(() => window.calls.some(c => c.name === 'agent_connection_send'))).toBe(false);
  await page.evaluate(() => { window.failReads = true; });
  await page.clock.runFor(11000);
  await expect(row.locator('.thread-preview')).toContainText('Preview unavailable');
  await expect(row.locator('.thread-time')).toHaveText('');
  await expect(row.locator('.unread-dot')).toBeHidden();
});

test('receipt-only acks are hidden but substantive acks remain visible', async ({ page }) => {
  const ownRecords = [undefined, '', 'ack', ' ACK ', 'ack — I need your decision', 'Read.'].map((body, i) => ({
    id: `receipt-${i}`, kind: 'ack', sender: 'chatgpt', body,
    start_time: '2026-10-13T11:30:00Z', in_reply_to: `${peer}-3`,
  }));
  const ui = await open(page, 900, { ownRecords, listOnly: true });
  await ui.locator('.thread-button').filter({ hasText: 'Weekend' }).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(8);
  await expect(ui.locator('#messages')).toContainText('ack — I need your decision');
  await expect(ui.locator('#messages')).toContainText('Read.');
});
