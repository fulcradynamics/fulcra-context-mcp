import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
const html = await readFile(new URL('../fulcra_mcp/ui/hello.html', import.meta.url), 'utf8');
const own = { id: 'MomentAnnotation/00000000-0000-0000-0000-000000000001', name: 'Mesh Outbox Own' };
const peer = { id: 'MomentAnnotation/00000000-0000-0000-0000-000000000002', name: 'Mesh Outbox Peer', fulcra_userid: 'peer-user' };
async function open(page, paired = false) {
  await page.setContent('<iframe sandbox="allow-scripts"></iframe>');
  await page.evaluate(({ html, entries, paired }) => {
    window.discovery = [];
    window.shares = { own_fulcra_userid: 'me', outgoing: paired ? [{ data_types: [entries[0].id], with_user_ids: ['peer-user'], share_all_data: false }] : [], incoming: paired ? [{ data_types: [entries[1].id], sharing_fulcra_userid: 'peer-user', grant_type: 'user', share_all_data: false }] : [] };
    window.reads = [];
    window.agentRequests = [];
    const frame = document.querySelector('iframe');
    window.reply = (id, result) => frame.contentWindow.postMessage({ jsonrpc: '2.0', id, result }, '*');
    window.addEventListener('message', event => {
      if (event.source !== frame.contentWindow) return;
      const message = event.data;
      if (message.method === 'ui/message') window.agentRequests.push(message);
      if (message.method === 'ui/initialize') window.reply(message.id, { protocolVersion: '2026-01-26', hostInfo: { name: 'test', version: '1' }, hostCapabilities: { message: { text: {} } }, hostContext: { displayMode: 'fullscreen' } });
      if (message.method === 'tools/call') {
        if (['get_data_catalog', 'list_shares'].includes(message.params.name)) {
          window.discovery.push(message);
          if (window.holdDiscovery) return;
          const text = message.params.name === 'get_data_catalog'
            ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': entries })
            : 'Shares: ' + JSON.stringify(window.shares);
          window.reply(message.id, { content: [{ type: 'text', text }] });
        } else window.reads.push(message);
      }
    });
    frame.srcdoc = html;
  }, { html, entries: [own, peer], paired });
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
  await expect(ui.locator('#message-status')).toContainText('Conversation incomplete');
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

test('Tell My Agent sends only the chosen message and instruction via the real SDK', async ({ page }) => {
  const ui = await open(page);
  await ui.getByRole('button', { name: 'Mesh Outbox Peer', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(1);
  const record = { note: JSON.stringify({ v: 1, mid: 'chosen-mid', body: 'Please respond' }) };
  await respond(page, 0, [record, { note: 'unrelated other message' }]);
  const first = ui.locator('#messages > li').first();
  const input = first.getByRole('textbox', { name: 'Instructions for my agent' });
  const button = first.getByRole('button', { name: 'Tell My Agent', exact: true });
  await expect(button).toBeDisabled();
  await input.fill('Draft a response for me to review.');
  expect(await page.evaluate(() => window.agentRequests.length)).toBe(0);
  await button.click();
  await expect(button).toBeDisabled();
  await expect.poll(() => page.evaluate(() => window.agentRequests.length)).toBe(1);
  const sent = await page.evaluate(() => window.agentRequests[0].params);
  expect(sent.role).toBe('user');
  expect(sent.content[0].text).toContain('Draft a response for me to review.');
  expect(sent.content[1].text).toContain(peer.id);
  expect(sent.content[1].text).toContain('peer-user');
  expect(sent.content[1].text).toContain('chosen-mid');
  expect(sent.content[1].text).not.toContain('unrelated other message');
  expect(await page.evaluate(() => window.reads.length)).toBe(1);
  await page.evaluate(() => window.reply(window.agentRequests[0].id, { isError: true }));
  await expect(first.getByRole('status')).toContainText('Could not send');
  await expect(input).toHaveValue('Draft a response for me to review.');
  await button.click();
  await expect.poll(() => page.evaluate(() => window.agentRequests.length)).toBe(2);
  await page.evaluate(() => window.reply(window.agentRequests[1].id, {}));
  await expect(first.getByRole('status')).toContainText('Request sent');
  await expect(input).toHaveValue('');
  await expect(button).toBeDisabled();
});

for (const selection of [own, peer]) test(`two-way ${selection.name}: chronology, original incoming context, refreshed date window`, async ({ page }) => {
  const ui = await open(page, true);
  await ui.getByRole('button', { name: selection.name, exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(2);
  const incomingIndex = selection === peer ? 0 : 1;
  await respond(page, incomingIndex, [{ recorded_at: '2026-01-01T12:00:00Z', note: JSON.stringify({ v: 1, body: 'unacked reply', mid: 'incoming-id' }) }]);
  await respond(page, 1 - incomingIndex, [{ recorded_at: '2026-01-02T12:00:00Z', note: 'outgoing message' }]);
  await expect(ui.locator('#messages > li')).toHaveCount(2);
  const first = ui.locator('#messages > li').first();
  await expect(first).toContainText('Incoming');
  await expect(first).toContainText('your local time');
  await expect(ui.locator('#messages > li').last()).toContainText('Outgoing');
  await first.getByRole('textbox').fill('Explain this reply');
  await first.getByRole('button', { name: 'Tell My Agent' }).click();
  await expect.poll(() => page.evaluate(() => window.agentRequests.length)).toBe(1);
  const context = await page.evaluate(() => window.agentRequests[0].params.content[1].text);
  expect(context).toContain(peer.id);
  expect(context).toContain('peer-user');
  expect(context).not.toContain(own.id);
  expect(context).not.toContain('outgoing message');
  await ui.locator('#message-start').fill('2026-01-01');
  await ui.locator('#message-end').fill('2026-01-02');
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(4);
  const ranges = await page.evaluate(() => window.reads.slice(2).map(r => r.params.arguments));
  for (const args of ranges) {
    expect(args.start_time).toBe('2026-01-01T00:00:00.000Z');
    expect(args.end_time).toBe('2026-01-03T00:00:00.000Z');
  }
  expect(await page.evaluate(() => window.discovery.map(r => r.params.name))).toEqual(['get_data_catalog', 'get_data_catalog', 'list_shares', 'get_data_catalog', 'list_shares']);
  await respond(page, 2, []);
  await respond(page, 3, []);
  await expect(ui.locator('#message-status')).toContainText('No messages in this range');
});

test('paired partial failure retains incoming, and failed empty reads are not empty success', async ({ page }) => {
  const ui = await open(page, true);
  await ui.getByRole('button', { name: own.name, exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(2);
  await respond(page, 1, [{ note: 'incoming preserved' }], true);
  await page.evaluate(() => window.reply(window.reads[0].id, { isError: true }));
  await expect(ui.locator('#messages')).toContainText('incoming preserved');
  await expect(ui.locator('#message-status')).toContainText('Could not load messages — Outgoing');
  await expect(ui.locator('#message-status')).toContainText('Partial result — Incoming');
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(4);
  await respond(page, 2, []);
  await page.evaluate(() => window.reply(window.reads[3].id, { isError: true }));
  await expect(ui.locator('#message-status')).toContainText('0 messages shown');
  await expect(ui.locator('#message-status')).toContainText('Conversation incomplete');
  await expect(ui.locator('#message-status')).not.toContainText('No messages in this range');
  expect(await page.evaluate(() => window.agentRequests.length)).toBe(0);
});

test('both old channel reads are ignored after back and reselection', async ({ page }) => {
  const ui = await open(page, true);
  await ui.getByRole('button', { name: own.name, exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(2);
  await ui.getByRole('button', { name: 'Back to meshes' }).click();
  await ui.getByRole('button', { name: peer.name, exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(4);
  await respond(page, 2, [{ note: 'fresh peer' }]);
  await respond(page, 3, []);
  await respond(page, 0, [{ note: 'stale own' }]);
  await respond(page, 1, [{ note: 'stale peer' }]);
  await expect(ui.locator('#messages')).toContainText('fresh peer');
  await expect(ui.locator('#messages')).not.toContainText('stale');
  await expect(ui.getByRole('button', { name: 'Load messages', exact: true })).toBeEnabled();
});

test('navigation during discovery ignores late discovery and starts no stale reads', async ({ page }) => {
  const ui = await open(page);
  await expect(ui.getByRole('button', { name: own.name, exact: true })).toBeVisible();
  await page.evaluate(() => { window.holdDiscovery = true; });
  await ui.getByRole('button', { name: own.name, exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.discovery.length)).toBe(3);
  await ui.getByRole('button', { name: 'Back to meshes' }).click();
  await page.evaluate(() => {
    window.holdDiscovery = false;
    for (const r of window.discovery.slice(1)) window.reply(r.id, { isError: true });
  });
  await ui.getByRole('button', { name: peer.name, exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(1);
  expect(await page.evaluate(() => window.reads[0].params.arguments.fulcra_userid)).toBe('peer-user');
  await respond(page, 0, [{ note: 'current' }]);
  await expect(ui.locator('#messages')).toContainText('current');
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
