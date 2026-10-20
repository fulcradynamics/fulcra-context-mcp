import { test, expect } from '@playwright/test';
import { open, out, peer, incoming } from './harness.js';

test('open invitation matcher completion rediscovers grants without sharing the template', async ({page}) => {
  const ui = await open(page, 900, {listOnly:true});
  await page.evaluate(() => { window.excludeOut = true; window.holdMatches = true; });
  await page.clock.runFor(11000);
  await expect(ui.locator('#connections .thread-row')).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => Boolean(window.releaseMatch))).toBe(true);

  // A claimed match alone cannot turn the unshared template into a connection.
  await page.evaluate(({out, peer, incoming}) => {
    window.invitationMatches = [{template_data_type:out, data_type:out.slice(0,-1)+'9',
      status:'matched', peer_userid:peer, incoming_data_type:incoming}];
    window.discoveryBefore = window.calls.filter(c => c.name === 'list_shares').length;
    window.releaseMatch();
  }, {out, peer, incoming});
  await expect.poll(() => page.evaluate(() => window.calls.filter(c => c.name === 'list_shares').length)).toBeGreaterThan(await page.evaluate(() => window.discoveryBefore));
  await expect(ui.locator('#connections .thread-row')).toHaveCount(0);

  // The completed binding disappears from results. Its independently discovered
  // individual outbox/grant, not that result, makes the responder connected.
  await page.evaluate(() => {
    window.direct = true;
    window.invitationMatches = [];
    window.discoveryBefore = window.calls.filter(c => c.name === 'list_shares').length;
    window.releaseMatch();
  });
  await expect.poll(() => page.evaluate(() => window.calls.filter(c => c.name === 'list_shares').length)).toBeGreaterThan(await page.evaluate(() => window.discoveryBefore));
  await expect(ui.locator('#connections .thread-row')).toHaveCount(1);
  await expect(ui.locator('#pending-connections')).toContainText('Not connected yet. Invitation sent');
  expect(await page.evaluate(() => window.excludeOut)).toBe(true);
  expect(await page.evaluate(() => window.hostMessages.length)).toBe(0);
  expect(await page.evaluate(() => window.calls.some(c => ['create_share', 'create_data_type', 'agent_connection_send'].includes(c.name)))).toBe(false);
});
