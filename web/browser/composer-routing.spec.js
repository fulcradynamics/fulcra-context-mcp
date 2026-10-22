import { test, expect } from '@playwright/test';
import { open, out, peer, other } from './harness.js';

test('multiple authorized outboxes default to newest share and preserve explicit choice', async ({page}) => {
  const ui = await open(page, 900, {second:true});
  await ui.locator('#thread-composer textarea:not([readonly])').fill('Contact draft');
  await ui.locator('#advanced-toggle').click();
  await ui.getByText('Delivery address', {exact:true}).click();
  await expect(ui.getByLabel('Your outbox')).toHaveValue(out.slice(0,-1)+'8');
  await expect(ui.getByRole('button', {name:'Send',exact:true})).toBeEnabled();
  await ui.getByLabel('Your outbox').selectOption(out);
  await page.clock.runFor(11000);
  await expect(ui.getByLabel('Your outbox')).toHaveValue(out);
  await ui.getByRole('button', {name:'Send',exact:true}).click();
  await expect.poll(() => page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message' && c.arguments.kind !== 'ack').length)).toBe(1);
  const sent = await page.evaluate(() => window.calls.find(c => c.name === 'send_agent_contact_message' && c.arguments.kind !== 'ack').arguments);
  expect(sent.outbox).toBe(out);
  expect(sent.expected_peer_userids).toEqual([peer,other]);
});

test('typed Continue handoff preserves draft provenance without posting to the contact', async ({page}) => {
  const ui = await open(page);
  await ui.locator('#thread-composer textarea:not([readonly])').fill('Please book the room');
  await ui.getByRole('button', {name:'Continue in synthetic',exact:true}).click();
  await expect.poll(() => page.evaluate(() => window.hostMessages.length)).toBe(1);
  const text = await page.evaluate(() => window.hostMessages[0].content[0].text);
  expect(text).toContain('send-message composer');
  expect(text).toContain('draft to the selected contact');
  expect(text).toContain('not an instruction to the host');
  expect(text).toContain('does not authorize sending');
  expect(text).toContain('clarify with the user before sending');
  expect(text).toContain('Please book the room');
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message' && c.arguments.kind !== 'ack'))).toEqual([]);
});
