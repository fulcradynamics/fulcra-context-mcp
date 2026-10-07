import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
const html = await readFile(new URL('../fulcra_mcp/ui/hello.html', import.meta.url), 'utf8');
const own = { id: 'MomentAnnotation/00000000-0000-0000-0000-000000000001', name: 'Mesh Outbox Own' };
const peer = { id: 'MomentAnnotation/00000000-0000-0000-0000-000000000002', name: 'Mesh Outbox Peer', fulcra_userid: 'peer-user' };
async function open(page) {
  await page.setContent('<iframe sandbox="allow-scripts"></iframe>');
  await page.evaluate(({ html, entries }) => {
    window.reads = [];
    const frame = document.querySelector('iframe');
    window.reply = (id, result) => frame.contentWindow.postMessage({ jsonrpc: '2.0', id, result }, '*');
    window.addEventListener('message', event => {
      if (event.source !== frame.contentWindow) return;
      const message = event.data;
      if (message.method === 'ui/initialize') window.reply(message.id, { protocolVersion: '2026-01-26', hostInfo: { name: 'test', version: '1' }, hostCapabilities: { message: { text: {} } }, hostContext: { displayMode: 'fullscreen' } });
      if (message.method === 'tools/call') {
        if (message.params.name === 'get_data_catalog') window.reply(message.id, { content: [{ type: 'text', text: 'Available data types, grouped by compatible tool: ' + JSON.stringify({ records: entries }) }] });
        else window.reads.push(message);
      }
    });
    frame.srcdoc = html;
  }, { html, entries: [own, peer] });
  return page.frameLocator('iframe');
}
async function respond(page, index, rows, truncated = false) {
  await page.evaluate(({ index, rows, truncated }) => {
    const request = window.reads[index];
    window.reply(request.id, { content: [{ type: 'text', text: `Records for ${request.params.arguments.data_type} from start to end${truncated ? ' (showing the first 1 of 2; narrow the time range for the rest)' : ''}: ${JSON.stringify(rows)}` }] });
  }, { index, rows, truncated });
}

test('click reads selected peer messages, shows loading, text-safe content and bounded empty/error states', async ({ page }) => {
  const ui = await open(page);
  await ui.getByRole('button', { name: 'Mesh Outbox Peer', exact: true }).click();
  await expect(ui.locator('#message-status')).toContainText('Loading messages — calling get_records');
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(1);
  const request = await page.evaluate(() => window.reads[0].params);
  expect(request.name).toBe('get_records');
  expect(request.arguments.data_type).toBe(peer.id);
  expect(request.arguments.fulcra_userid).toBe('peer-user');
  expect(request.arguments.start_time).toMatch(/T00:00:00.000Z$/);
  await respond(page, 0, [{ recorded_at: '2026-01-02T12:00:00Z', note: JSON.stringify({ v: 1, body: '<img src=x onerror=alert(1)>hello', kind: 'directive' }) }], true);
  await expect(ui.locator('#message-status')).toContainText('Partial result');
  await expect(ui.locator('#messages')).toContainText('<img src=x onerror=alert(1)>hello');
  await expect(ui.locator('#messages img')).toHaveCount(0);
  await ui.locator('#message-start').fill('2026-01-01');
  await ui.locator('#message-end').fill('2026-01-02');
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(2);
  expect(await page.evaluate(() => window.reads[1].params.arguments.end_time)).toBe('2026-01-03T00:00:00.000Z');
  await respond(page, 1, []);
  await expect(ui.locator('#message-status')).toContainText('0 messages returned for this range');
  await expect(ui.locator('#message-status')).toContainText('2026-01-01 through 2026-01-02 UTC');
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(3);
  await page.evaluate(() => window.reply(window.reads[2].id, { isError: true, content: [] }));
  await expect(ui.locator('#message-status')).toContainText('Could not load messages');
  await expect(ui.getByRole('button', { name: 'Load messages', exact: true })).toBeEnabled();
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(4);
  await respond(page, 3, [{ note: 'retry succeeded' }]);
  await expect(ui.locator('#messages')).toContainText('retry succeeded');
  await ui.locator('#message-start').fill('2026-02-01');
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect(ui.locator('#message-status')).toContainText('Choose a valid date range');
  expect(await page.evaluate(() => window.reads.length)).toBe(4);
});

test('returning to list and choosing another outbox ignores late responses', async ({ page }) => {
  const ui = await open(page);
  await ui.getByRole('button', { name: 'Mesh Outbox Peer', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(1);
  await ui.getByRole('button', { name: 'Back to meshes' }).click();
  await ui.getByRole('button', { name: 'Mesh Outbox Own', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(2);
  expect(await page.evaluate(() => window.reads[1].params.arguments.fulcra_userid)).toBeUndefined();
  await respond(page, 1, [{ note: 'current own message' }]);
  await respond(page, 0, [{ note: 'stale peer message' }]);
  await expect(ui.locator('#messages')).toContainText('current own message');
  await expect(ui.locator('#messages')).not.toContainText('stale peer message');
  await expect(ui.locator('#messages')).toContainText('Unrecognized mesh envelope');
});
