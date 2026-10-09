import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
const html = await readFile(new URL('../fulcra_mcp/ui/mesh.html', import.meta.url), 'utf8');
const own = { id: 'MomentAnnotation/00000000-0000-0000-0000-000000000001', name: 'Mesh Outbox Same' };
const peer = { id: 'MomentAnnotation/00000000-0000-0000-0000-000000000002', name: 'Mesh Outbox Same', fulcra_userid: 'peer-user' };
const second = { ...own, id: 'MomentAnnotation/00000000-0000-0000-0000-000000000003' };
const other = { ...peer, fulcra_userid: 'other-user' };
async function open(page, { paired = true, multiple = false, outgoingOnly = false, supported = true, peerId = 'peer-user', safeAreaInsets } = {}) {
  await page.setContent('<iframe sandbox="allow-scripts"></iframe>');
  await page.evaluate(({ html, own, peer, second, other, paired, multiple, outgoingOnly, supported, peerId, safeAreaInsets }) => {
    peer.fulcra_userid = peerId;
    const grant = id => ({ data_types: [id], with_user_ids: [peerId], share_all_data: false });
    window.entries = [own, ...(outgoingOnly ? [] : [peer, peer]), other, ...(multiple ? [second] : [])];
    window.discovery = [];
    window.shares = { own_fulcra_userid: 'me', outgoing: paired ? [grant(own.id), grant(own.id), ...(multiple ? [grant(second.id)] : [])] : [], incoming: [] };
    window.reads = [];
    window.agentRequests = [];
    window.contexts = [];
    window.resizeNotifications = [];
    const frame = document.querySelector('iframe');
    window.reply = (id, result) => frame.contentWindow.postMessage({ jsonrpc: '2.0', id, result }, '*');
    window.addEventListener('message', event => {
      if (event.source !== frame.contentWindow) return;
      const message = event.data;
      if (message.method === 'ui/notifications/size-changed') window.resizeNotifications.push(message.params);
      if (message.method === 'ui/message') { window.agentRequests.push(message); if (message.params.content[0].text === 'Let’s talk about this mesh thread.') window.reply(message.id, {}); }
      if (message.method === 'ui/update-model-context') { window.contexts.push(message); window.reply(message.id, {}); }
      if (message.method === 'ui/initialize') window.reply(message.id, { protocolVersion: '2026-01-26', hostInfo: { name: 'test', version: '1' }, hostCapabilities: supported ? { message: { text: {} }, updateModelContext: { text: {} } } : {}, hostContext: { displayMode: 'fullscreen', safeAreaInsets } });
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
  }, { html, own, peer, second, other, paired, multiple, outgoingOnly, supported, peerId, safeAreaInsets });
  return page.frameLocator('iframe');
}
async function respond(page, index, rows, truncated = false) {
  await page.evaluate(({ index, rows, truncated }) => {
    const request = window.reads[index];
    window.reply(request.id, { content: [{ type: 'text', text: `Records for ${request.params.arguments.data_type} from start to end${truncated ? ' (showing the first 1 of 2; narrow the time range for the rest)' : ''}: ${JSON.stringify(rows)}` }] });
  }, { index, rows, truncated });
}
for (const width of [1120, 320]) test(`simplified message headers and muted separate dates at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1100 });
  await page.clock.install({ time: new Date('2026-01-10T12:00:00Z') });
  await page.clock.pauseAt(new Date('2026-01-10T12:00:01Z'));
  const ui = await open(page);
  await page.addStyleTag({ content: 'body { margin: 0; background: black; } iframe { display: block; width: 100%; height: 100vh; border: 0; }' });
  await choose(ui);
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(2);
  await respond(page, 0, [{ id: 'out', recorded_at: '2026-01-10T10:00:00Z', note: JSON.stringify({ v: 1, kind: 'message', mid: 'out', body: 'The route is ready. Shall we meet by the river?' }) }]);
  await respond(page, 1, [{ id: 'in', recorded_at: '2026-01-10T11:00:00Z', note: JSON.stringify({ v: 1, kind: 'reply', mid: 'in', body: 'Yes, the riverside meeting point works for me.' }) }]);
  const row = ui.locator('#messages > li').first();
  await expect(row.locator('p').first()).toHaveText(`Incoming (${peer.name})`);
  const date = row.locator('.message-date');
  await expect(date).toHaveText(await row.evaluate(() => `${new Date('2026-01-10T11:00:00Z').toLocaleString()} (your local time)`));
  await expect(date).toHaveCSS('color', 'rgb(138, 138, 142)');
  const headingBox = await row.locator('p').first().boundingBox(), dateBox = await date.boundingBox();
  expect(dateBox.y).toBeGreaterThanOrEqual(headingBox.y + headingBox.height);
  expect(await ui.locator('html').evaluate(el => el.scrollWidth <= innerWidth)).toBe(true);
  if (process.env.SIMPLIFY_PREVIEW_DIR) {
    await page.screenshot({ path: `${process.env.SIMPLIFY_PREVIEW_DIR}/thread-${width}.png` });
    await row.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${process.env.SIMPLIFY_PREVIEW_DIR}/messages-${width}.png` });
    await ui.locator('.reading-details summary').click();
    await expect(ui.locator('#thread-help')).toBeVisible();
    await page.screenshot({ path: `${process.env.SIMPLIFY_PREVIEW_DIR}/about-${width}.png` });
  }
});

for (const width of [1120, 320]) test(`refresh UX first load, error and success at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1100 });
  await page.clock.install({ time: new Date('2026-01-10T12:00:00Z') });
  await page.clock.pauseAt(new Date('2026-01-10T12:00:01Z'));
  const ui = await open(page);
  await page.addStyleTag({ content: 'body { margin: 0; background: black; } iframe { display: block; width: 100%; height: 100vh; border: 0; }' });
  await choose(ui);
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(2);
  await expect(ui.locator('#message-loading')).toBeVisible();
  await expect(ui.locator('#refresh-status')).toHaveCount(0);
  const capture = async state => {
    expect(await ui.locator('html').evaluate(el => el.scrollWidth <= innerWidth)).toBe(true);
    await ui.locator('body').evaluate(() => scrollTo(0, 0));
    if (process.env.REFRESH_PREVIEW_DIR) await page.screenshot({ path: `${process.env.REFRESH_PREVIEW_DIR}/${state}-${width}.png` });
  };
  await capture('firstload');
  await page.evaluate(() => { for (const request of window.reads) window.reply(request.id, { isError: true }); });
  await expect(ui.locator('#message-loading')).toBeHidden();
  await expect(ui.locator('#message-status')).toHaveText('Could not load messages. Retrying in 20 seconds.');
  await capture('error');
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(4);
  await expect(ui.locator('#message-loading')).toBeHidden();
  await expect(ui.locator('#message-status')).toHaveText('Could not load messages. Retrying…');
  await respond(page, 2, [{ id: 'out', recorded_at: '2026-01-10T10:00:00Z', note: JSON.stringify({ v: 1, body: 'The route is ready. Shall we meet by the river?' }) }]);
  await respond(page, 3, [{ id: 'in', recorded_at: '2026-01-10T11:00:00Z', note: JSON.stringify({ v: 1, body: 'Yes, the riverside meeting point works for me.' }) }]);
  await expect(ui.locator('#messages li')).toHaveCount(2);
  await expect(ui.locator('#message-status')).toBeEmpty();
  await page.clock.runFor(250);
  await capture('success');
  expect(await page.evaluate(() => window.agentRequests.length)).toBe(0);
});

// Synthetic fixtures only: the real bundled SDK talks to this local host harness.
test('global handoff help lives in About this thread and obsolete date copy is absent', async ({ page }) => {
  const ui = await open(page);
  await choose(ui);
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(2);
  await respond(page, 0, []); await respond(page, 1, []);
  const about = ui.locator('.reading-details');
  const help = about.getByText(/Send posts your exact message directly/);
  await expect(help).toHaveCount(1);
  await expect(help).toBeHidden();
  await expect(ui.locator('#thread-composer > p')).toHaveCount(0);
  await expect(ui.locator('body')).not.toContainText('Initially today and yesterday, in UTC. Dates are inclusive. Load messages applies edited dates.');
  await about.locator('summary').click();
  await expect(help).toBeVisible();
  await expect(help).toContainText('0 of 0 displayed records');
  await ui.getByRole('button', { name: 'Back to threads' }).click();
  await choose(ui);
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(4);
  await respond(page, 2, []); await respond(page, 3, []);
  await expect(help).toHaveCount(1);
  await expect(tell(ui)).toBeEnabled();
});
test('Refresh threads is hidden in detail and restored by Back', async ({ page }) => {
  const ui = await open(page);
  const refresh = ui.getByRole('button', { name: 'Refresh threads', exact: true });
  await expect(refresh).toBeVisible();
  await choose(ui);
  await expect(refresh).toBeHidden();
  await ui.getByRole('button', { name: 'Back to threads' }).click();
  await expect(refresh).toBeVisible();
});
for (const width of [1120, 320]) test(`global top-right invitation and list-only refresh at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  await page.clock.install({ time: new Date('2026-01-10T12:00:00Z') });
  await page.clock.pauseAt(new Date('2026-01-10T12:00:01Z'));
  const ui = await open(page);
  await page.addStyleTag({ content: 'body { margin: 0; background: black; } iframe { display: block; width: 100%; height: 100vh; border: 0; }' });
  const invite = ui.getByRole('button', { name: 'Invite someone', exact: true });
  const refresh = ui.getByRole('button', { name: 'Refresh threads', exact: true });
  const assertTopRight = async view => {
    await expect(invite).toBeEnabled();
    const button = await invite.boundingBox(), content = await view.boundingBox(), main = await ui.locator('main').boundingBox();
    expect(button.y + button.height).toBeLessThanOrEqual(content.y);
    expect(Math.abs(button.x + button.width - main.x - main.width)).toBeLessThan(2);
    expect(await ui.locator('html').evaluate(el => el.scrollWidth <= innerWidth)).toBe(true);
  };
  await expect(refresh).toBeVisible();
  await assertTopRight(ui.locator('#mesh-list'));
  if (process.env.LAYOUT_PREVIEW_DIR) await page.screenshot({ path: `${process.env.LAYOUT_PREVIEW_DIR}/layout-list-${width}.png` });
  await invite.focus(); await page.keyboard.press('Enter');
  await expect.poll(() => page.evaluate(() => window.agentRequests.length)).toBe(1);
  await page.evaluate(() => window.reply(window.agentRequests[0].id, {}));
  await expect(ui.locator('#status')).toContainText('Request sent');
  await choose(ui);
  await expect(refresh).toBeHidden();
  await expect(ui.getByRole('button', { name: 'Back to threads' })).toBeVisible();
  await expect(ui.getByRole('button', { name: 'Load messages', exact: true })).toBeVisible();
  await expect(ui.locator('#message-loading')).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(2);
  await respond(page, 0, []); await respond(page, 1, []);
  await expect(ui.locator('#message-loading')).toBeHidden();
  await assertTopRight(ui.locator('#mesh-detail'));
  await expect(ui.locator('#status')).toHaveAttribute('role', 'status');
  await expect(ui.locator('#status')).toContainText('Request sent');
  if (process.env.LAYOUT_PREVIEW_DIR) await page.screenshot({ path: `${process.env.LAYOUT_PREVIEW_DIR}/layout-thread-${width}.png` });
  await invite.click();
  await expect.poll(() => page.evaluate(() => window.agentRequests.length)).toBe(2);
  await page.evaluate(() => window.reply(window.agentRequests[1].id, { isError: true }));
  await expect(ui.locator('#status')).toContainText('Could not send');
  await expect(invite).toBeEnabled();
  await ui.getByRole('button', { name: 'Back to threads' }).click();
  await expect(refresh).toBeVisible();
  await assertTopRight(ui.locator('#mesh-list'));
  expect(await page.evaluate(() => window.contexts.length)).toBe(0);
});
for (const width of [1120, 320]) test(`Fulcra branding, keyboard and host footer clearance at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  await page.clock.setFixedTime(new Date('2026-01-10T12:00:00Z'));
  const networkRequests = [];
  page.on('request', request => networkRequests.push(request.url()));
  const peerId = '00000000-0000-0000-0000-000000000042';
  const ui = await open(page, { peerId, safeAreaInsets: { top: 0, right: 0, bottom: 12, left: 0 } });
  await page.addStyleTag({ content: 'body { margin: 0; background: black; } iframe { display: block; width: 100%; height: 100vh; border: 0; } #host-composer { position: fixed; inset: auto 0 0; height: 160px; background: #25252b; color: white; display: grid; place-items: center; font: 14px sans-serif; }' });
  await page.evaluate(() => {
    const overlay = document.createElement('div');
    overlay.id = 'host-composer';
    overlay.textContent = 'Simulated host message bar · synthetic preview';
    document.body.append(overlay);
  });
  await expect(ui.getByRole('heading', { name: 'Fulcra Mesh', exact: true })).toBeVisible();
  await expect(ui.locator('body')).not.toContainText(/hello world|proof of concept|served by|demo/i);
  await expect(ui.locator('body')).toHaveCSS('padding-bottom', '172px');
  expect(await ui.locator('html').evaluate(el => el.scrollWidth <= innerWidth)).toBe(true);
  await ui.getByRole('button', { name: peerId, exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(2);
  await respond(page, 0, [{ recorded_at: '2026-01-02T12:00:00Z', note: JSON.stringify({ v: 1, body: 'The walking route is ready. Can you review the meeting point?', mid: '00000000-0000-0000-0000-000000000001' }) }]);
  await respond(page, 1, [{ recorded_at: '2026-01-01T12:00:00Z', note: JSON.stringify({ v: 1, body: 'Let’s meet by the river. Synthetic reference: ' + '0123456789abcdef'.repeat(12), mid: '00000000-0000-0000-0000-000000000002' }) }]);
  await expect(tell(ui)).toBeVisible();
  const frame = page.frames()[1];
  const assertNoOverflow = async () => expect(await frame.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await assertNoOverflow();
  expect(await ui.locator('body').evaluate(el => getComputedStyle(el).fontFamily)).toContain('Rubik');
  expect(await frame.evaluate(async () => { await document.fonts.ready; return [...document.fonts].some(font => font.family === 'Rubik' && font.status === 'loaded'); })).toBe(true);
  expect(await ui.locator('body').evaluate(el => parseFloat(getComputedStyle(el).paddingBottom))).toBeGreaterThanOrEqual(160);
  // SDK host context notifications update insets; unrelated updates preserve them.
  await page.evaluate(() => document.querySelector('iframe').contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/host-context-changed', params: { safeAreaInsets: { top: 0, right: 0, bottom: 24, left: 0 } } }, '*'));
  await expect.poll(() => ui.locator('body').evaluate(el => parseFloat(getComputedStyle(el).paddingBottom))).toBeGreaterThanOrEqual(184);
  await page.evaluate(() => document.querySelector('iframe').contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/host-context-changed', params: { theme: 'light' } }, '*'));
  await expect.poll(() => ui.locator('body').evaluate(el => parseFloat(getComputedStyle(el).paddingBottom))).toBeGreaterThanOrEqual(184);
  const aboveOverlay = async locator => {
    await locator.evaluate(el => el.scrollIntoView({ block: 'center' }));
    const box = await locator.boundingBox();
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y + box.height).toBeLessThanOrEqual(740);
  };
  await ui.locator('#message-load').focus();
  await page.keyboard.press('Tab');
  await expect(ui.locator('textarea')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(tell(ui)).toBeFocused();
  expect(await tell(ui).evaluate(el => getComputedStyle(el).outlineStyle)).toBe('solid');
  await aboveOverlay(tell(ui));
  await page.keyboard.press('Enter');
  await expect.poll(() => page.evaluate(() => window.contexts.length)).toBe(1);
  await expect(ui.locator('#send-status')).toContainText('accepted');
  await aboveOverlay(ui.locator('#send-status'));
  const disclosure = ui.locator('#thread-composer .context-details summary');
  await aboveOverlay(disclosure);
  await disclosure.focus();
  await page.keyboard.press('Enter');
  await expect(ui.locator('#thread-context')).toBeVisible();
  await assertNoOverflow();
  await page.keyboard.press('Enter');
  await aboveOverlay(ui.locator('#invite'));
  if (process.env.BRAND_PREVIEW_DIR) {
    await aboveOverlay(ui.locator('#send-status'));
    const feedbackBox = await ui.locator('#send-status').boundingBox();
    expect(feedbackBox.y + feedbackBox.height).toBeLessThanOrEqual(740);
    await page.screenshot({ path: `${process.env.BRAND_PREVIEW_DIR}/brand-preview-composer-${width === 320 ? 'narrow' : 'wide'}.png` });
  }
  await ui.locator('#invite').focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => page.evaluate(() => window.agentRequests.length)).toBe(2);
  await page.evaluate(() => window.reply(window.agentRequests[1].id, {}));
  await aboveOverlay(ui.locator('#status'));
  await assertNoOverflow();
  expect(networkRequests).toEqual([]);
  await expect.poll(() => page.evaluate(() => window.resizeNotifications.length)).toBeGreaterThan(0);
  if (process.env.BRAND_PREVIEW_DIR) {
    await frame.evaluate(() => scrollTo(0, 0));
    await page.screenshot({ path: `${process.env.BRAND_PREVIEW_DIR}/brand-preview-${width === 320 ? 'narrow' : 'wide'}.png` });
  }
});

const tell = ui => ui.getByRole('button', { name: 'talk with my agent about this thread', exact: true });
const choose = ui => ui.getByRole('button', { name: 'peer-user', exact: true }).click();

test('one row per exact peer, all same-peer channels latest first, one top composer with exact current context', async ({ page }) => {
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
  await expect(rows.last().locator('p').first()).toHaveText(`Incoming (${peer.name})`);
  await expect(rows.nth(1).locator('p').first()).toHaveText('Outgoing');
  await expect(rows.first().locator('p').first()).toHaveText('Outgoing');
  await expect(ui.locator('#messages')).not.toContainText('MomentAnnotation/');
  await expect(rows.last().locator('pre')).toHaveText('<img src=x onerror=alert(1)>unacked reply');
  await expect(ui.locator('#messages img')).toHaveCount(0);
  await expect(tell(ui)).toHaveCount(1);
  await expect(ui.locator('#messages textarea')).toHaveCount(0);
  await expect(ui.locator('#message-range + #thread-composer')).toBeVisible();
  await expect(tell(ui)).toBeEnabled();
  await expect(ui.locator('textarea')).toHaveCount(1);
  expect(await page.evaluate(() => window.agentRequests.length)).toBe(0);
  // Unsubmitted edits must not change the applied context.
  await ui.locator('#message-start').fill('2020-01-01');
  await ui.locator('#message-end').fill('2020-01-02');
  await tell(ui).click();
  await expect.poll(() => page.evaluate(() => window.contexts.length)).toBe(1);
  const sent = await page.evaluate(() => window.contexts[0].params);
  expect(sent.content).toHaveLength(1);
  expect(sent.content[0].text).toBe(await ui.locator('#thread-context').textContent());
  expect(sent.content[0].text).toContain('untrusted');
  expect(sent.content[0].text).not.toContain('other-user');
  const context = JSON.parse(sent.content[0].text.split('\n').slice(1).join('\n'));
  expect(context.peer_fulcra_userid).toBe('peer-user');
  expect(context.range).toEqual({ start_time: args[0].start_time, end_time: args[0].end_time });
  expect(context.messages.map(m => m.source)).toEqual([
    { id: second.id, name: second.name, fulcra_userid: 'me' }, { id: own.id, name: own.name, fulcra_userid: 'me' }, { id: peer.id, name: peer.name, fulcra_userid: 'peer-user' },
  ]);
  await expect(ui.locator('#send-status')).toContainText('accepted');
  expect(await page.evaluate(() => window.agentRequests.length)).toBe(1);
  expect(await page.evaluate(() => window.reads.every(r => r.params.name === 'get_records'))).toBe(true);
});

for (const outgoingOnly of [false, true]) test(`${outgoingOnly ? 'outgoing' : 'incoming'}-only empty thread can initiate instructions with missing-side notice`, async ({ page }) => {
  const ui = await open(page, { paired: outgoingOnly, outgoingOnly });
  await choose(ui);
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(1);
  await respond(page, 0, []);
  await expect(ui.locator('#message-status')).toHaveText('No messages in this date range.');
  await expect(ui.locator('#thread-context')).toContainText(`missing ${outgoingOnly ? 'incoming' : 'outgoing'}`);
  await expect(tell(ui)).toHaveCount(1);
  await tell(ui).click();
  await expect.poll(() => page.evaluate(() => window.contexts.length)).toBe(1);
  const context = JSON.parse(await page.evaluate(() => window.contexts[0].params.content[0].text.split('\n').slice(1).join('\n')));
  expect(context.messages).toEqual([]);
  expect(context.peer_fulcra_userid).toBe('peer-user');
  expect(context.completeness).toBe('partial');
});

test('each load refreshes discovery; reload preserves disclosure, applies same dates to new channels', async ({ page }) => {
  const ui = await open(page, { paired: false });
  await choose(ui);
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(1);
  await respond(page, 0, [{ note: 'old record' }]);
  await ui.locator('#thread-composer .context-details summary').click();
  await ui.locator('#message-start').fill('2026-01-01');
  await ui.locator('#message-end').fill('2026-01-02');
  await page.evaluate(id => { window.shares.outgoing.push({ data_types: [id], with_user_ids: ['peer-user'], share_all_data: false }); window.holdDiscovery = true; }, own.id);
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect(tell(ui)).toHaveCount(1);
  await expect(tell(ui)).toBeDisabled();
  await expect(ui.locator('#messages > li')).toHaveCount(1);
  await expect(ui.locator('#thread-composer .context-details')).toHaveAttribute('open', '');
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
  await expect(ui.locator('#message-status')).toHaveText('No messages in this date range.');
  await expect(ui.locator('#thread-context')).toContainText('2026-01-01T00:00:00.000Z');
  await expect(ui.locator('#thread-composer .context-details')).toHaveAttribute('open', '');
  await expect(tell(ui)).toHaveCount(1);
  expect(await page.evaluate(() => window.agentRequests.length)).toBe(0);
  await ui.locator('#message-start').fill('2026-02-01');
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect(ui.locator('#message-status')).toContainText('Choose a valid date range');
  await expect(tell(ui)).toHaveCount(1);
  await expect(ui.locator('#thread-context')).toContainText('2026-01-01T00:00:00.000Z');
  expect(await page.evaluate(() => window.reads.length)).toBe(3);
});

test('partial failure and truncation remain visible and are sent as incomplete context', async ({ page }) => {
  const ui = await open(page);
  await choose(ui);
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(2);
  await respond(page, 1, [{ note: 'incoming preserved' }], true);
  await page.evaluate(() => window.reply(window.reads[0].id, { isError: true }));
  await expect(ui.locator('#message-status')).toContainText('Could not load messages. Retrying');
  await expect(ui.locator('#thread-context')).toContainText('Could not load messages — Outgoing');
  await expect(ui.locator('#thread-context')).toContainText('Partial result — Incoming');
  await tell(ui).click();
  await expect.poll(() => page.evaluate(() => window.contexts.length)).toBe(1);
  const context = JSON.parse(await page.evaluate(() => window.contexts[0].params.content[0].text.split('\n').slice(1).join('\n')));
  expect(context.messages).toHaveLength(1);
  expect(context.warnings).toHaveLength(2);
  expect(context.completeness).toBe('partial');
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(4);
  await respond(page, 2, []);
  await page.evaluate(() => window.reply(window.reads[3].id, { isError: true }));
  await expect(ui.locator('#message-status')).toContainText('Could not load messages. Retrying');
  await expect(ui.locator('#thread-context')).toContainText('"stale":true');
  await expect(ui.locator('#messages')).toContainText('incoming preserved');
  await expect(ui.locator('#message-status')).not.toContainText('No messages in this date range');
  await expect(tell(ui)).toHaveCount(1);
});

test('navigation ignores late multi-source success and failure, with no peer contamination', async ({ page }) => {
  const ui = await open(page);
  await choose(ui);
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(2);
  await ui.getByRole('button', { name: 'Back to threads' }).click();
  await ui.getByRole('button', { name: 'other-user', exact: true }).click();
  expect(await page.evaluate(() => window.reads.length)).toBe(2);
  await respond(page, 0, [{ note: 'stale own' }]);
  await page.evaluate(() => window.reply(window.reads[1].id, { isError: true }));
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(3);
  await respond(page, 2, [{ note: 'fresh other peer' }]);
  await expect(ui.locator('#messages')).toContainText('fresh other peer');
  await expect(ui.locator('#messages')).not.toContainText('stale');
  await expect(ui.locator('#message-status')).not.toContainText('Could not load');
  await tell(ui).click();
  await expect.poll(() => page.evaluate(() => window.contexts.length)).toBe(1);
  const context = await page.evaluate(() => window.contexts[0].params.content[0].text);
  expect(context).toContain('other-user');
  expect(context).not.toContain('peer-user');
  expect(context).not.toContain('stale own');
});

test('late discovery starts no stale reads; failed discovery retains sendable loaded context, retry works', async ({ page }) => {
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
  await page.evaluate(() => { window.failDiscovery = true; });
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect(ui.locator('#message-status')).toContainText('Could not load messages. Retrying');
  await expect(ui.locator('#thread-context')).toContainText('discovery failed');
  await expect(tell(ui)).toBeEnabled();
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
  await ui.locator('.reading-details summary').click();
  await expect(ui.locator('#thread-help')).toBeVisible();
  await expect(ui.locator('#thread-help')).toContainText('Context clipped — 1 displayed records omitted');
  await tell(ui).click();
  await expect.poll(() => page.evaluate(() => window.contexts.length)).toBe(1);
  const payload = await page.evaluate(() => window.contexts[0].params.content[0].text);
  expect(payload.length).toBeLessThanOrEqual(24000);
  expect(payload).toBe(await ui.locator('#thread-context').textContent());
  expect(JSON.parse(payload.split('\n').slice(1).join('\n')).omitted_records).toBe(1);
});

test('unsupported host still reads an empty thread, but cannot attach context', async ({ page }) => {
  const ui = await open(page, { paired: false, supported: false });
  await choose(ui);
  await expect.poll(() => page.evaluate(() => window.reads.length)).toBe(1);
  await respond(page, 0, []);
  await expect(tell(ui)).toBeDisabled();
  await expect(ui.locator('#send-status')).toContainText('does not support');
  expect(await page.evaluate(() => window.agentRequests.length)).toBe(0);
});
