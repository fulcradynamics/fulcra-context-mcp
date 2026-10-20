import { test, expect } from '@playwright/test';
import { open } from './harness.js';

const writes = page => page.evaluate(() => window.calls.filter(c => c.name === 'agent_connection_send').map(c => c.arguments));
const choose = ui => ui.locator('.thread-button').filter({ hasText: 'Weekend' }).click();
const leave = async (page, ui) => {
  await page.evaluate(() => { window.navigationContact = true; });
  await page.clock.runFor(11000);
  await ui.locator('.thread-button').filter({ hasText: 'Quiet contact' }).click();
  await expect(ui.locator('#message-title')).toHaveText('Quiet contact');
  await expect(ui.locator('.composer-input')).toHaveValue('');
};

test('Send auto-acks retain uncertain writes without duplicating or overwriting newer drafts', async ({ page }) => {
  const ui = await open(page, 900, { acceptAck: true });
  await expect.poll(() => writes(page)).toHaveLength(1);
  await page.evaluate(() => {
    window.pendingAcks = [];
    window.sendResult = (request, reply) => {
      const a = request.params.arguments;
      const record = { id: a.mid, kind: a.kind, body: a.body, sender: a.sender,
        in_reply_to: a.in_reply_to, start_time: '2026-10-13T12:00:00Z' };
      if (a.kind === 'ack') window.pendingAcks.push(record);
      else window.ownRecords.push(record);
      reply(request.id, { structuredContent: { status: a.kind === 'ack' ? 'uncertain' : 'posted',
        mid: a.mid, outbox: a.outbox, peer_userid: a.peer_userid, record } });
    };
  });
  await ui.locator('.composer-input').fill('My reply');
  await ui.locator('.send-to-peer').click();
  await expect.poll(() => writes(page)).toHaveLength(6); // open ack, reply, four remaining acks
  // Uncertain read-acks surface as a transient toast, not a persistent footer line.
  await expect(ui.locator('.toast')).toContainText('Couldn’t confirm messages read');
  await ui.locator('.composer-input').fill('New draft');
  const first = await writes(page);
  expect(new Set(first.map(a => a.mid)).size).toBe(first.length); // No duplicate IDs.
  await leave(page, ui);
  await choose(ui);
  await page.clock.runFor(11000);
  expect(await writes(page)).toEqual(first); // Reopening never re-sends an ack.
  await page.evaluate(() => { window.ownRecords.push(...window.pendingAcks); });
  await page.clock.runFor(11000);
  await expect(ui.locator('.composer-input')).toHaveValue('New draft');
  await expect(ui.locator('.send-to-peer')).toBeEnabled();
  expect(await writes(page)).toEqual(first);
});

for (const outcome of ['uncertain', 'lost', 'rejected']) {
  test(`opening acknowledgement: ${outcome} retains identity without duplicate writes`, async ({ page }) => {
    const ui = await open(page, 900, { listOnly: true, autoSelect: false });
    await expect(ui.locator('#selection-empty')).toBeVisible();
    await expect(ui.locator('#messages .message-row')).toHaveCount(0);
    expect(await writes(page)).toEqual([]); // Untargeted startup performs no writes.
    await page.evaluate(outcome => {
      window.pendingAcks = [];
      window.sendResult = (request, reply) => {
        const a = request.params.arguments;
        window.pendingAcks.push({ id: a.mid, kind: 'ack', body: 'ack', sender: a.sender,
          in_reply_to: a.in_reply_to, start_time: '2026-10-13T12:00:00Z' });
        if (outcome !== 'lost') reply(request.id, { structuredContent: {
          status: outcome, mid: a.mid, outbox: a.outbox, peer_userid: a.peer_userid,
          reason: 'Private arbitrary host error',
        } });
      };
    }, outcome);
    await choose(ui);
    await expect.poll(() => writes(page)).toHaveLength(1);
    if (outcome === 'lost') await page.clock.runFor(31000);
    // The host's private reason is never surfaced anywhere in the UI.
    await expect(ui.locator('body')).not.toContainText('Private arbitrary host error');
    const first = await writes(page);
    await ui.locator('.composer-input').fill('Keep my draft');
    await leave(page, ui);
    await choose(ui);
    await expect(ui.locator('#messages .message-row')).toHaveCount(6);
    await expect(ui.locator('.composer-input')).toHaveValue('Keep my draft');
    await page.clock.runFor(11000);
    expect(await writes(page)).toEqual(first); // Reopening never re-sends the ack.
    if (outcome !== 'rejected') {
      await page.evaluate(() => { window.ownRecords.push(...window.pendingAcks); });
      await page.clock.runFor(11000);
      await expect(ui.locator('.composer-input')).toHaveValue('Keep my draft');
      await leave(page, ui);
      await choose(ui);
      await expect(ui.locator('#messages .message-row')).toHaveCount(6);
      expect(await writes(page)).toEqual(first);
    }
  });
}
