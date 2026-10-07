import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
const html = await readFile(new URL('../fulcra_mcp/ui/hello.html', import.meta.url), 'utf8');
const own = { id: 'MomentAnnotation/00000000-0000-0000-0000-000000000001', name: 'Mesh Outbox Same' };
const peer = { id: 'MomentAnnotation/00000000-0000-0000-0000-000000000002', name: 'Mesh Outbox Same', fulcra_userid: 'peer-user' };
const second = { ...own, id: 'MomentAnnotation/00000000-0000-0000-0000-000000000003' };
const other = { ...peer, fulcra_userid: 'other-user' };
async function open(page, { paired = true, multiple = false, outgoingOnly = false, supported = true } = {}) {
  await page.setContent('<iframe sandbox="allow-scripts"></iframe>');
  await page.evaluate(({ html, own, peer, second, other, paired, multiple, outgoingOnly, supported }) => {
    const grant = id => ({ data_types: [id], with_user_ids: ['peer-user'], share_all_data: false });
    window.entries = [own, ...(outgoingOnly ? [] : [peer, peer]), other, ...(multiple ? [second] : [])];
    window.discovery = [];
    window.shares = { own_fulcra_userid: 'me', outgoing: paired ? [grant(own.id), grant(own.id), ...(multiple ? [grant(second.id)] : [])] : [], incoming: [] };
    window.reads = [];
    window.agentRequests = [];
    const frame = document.querySelector('iframe');
    window.reply = (id, result) => frame.contentWindow.postMessage({ jsonrpc: '2.0', id, result }, '*');
    window.addEventListener('message', event => {
      if (event.source !== frame.contentWindow) return;
      const message = event.data;
      if (message.method === 'ui/message') window.agentRequests.push(message);
      if (message.method === 'ui/initialize') window.reply(message.id, { protocolVersion: '2026-01-26', hostInfo: { name: 'test', version: '1' }, hostCapabilities: supported ? { message: { text: {} } } : {}, hostContext: { displayMode: 'fullscreen' } });
      if (message.method === 'tools/call') {
        if (['get_data_catalog', 'list_shares'].includes(message.params.name)) {
          window.discovery.push(message);
          if (window.holdDiscovery) return;
          if (window.failDiscovery) { window.reply(message.id, { isError: true }); return; }
          const text = message.params.name === 'get_data_catalog'
            ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': window.entries })
            : 'Shares: ' + JSON.stringify(window.shares);
          window.reply(message.id, { content: [{ type: 'text', text }] });
        } else window.reads.push(message);
      }
    });
    frame.srcdoc = html;
  }, { html, own, peer, second, other, paired, multiple, outgoingOnly, supported });
  return page.frameLocator('iframe');
}
async function respond(page, index, rows, truncated = false) {
  await page.evaluate(({ index, rows, truncated }) => {
    const request = window.reads[index];
    window.reply(request.id, { content: [{ type: 'text', text: `Records for ${request.params.arguments.data_type} from start to end${truncated ? ' (showing the first 1 of 2; narrow the time range for the rest)' : ''}: ${JSON.stringify(rows)}` }] });
  }, { index, rows, truncated });
}
const tell = ui => ui.getByRole('button', { name: 'Tell my agent', exact: true });
const input = ui => ui.getByRole('textbox', { name: 'Instructions for my agent' });
const choose = ui => ui.getByRole('button', { name: 'peer-user', exact: true }).click();

test('one row per exact peer, all same-peer channels chronological, one bottom composer with exact current context', async ({ page }) => {
  const ui = await open(page, { multiple: true });
  await expect(ui.locator('#meshes > li')).toHaveCount(2);
  await expect(ui.locator('#mesh-status')).toContainText('2 threads');
  await choose(ui);
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(3);
  const args = await page.evaluate(() => window.reads.map(r => r.params.arguments));
  expect(args.map(a => a.data_type)).toEqual([own.id, peer.id, second.id]);
  expect(args.some(a => a.fulcra_userid === 'other-user')).toBe(false);
  expect(new Set(args.map(a => a.start_time)).size).toBe(1);
  expect(new Set(args.map(a => a.end_time)).size).toBe(1);
  await respond(page, 0, [{ recorded_at: '2026-01-02T12:00:00Z', note: 'outgoing message' }]);
  await respond(page, 1, [{ recorded_at: '2026-01-01T12:00:00Z', note: JSON.stringify({ v: 1, body: '<img src=x onerror=alert(1)>unacked reply', mid: 'incoming-id', to_user: 'untrusted-routing' }) }]);
  await respond(page, 2, [{ recorded_at: '2026-01-03T12:00:00Z', note: 'second channel' }]);
  const rows = ui.locator('#messages > li');
  await expect(rows).toHaveCount(3);
  await expect(rows.first()).toContainText('Incoming');
  await expect(rows.first()).toContainText(`peer-user / ${peer.id}`);
  await expect(rows.nth(1)).toContainText(`Outgoing — me / ${own.id}`);
  await expect(rows.last()).toContainText(second.id);
  await expect(ui.locator('#messages img')).toHaveCount(0);
  await expect(tell(ui)).toHaveCount(1);
  await expect(ui.locator('#messages textarea')).toHaveCount(0);
  await expect(ui.locator('#messages + #thread-composer')).toBeVisible();
  await expect(tell(ui)).toBeDisabled();
  await input(ui).fill('Draft a response for my review.');
  expect(await page.evaluate(() => window.agentRequests.length)).toBe(0);
  // Unsubmitted edits must not change the applied context.
  await ui.locator('#message-start').fill('2020-01-01');
  await ui.locator('#message-end').fill('2020-01-02');
  await tell(ui).click();
  await expect(tell(ui)).toBeDisabled();
  await expect(input(ui)).toBeDisabled();
  await expect.poll(() => page.evaluate(() => window.agentRequests.length)).toBe(1);
  const sent = await page.evaluate(() => window.agentRequests[0].params);
  expect(sent.role).toBe('user');
  expect(sent.content[0].text).toContain('Draft a response for my review.');
  expect(sent.content[1].text).toBe(await ui.locator('#thread-context').textContent());
  expect(sent.content[1].text).toContain('untrusted');
  expect(sent.content[1].text).not.toContain('other-user');
  const context = JSON.parse(sent.content[1].text.split('\n').slice(1).join('\n'));
  expect(context.peer_fulcra_userid).toBe('peer-user');
  expect(context.range).toEqual({ start_time: args[0].start_time, end_time: args[0].end_time });
  expect(context.messages.map(m => m.source)).toEqual([
    { id: peer.id, fulcra_userid: 'peer-user' }, { id: own.id, fulcra_userid: 'me' }, { id: second.id, fulcra_userid: 'me' },
  ]);
  await page.evaluate(() => window.reply(window.agentRequests[0].id, { isError: true }));
  await expect(ui.locator('#agent-status')).toContainText('Check the conversation before retrying');
  await expect(input(ui)).toHaveValue('Draft a response for my review.');
  await tell(ui).click();
  await expect.poll(() => page.evaluate(() => window.agentRequests.length)).toBe(2);
  await page.evaluate(() => window.reply(window.agentRequests[1].id, {}));
  await expect(ui.locator('#agent-status')).toContainText('Request sent');
  await expect(input(ui)).toHaveValue('');
  expect(await page.evaluate(() => window.reads.every(r => r.params.name === 'get_records'))).toBe(true);
});

for (const outgoingOnly of [false, true]) test(`${outgoingOnly ? 'outgoing' : 'incoming'}-only empty thread can initiate instructions with missing-side notice`, async ({ page }) => {
  const ui = await open(page, { paired: outgoingOnly, outgoingOnly });
  await choose(ui);
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(1);
  await respond(page, 0, []);
  await expect(ui.locator('#message-status')).toContainText(`missing ${outgoingOnly ? 'incoming' : 'outgoing'}`);
  await expect(tell(ui)).toHaveCount(1);
  await input(ui).fill('Start planning with this peer.');
  await tell(ui).click();
  await expect.poll(() => page.evaluate(() => window.agentRequests.length)).toBe(1);
  const context = JSON.parse(await page.evaluate(() => window.agentRequests[0].params.content[1].text.split('\n').slice(1).join('\n')));
  expect(context.messages).toEqual([]);
  expect(context.peer_fulcra_userid).toBe('peer-user');
  expect(context.completeness).toBe('partial');
});

test('each load refreshes discovery; reload removes old composer, uses same dates for new channels and clears drafts', async ({ page }) => {
  const ui = await open(page, { paired: false });
  await choose(ui);
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(1);
  await respond(page, 0, [{ note: 'old record' }]);
  await input(ui).fill('old draft');
  await ui.locator('#message-start').fill('2026-01-01');
  await ui.locator('#message-end').fill('2026-01-02');
  await page.evaluate(id => { window.shares.outgoing.push({ data_types: [id], with_user_ids: ['peer-user'], share_all_data: false }); window.holdDiscovery = true; }, own.id);
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect(tell(ui)).toHaveCount(0);
  await expect(ui.locator('#messages > li')).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => window.discovery.length)).toBe(6);
  await page.evaluate(() => {
    window.holdDiscovery = false;
    for (const r of window.discovery.slice(4)) window.reply(r.id, { content: [{ type: 'text', text: r.params.name === 'list_shares' ? 'Shares: ' + JSON.stringify(window.shares) : 'Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': window.entries }) }] });
  });
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(3);
  for (const args of await page.evaluate(() => window.reads.slice(1).map(r => r.params.arguments))) {
    expect(args.start_time).toBe('2026-01-01T00:00:00.000Z');
    expect(args.end_time).toBe('2026-01-03T00:00:00.000Z');
  }
  await respond(page, 1, []); await respond(page, 2, []);
  await expect(ui.locator('#message-status')).toContainText('No messages in this range');
  await expect(ui.locator('#message-status')).toContainText('2026-01-01 through 2026-01-02 UTC');
  await expect(input(ui)).toHaveValue('');
  await expect(tell(ui)).toHaveCount(1);
  expect(await page.evaluate(() => window.agentRequests.length)).toBe(0);
  await ui.locator('#message-start').fill('2026-02-01');
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect(ui.locator('#message-status')).toContainText('Choose a valid date range');
  await expect(tell(ui)).toHaveCount(0);
});

test('partial failure and truncation remain visible and are sent as incomplete context', async ({ page }) => {
  const ui = await open(page);
  await choose(ui);
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(2);
  await respond(page, 1, [{ note: 'incoming preserved' }], true);
  await page.evaluate(() => window.reply(window.reads[0].id, { isError: true }));
  await expect(ui.locator('#message-status')).toContainText('Could not load messages — Outgoing');
  await expect(ui.locator('#message-status')).toContainText('Partial result — Incoming');
  await input(ui).fill('Explain the partial thread.'); await tell(ui).click();
  await expect.poll(() => page.evaluate(() => window.agentRequests.length)).toBe(1);
  const context = JSON.parse(await page.evaluate(() => window.agentRequests[0].params.content[1].text.split('\n').slice(1).join('\n')));
  expect(context.messages).toHaveLength(1);
  expect(context.warnings).toHaveLength(2);
  expect(context.completeness).toBe('partial');
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(4);
  await respond(page, 2, []);
  await page.evaluate(() => window.reply(window.reads[3].id, { isError: true }));
  await expect(ui.locator('#message-status')).toContainText('0 messages shown');
  await expect(ui.locator('#message-status')).not.toContainText('No messages in this range');
  await expect(tell(ui)).toHaveCount(1);
});

test('navigation ignores late multi-source success and failure, with no peer contamination', async ({ page }) => {
  const ui = await open(page);
  await choose(ui);
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(2);
  await ui.getByRole('button', { name: 'Back to threads' }).click();
  await ui.getByRole('button', { name: 'other-user', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(3);
  await respond(page, 2, [{ note: 'fresh other peer' }]);
  await respond(page, 0, [{ note: 'stale own' }]);
  await page.evaluate(() => window.reply(window.reads[1].id, { isError: true }));
  await expect(ui.locator('#messages')).toContainText('fresh other peer');
  await expect(ui.locator('#messages')).not.toContainText('stale');
  await expect(ui.locator('#message-status')).not.toContainText('Could not load');
  await input(ui).fill('Summarize current peer'); await tell(ui).click();
  await expect.poll(() => page.evaluate(() => window.agentRequests.length)).toBe(1);
  const context = await page.evaluate(() => window.agentRequests[0].params.content[1].text);
  expect(context).toContain('other-user');
  expect(context).not.toContain('peer-user');
  expect(context).not.toContain('stale own');
});

test('late discovery starts no stale reads; current failed discovery cannot submit old context, retry works', async ({ page }) => {
  const ui = await open(page);
  await expect(ui.locator('#meshes > li')).toHaveCount(2);
  await page.evaluate(() => { window.holdDiscovery = true; });
  await choose(ui);
  await expect.poll(() => page.evaluate(() => window.discovery.length)).toBe(4);
  await ui.getByRole('button', { name: 'Back to threads' }).click();
  await page.evaluate(() => {
    window.holdDiscovery = false;
    for (const r of window.discovery.slice(2)) window.reply(r.id, { isError: true });
  });
  await choose(ui);
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(2);
  await respond(page, 0, []); await respond(page, 1, []);
  await input(ui).fill('old draft');
  await page.evaluate(() => { window.failDiscovery = true; });
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect(ui.locator('#message-status')).toContainText('discovery failed');
  await expect(tell(ui)).toHaveCount(0);
  expect(await page.evaluate(() => window.reads.length)).toBe(2);
  await page.evaluate(() => { window.failDiscovery = false; });
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(4);
  await respond(page, 2, []); await respond(page, 3, []);
  await expect(tell(ui)).toHaveCount(1);
  expect(await page.evaluate(() => window.agentRequests.length)).toBe(0);
});

test('oversized displayed record is omitted whole, clipping disclosed in preview and host payload', async ({ page }) => {
  const ui = await open(page, { paired: false });
  await choose(ui);
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(1);
  await respond(page, 0, [{ note: 'small' }, { note: 'x'.repeat(30000) }]);
  await expect(ui.locator('#messages > li')).toHaveCount(2);
  await expect(ui.locator('#thread-composer')).toContainText('Context clipped — 1 displayed records omitted');
  await input(ui).fill('Summarize'); await tell(ui).click();
  await expect.poll(() => page.evaluate(() => window.agentRequests.length)).toBe(1);
  const payload = await page.evaluate(() => window.agentRequests[0].params.content[1].text);
  expect(payload.length).toBeLessThanOrEqual(24000);
  expect(payload).toBe(await ui.locator('#thread-context').textContent());
  expect(JSON.parse(payload.split('\n').slice(1).join('\n')).omitted_records).toBe(1);
});

test('unsupported host still reads an empty thread, but cannot Tell my agent', async ({ page }) => {
  const ui = await open(page, { paired: false, supported: false });
  await choose(ui);
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(1);
  await respond(page, 0, []);
  await input(ui).fill('Please help');
  await expect(tell(ui)).toBeDisabled();
  await expect(ui.locator('#agent-status')).toContainText('cannot send chat messages');
  expect(await page.evaluate(() => window.agentRequests.length)).toBe(0);
});
