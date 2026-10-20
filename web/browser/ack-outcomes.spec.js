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
  await expect(ui.locator('#ack-status')).toHaveText('');
};

test('Send auto-acks retain uncertain writes without overwriting send status or newer drafts', async ({ page }) => {
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
  await expect(ui.locator('#send-status')).toContainText('Posted to your outbox');
  await expect(ui.locator('#ack-status')).toContainText('unconfirmed');
  await ui.locator('.composer-input').fill('New draft');
  const first = await writes(page);
  expect(new Set(first.map(a => a.mid)).size).toBe(first.length);
  await leave(page, ui);
  await choose(ui);
  await expect(ui.locator('#ack-status')).toContainText('unconfirmed');
  await page.clock.runFor(11000);
  expect(await writes(page)).toEqual(first);
  await page.evaluate(() => { window.ownRecords.push(...window.pendingAcks); });
  await page.clock.runFor(11000);
  await expect(ui.locator('#ack-status')).toHaveText('');
  await expect(ui.locator('.composer-input')).toHaveValue('New draft');
  await expect(ui.locator('.send-to-peer')).toBeEnabled();
  expect(await writes(page)).toEqual(first);
});

for (const outcome of ['uncertain', 'lost', 'rejected']) {
  test(`opening acknowledgement: ${outcome} retains identity without duplicate writes`, async ({ page }) => {
    const ui = await open(page, 900, { listOnly: true });
    await expect(ui.locator('#messages .message-row')).toHaveCount(6);
    expect(await writes(page)).toEqual([]); // Startup selection is read-only.
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
    const status = ui.locator('#ack-status');
    await expect(ui.locator('#connection-detail')).toContainText(outcome === 'rejected' ? 'rejected' : 'unconfirmed');
    await expect(ui.locator('#connection-detail')).not.toContainText('Private arbitrary host error');
    await expect(ui.locator('#send-status')).not.toContainText('Reopen');
    const first = await writes(page);
    await ui.locator('.composer-input').fill('Keep my draft');
    await leave(page, ui);
    await choose(ui);
    await expect(ui.locator('#messages .message-row')).toHaveCount(6);
    await expect(status).toContainText(outcome === 'rejected' ? 'rejected' : 'unconfirmed');
    await expect(ui.locator('.composer-input')).toHaveValue('Keep my draft');
    await page.clock.runFor(11000);
    expect(await writes(page)).toEqual(first);
    if (outcome !== 'rejected') {
      await page.evaluate(() => { window.ownRecords.push(...window.pendingAcks); });
      await page.clock.runFor(11000);
      await expect(status).toHaveText('');
      await expect(ui.locator('.composer-input')).toHaveValue('Keep my draft');
      await leave(page, ui);
      await choose(ui);
      await expect(ui.locator('#messages .message-row')).toHaveCount(6);
      await expect(status).toHaveText('');
      expect(await writes(page)).toEqual(first);
    }
  });
}
