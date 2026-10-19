import { test, expect } from '@playwright/test';
import { open } from './harness.js';

async function debug(ui) {
  await ui.locator('#advanced-toggle').click();
  await ui.locator('#debug-preview summary').click();
}

test('debug contact states are display-only, survive polling, and reset to latest live data', async ({ page }) => {
  const ui = await open(page);
  await debug(ui);
  const before = await page.evaluate(() => ({ calls: calls.length, contexts: contexts.length, messages: hostMessages.length }));
  await ui.getByLabel('Unread state', { exact: true }).selectOption('read');
  await ui.getByLabel('Contact status', { exact: true }).selectOption('attention');
  await ui.getByLabel('Status reason', { exact: true }).fill('<Preview reason>');
  await ui.getByLabel('Relationship', { exact: true }).selectOption('pending');
  const row = ui.locator('.thread-button').filter({ hasText: 'Weekend' });
  await expect(row.locator('.unread-dot')).not.toHaveClass(/on/);
  await expect(row.locator('.status-reason')).toHaveText('<Preview reason>');
  await expect(row.locator('.relationship-state')).toHaveText('Pending');
  await expect(ui.locator('#debug-preview-active')).toBeVisible();
  expect(await page.evaluate(() => ({ calls: calls.length, contexts: contexts.length, messages: hostMessages.length }))).toEqual(before);
  await page.evaluate(() => { window.emptyRecords = true; });
  await page.clock.runFor(11000);
  await expect(row.locator('.status-reason')).toHaveText('<Preview reason>');
  await expect(row.locator('.relationship-state')).toHaveText('Pending');
  await ui.getByRole('button', { name: 'Reset to live', exact: true }).click();
  await expect(row.locator('.relationship-state')).toHaveText('Connected');
  await expect(row.locator('.status-badge')).toBeHidden();
  await expect(row.locator('.thread-preview')).toBeHidden();
  await expect(row.locator('.thread-time .refresh-spinner')).toHaveCount(0);
  await expect(ui.locator('#debug-preview-active')).toBeHidden();
});

test('message, loading and acknowledgement previews never enter sends or host context', async ({ page }) => {
  const ui = await open(page);
  await debug(ui);
  const before = await page.evaluate(() => calls.length);
  await ui.getByLabel('Messages', { exact: true }).selectOption('outgoing');
  await ui.getByLabel('Message body', { exact: true }).fill('PREVIEW ONLY <script>');
  await ui.getByLabel('Message delivery', { exact: true }).selectOption('uncertain');
  await ui.getByLabel('Acknowledgement', { exact: true }).selectOption('rejected');
  await expect(ui.locator('#messages .bubble-body')).toHaveText('PREVIEW ONLY <script>');
  await expect(ui.locator('#messages .send-badge')).toHaveText('unconfirmed');
  await expect(ui.locator('#debug-ack-status')).toContainText('Could not mark');
  expect(await page.evaluate(() => calls.length)).toBe(before);
  await ui.getByLabel('Messages', { exact: true }).selectOption('loading');
  await expect(ui.locator('#message-loading')).toBeVisible();
  await expect(ui.locator('#messages')).toBeHidden();
  await page.clock.runFor(11000);
  await expect(ui.locator('#message-loading')).toBeVisible();
  await ui.getByLabel('Messages', { exact: true }).selectOption('empty');
  await expect(ui.locator('#messages .message-row')).toHaveCount(0);
  await expect(ui.locator('#message-status')).toContainText('No messages');
  await ui.getByLabel('Messages', { exact: true }).selectOption('outgoing');
  await expect(ui.locator('#messages .bubble-body')).toHaveText('PREVIEW ONLY <script>');
  await ui.getByRole('button', { name: 'Discuss in synthetic', exact: true }).click();
  await expect.poll(() => page.evaluate(() => contexts.length)).toBeGreaterThan(0);
  const attached = await page.evaluate(() => JSON.stringify(contexts));
  expect(attached).toContain('Broadcast message');
  expect(attached).not.toContain('PREVIEW ONLY');
  await ui.getByRole('button', { name: 'OK', exact: true }).click();
  await ui.locator('.composer-input').fill('Real reply');
  await ui.getByRole('button', { name: 'Send', exact: true }).click();
  await expect.poll(() => page.evaluate(() => calls.filter(c => c.name === 'agent_connection_send' && c.arguments.body === 'Real reply').length)).toBe(1);
  const sent = await page.evaluate(() => calls.find(c => c.name === 'agent_connection_send' && c.arguments.body === 'Real reply').arguments);
  expect(sent.kind).toBe('reply');
  expect(sent.in_reply_to).not.toContain('debug');
  await expect(ui.locator('#messages .bubble-body')).toHaveText('PREVIEW ONLY <script>');
  expect(await page.evaluate(() => JSON.stringify({ calls, contexts, hostMessages }))).not.toContain('PREVIEW ONLY');
  await ui.getByRole('button', { name: 'Reset to live', exact: true }).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await expect(ui.locator('#message-loading')).toBeHidden();
  await expect(ui.locator('#debug-ack-status')).toBeHidden();
});

test('forced loading remains visible while live poll reads are held', async ({ page }) => {
  const ui = await open(page);
  await debug(ui);
  await ui.getByLabel('Messages', { exact: true }).selectOption('loading');
  await expect(ui.locator('#message-loading')).toBeVisible();
  await page.evaluate(() => { window.holdReads = true; });
  await page.clock.runFor(11000);
  await expect.poll(() => page.evaluate(() => heldReads.length)).toBeGreaterThan(0);
  await expect(ui.locator('#message-loading')).toBeVisible();
  await expect(ui.locator('#messages')).toBeHidden();
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  await expect(ui.locator('#message-loading')).toBeVisible();
  await ui.getByRole('button', { name: 'Reset to live', exact: true }).click();
  await expect(ui.locator('#message-loading')).toBeHidden();
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
});

test('debug changes and reset retain the latest topic from receipt-only acknowledgements', async ({ page }) => {
  const ui = await open(page, 900, { ownRecords: [{
    id: 'live-receipt', kind: 'ack', body: 'ack', sender: 'chatgpt',
    topic: 'Live ack topic', start_time: '2026-10-13T11:03:00Z',
  }] });
  await expect(ui.locator('#contact-topic')).toHaveText('Live ack topic');
  await debug(ui);
  await ui.getByLabel('Acknowledgement', { exact: true }).selectOption('posted');
  await expect(ui.locator('#contact-topic')).toHaveText('Live ack topic');
  await ui.getByLabel('Topic', { exact: true }).fill('Preview topic');
  await page.evaluate(() => { window.ownRecords[0].topic = 'Latest ack topic'; });
  await page.clock.runFor(11000);
  await expect(ui.locator('#contact-topic')).toHaveText('Preview topic');
  await ui.getByRole('button', { name: 'Reset to live', exact: true }).click();
  await expect(ui.locator('#contact-topic')).toHaveText('Latest ack topic');
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
});

test('list loading and text previews stay scoped across contact navigation', async ({ page }) => {
  const ui = await open(page);
  await debug(ui);
  await ui.getByLabel('List preview', { exact: true }).selectOption('loading');
  const row = ui.locator('.thread-button').filter({ hasText: 'Weekend' });
  await expect(row.locator('.thread-time .refresh-spinner')).toBeVisible();
  await page.clock.runFor(11000);
  await expect(row.locator('.thread-time .refresh-spinner')).toBeVisible();
  await ui.getByLabel('List preview', { exact: true }).selectOption('error');
  await expect(row.locator('.thread-preview')).toContainText('Preview unavailable');
  await ui.getByLabel('List preview', { exact: true }).selectOption('');
  await ui.getByLabel('Preview text', { exact: true }).fill('Custom preview');
  await ui.getByLabel('Preview time', { exact: true }).fill('2d');
  await ui.getByLabel('Topic', { exact: true }).fill('Preview topic');
  await expect(row.locator('.thread-preview')).toHaveText('Custom preview');
  await ui.getByLabel('Messages', { exact: true }).selectOption('incoming');
  await expect(row.locator('.thread-time')).toHaveText('2d');
  await expect(ui.locator('#contact-topic')).toHaveText('Preview topic');
  await page.evaluate(() => { window.direct = true; });
  await page.clock.runFor(11000);
  const second = ui.locator('#connections .thread-button').filter({ hasNotText: 'Weekend' });
  await expect(second).toBeVisible();
  await second.click();
  await expect(ui.locator('#debug-preview-active')).toBeHidden();
  await expect(ui.locator('#contact-topic')).not.toHaveText('Preview topic');
  await expect(ui.locator('#messages')).not.toContainText('Preview message');
  await row.click();
  await expect(ui.locator('#debug-preview-active')).toBeVisible();
  await expect(ui.locator('#contact-topic')).toHaveText('Preview topic');
  await expect(ui.locator('#messages .bubble-body')).toHaveText('Preview message');
  await second.click();
  await row.click();
  await expect(ui.locator('#messages .bubble-body')).toHaveText('Preview message');
  await expect(ui.locator('.composer-input')).toBeEnabled();
  const acknowledgements = await page.evaluate(() => calls.filter(c => c.name === 'agent_connection_send' && c.arguments.kind === 'ack'));
  expect(acknowledgements.length).toBeGreaterThan(0);
  for (const call of acknowledgements) expect(call.arguments.in_reply_to).not.toContain('debug');
});

test('previews cannot restore revoked permissions and remain usable at narrow widths', async ({ page }) => {
  const ui = await open(page, 390);
  await debug(ui);
  await ui.getByLabel('Messages', { exact: true }).selectOption('incoming');
  await ui.getByLabel('Relationship', { exact: true }).selectOption('connected');
  await ui.getByLabel('Unread state', { exact: true }).selectOption('unread');
  await ui.locator('.composer-input').fill('Must not send');
  await page.evaluate(() => { window.excludeOut = true; });
  await page.clock.runFor(11000);
  await expect(ui.getByRole('button', { name: 'Send', exact: true })).toBeDisabled();
  await expect(ui.locator('#message-status')).toContainText('no longer available');
  await expect(ui.locator('#messages .bubble-body')).toHaveText('Preview message');
  const before = await page.evaluate(() => calls.length);
  await ui.getByRole('button', { name: 'Reset to live', exact: true }).click();
  expect(await page.evaluate(() => calls.length)).toBe(before);
  await expect(ui.locator('#messages .message-row')).toHaveCount(0);
  await expect(ui.getByRole('button', { name: 'Send', exact: true })).toBeDisabled();
  expect(await ui.locator('.debug-fields').evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
});
