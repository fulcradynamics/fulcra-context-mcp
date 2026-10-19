import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { open } from './harness.js';

const source = await readFile(new URL('../message-list.js', import.meta.url), 'utf8');

test('contact history stays chronological with event-time precedence and malformed dates last', async ({ page }) => {
  const record = (id, start_time, recorded_at) => ({ id, body: id, sender: 'chatgpt', kind: 'message', start_time, recorded_at });
  const ownRecords = [
    record('invalid', 'invalid'), record('coerced', 123),
    record('event-time', '2026-10-13T13:00:00Z', '2026-10-13T10:00:00Z'),
    record('same-time', '2026-10-13T10:00:00Z'), record('missing'),
    record('latest', '2026-10-13T11:30:00Z'),
  ];
  const ui = await open(page, 900, { listOnly: true, ownRecords });
  await ui.locator('.thread-button').filter({ hasText: 'Weekend' }).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(12);
  await expect(ui.locator('#messages .outgoing .bubble-body')).toHaveText(
    ['coerced', 'event-time', 'same-time', 'latest', 'invalid', 'missing']);
  expect(await ui.locator('#message-history').evaluate(el => el.nextElementSibling.id)).toBe('messages');
});

test('oldest-first list follows new messages but preserves readers and focused drafts', async ({ page }) => {
  await page.setViewportSize({ width: 800, height: 600 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route('https://message-list.test/**', route => route.fulfill(
    route.request().url().endsWith('.js')
      ? { contentType: 'text/javascript', body: source }
      : { contentType: 'text/html', body: '<style>body{margin:0}li{height:100px}ul{margin:0;padding:0}#message-area{height:412px;overflow:auto;padding-bottom:12px;box-sizing:border-box;overflow-anchor:none}</style><div id="message-area"><ul></ul></div><textarea></textarea>' }));
  await page.goto('https://message-list.test/');
  await page.evaluate(async () => {
    const { createMessageList } = await import('/message-list.js');
    window.messages = Array.from({ length: 20 }, (_, id) => ({ source: { id: 'channel', fulcra_userid: 'owner' }, record: { id } }));
    window.list = createMessageList(document.querySelector('ul'), (row, message) => { row.textContent = message.record.id; });
    window.render = () => window.list.update(window.messages, () => {});
    window.add = id => window.messages.push({ ...window.messages[0], record: { id } });
    window.render();
  });
  const bottom = () => page.locator('li').last().evaluate(el => el.getBoundingClientRect().bottom);
  expect(await bottom()).toBe(400);
  await page.evaluate(() => { window.add(20); window.render(); });
  expect(await bottom()).toBe(400);

  // Prepending history while reading in the middle retains the same row/offset.
  await page.evaluate(() => document.querySelector('#message-area').scrollTop = 500);
  const anchor = page.locator('li').filter({ hasText: /^5$/ });
  const before = await anchor.evaluate(el => el.getBoundingClientRect().top);
  await page.evaluate(() => { window.messages.unshift({ ...window.messages[0], record: { id: -1 } }); window.render(); });
  expect(await anchor.evaluate(el => el.getBoundingClientRect().top)).toBe(before);
  await page.evaluate(() => { window.add(21); window.render(); });
  expect(await anchor.evaluate(el => el.getBoundingClientRect().top)).toBe(before);

  // Even at the newest edge, a focused draft suppresses automatic following.
  const scroll = await page.evaluate(() => {
    document.querySelector('#message-area').scrollTop += document.querySelector('li:last-child').getBoundingClientRect().bottom - 400;
    document.querySelector('textarea').focus({ preventScroll: true });
    return document.querySelector('#message-area').scrollTop;
  });
  await page.evaluate(() => { window.add(22); window.render(); });
  expect(await page.evaluate(() => document.querySelector('#message-area').scrollTop)).toBe(scroll);
  await expect(page.locator('textarea')).toBeFocused();
});
