import { test, expect } from '@playwright/test';
import { open, out, peer, other } from './harness.js';

for (const width of [390, 1100]) test(`pending incoming and unshared channels have explicit bounded assistance at ${width}`, async ({page}) => {
  const ui = await open(page, width, {listOnly: true});
  await page.evaluate(() => { window.excludeOut = true; });
  await page.clock.runFor(11000);
  await expect(ui.locator('#connections .thread-row')).toHaveCount(0);
  await expect(ui.locator('#pending-connections > li')).toHaveCount(3);
  await expect(ui.locator('#pending-connections')).toContainText('Not connected yet. Invitation sent');
  await expect(ui.locator('#pending-connections')).toContainText('Incoming — awaiting connection');
  expect(await page.evaluate(() => window.hostMessages.length)).toBe(0);
  expect(await page.evaluate(() => window.calls.some(c => ['create_share', 'agent_connection_send'].includes(c.name)))).toBe(false);
  await page.screenshot({path:`${process.env.TMPDIR ?? '../test-results'}/invitation-pending-${width}.png`,fullPage:true});
  await ui.locator('.pending-assist').last().click();
  await expect.poll(() => page.evaluate(() => window.hostMessages.length)).toBe(1);
  const sent = await page.evaluate(() => ({messages:window.hostMessages,contexts:window.contexts}));
  expect(JSON.stringify(sent.messages)).toContain('explicit consent');
  expect(JSON.stringify(sent.contexts)).toContain('pending_source');
  expect(JSON.stringify(sent.contexts)).not.toContain('Broadcast message');
  await expect(ui.locator('.pending-assist').last()).toBeDisabled();
});

for (const outgoing of [false, true]) test(`incoming assistance remains available with outgoing shares: ${outgoing}`, async ({page}) => {
  const ui = await open(page, 900, {listOnly:true});
  await page.evaluate(({outgoing, peer}) => {
    window.excludeOwn = !outgoing;
    window.excludeOut = !outgoing;
    window.audience = [peer];
  }, {outgoing, peer});
  await page.clock.runFor(11000);
  await expect(ui.locator('#pending-connections > li')).toHaveCount(outgoing ? 1 : 2);
  const button = ui.locator('.pending-assist').last();
  await expect(button).toBeVisible();
  await expect(button).toBeEnabled();
  await button.click();
  await expect.poll(() => page.evaluate(() => window.hostMessages.length)).toBe(1);
  const context = await page.evaluate(() => JSON.stringify(window.contexts));
  expect(context).toContain(other);
  expect(context).toContain('Incoming');
  expect(await page.evaluate(() => window.calls.some(c => ['create_share', 'agent_connection_send'].includes(c.name)))).toBe(false);
});

test('outgoing-only stays pending, matched result still needs independently discovered two-way grants', async ({page}) => {
  const ui = await open(page, 900, {listOnly:true, presentation:'threads'});
  await page.evaluate(out => { window.excludeIncoming = true; window.invitationMatches = [{data_type:out,status:'matched'}]; }, out);
  await page.clock.runFor(11000);
  await expect(ui.locator('#connections .thread-row')).toHaveCount(0);
  await expect(ui.locator('#pending-connections')).toContainText('Outgoing — awaiting connection');
  await page.evaluate(() => { window.excludeIncoming = false; });
  await page.clock.runFor(21000);
  await expect(ui.locator('#connections .thread-row')).toHaveCount(1);
  await expect(ui.locator('#pending-connections > li')).toHaveCount(0);
  expect(await page.evaluate(() => window.hostMessages.length)).toBe(0);
});

test('unverified invitation remains pending across metadata polls and failed discovery', async ({page}) => {
  const ui = await open(page, 900, {listOnly:true});
  await page.evaluate(out => { window.excludeOut = true; window.invitationMatches = [{data_type:out,status:'pending'}]; }, out);
  await page.clock.runFor(11000);
  await expect(ui.locator('#connections .thread-row')).toHaveCount(0);
  await expect(ui.locator('#pending-connections > li')).toHaveCount(3);
  await page.evaluate(() => { window.failDiscovery = true; });
  await page.clock.runFor(11000);
  await expect(ui.locator('#pending-connections > li')).toHaveCount(3);
  expect(await page.evaluate(() => window.hostMessages.length)).toBe(0);
});

test('uncertain pending handoff locks the exact source without automatic retry', async ({page}) => {
  const ui = await open(page, 900, {listOnly:true});
  await page.evaluate(() => { window.excludeOut = true; window.rejectMessages = true; });
  await page.clock.runFor(11000);
  await ui.locator('.pending-assist').last().click();
  await expect(ui.locator('#connection-status')).toContainText('Could not confirm chat handoff');
  await expect(ui.locator('.pending-assist').last()).toBeDisabled();
  await page.clock.runFor(11000);
  expect(await page.evaluate(() => window.hostMessages.length)).toBe(1);
});

test('invitation completion does not veto later reciprocal multiparty grants', async ({page}) => {
  const ui = await open(page, 900, {listOnly:true, presentation:'threads'});
  await page.evaluate(({out, peer}) => {
    window.audience = [peer];
    window.invitationMatches = [{data_type:out,status:'matched'}];
  }, {out, peer});
  await page.clock.runFor(11000);
  await expect(ui.locator('#connections .thread-row')).toHaveCount(1);
  await page.evaluate(({peer, other}) => { window.audience = [peer, other]; }, {peer, other});
  for (const status of ['matched', 'pending', null]) {
    await page.evaluate(({out, status}) => { window.invitationMatches = status ? [{data_type:out,status}] : []; }, {out, status});
    await page.clock.runFor(21000);
    await expect(ui.locator('#connections .thread-row')).toHaveCount(1);
    await expect(ui.locator('#pending-connections > li')).toHaveCount(0);
  }
  expect(await page.evaluate(() => window.hostMessages.length)).toBe(0);
});

test('unsupported chat hosts retain pending contacts without automatic messages', async ({page}) => {
  const ui = await open(page, 390, {listOnly:true, chat:false});
  await page.evaluate(() => { window.excludeOut = true; });
  await page.clock.runFor(11000);
  await expect(ui.locator('.pending-assist').first()).toBeDisabled();
  await expect(ui.locator('#pending-connections')).toContainText('Chat assistance is unavailable here');
  expect(await page.evaluate(() => window.hostMessages.length)).toBe(0);
});

test('slow matching does not stall discovery, opening or draft-preserving refresh', async ({page}) => {
  const ui = await open(page, 900, {listOnly:true});
  await page.evaluate(() => { window.holdMatches = true; });
  await page.clock.runFor(11000);
  await expect.poll(() => page.evaluate(() => Boolean(window.releaseMatch))).toBe(true);
  await ui.locator('.thread-button').filter({hasText:'Weekend'}).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await ui.locator('#thread-composer textarea:not([readonly])').fill('Keep this draft');
  await page.clock.runFor(11000);
  await expect(ui.locator('#thread-composer textarea:not([readonly])')).toHaveValue('Keep this draft');
  await page.evaluate(() => { window.holdMatches = false; window.releaseMatch(); });
  await expect(ui.locator('#thread-composer textarea:not([readonly])')).toHaveValue('Keep this draft');
  expect(await page.evaluate(() => window.hostMessages.length)).toBe(0);
});
