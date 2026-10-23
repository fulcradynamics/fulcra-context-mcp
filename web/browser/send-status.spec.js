import { test, expect } from '@playwright/test';
import { open } from './harness.js';

for (const outcome of ['posted', 'rejected', 'uncertain']) {
  test(`contact status follows confirmed server metadata after ${outcome} send`, async ({page}) => {
    const ui = await open(page, 900, {acceptAck:true, status:{attention:true,reason:'Decision needed',assessed_at:'2026-10-13T12:00:00Z'}});
    const badge = ui.locator('.thread-button').filter({hasText:'Weekend'}).locator('.status-badge');
    // Successful opening ack is not a message send and must retain the status.
    await expect(badge).toContainText('Decision needed');
    await page.evaluate(outcome => {
      window.sendResult = (request, reply) => {
        const a = request.params.arguments;
        const record = {id:a.mid,sender:a.sender,kind:a.kind ?? 'message',body:a.body,start_time:'2026-10-13T12:00:00Z',...(a.in_reply_to ? {in_reply_to:a.in_reply_to} : {})};
        if (outcome === 'posted') {
          window.ownRecords.push(record);
          if (a.kind !== 'ack') window.contactStatus = null;
        }
        reply(request.id, {structuredContent:{status:outcome,mid:a.mid,outbox:a.outbox,peer_userid:a.peer_userid,record}});
      };
    }, outcome);
    await ui.locator('#thread-composer textarea:not([readonly])').fill('Here is my reply');
    await ui.getByRole('button', {name:'Send',exact:true}).click();
    await page.clock.runFor(11000);
    if (outcome === 'posted') await expect(badge).toBeHidden();
    else await expect(badge).toContainText('Decision needed');
  });
}
