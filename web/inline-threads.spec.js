import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
const bundle = await readFile(new URL('../fulcra_mcp/ui/mesh.html', import.meta.url), 'utf8');
async function open(page, options = {}) {
  await page.clock.install({ time: new Date('2026-01-10T12:00:00Z') });
  await page.clock.pauseAt(new Date('2026-01-10T12:00:01Z'));
  await page.setContent('<style>body{margin:0}iframe{width:100%;height:1000px;border:0}</style><iframe sandbox="allow-scripts"></iframe>');
  await page.evaluate(({ bundle, options }) => {
    const frame = document.querySelector('iframe');
    window.options = options; window.requests = []; window.peers = ['peer', 'other'];
    window.reply = (id, result) => frame.contentWindow.postMessage({ jsonrpc: '2.0', id, result }, '*');
    window.notify = (method, params) => frame.contentWindow.postMessage({ jsonrpc: '2.0', method, params }, '*');
    window.initial = () => window.notify('ui/notifications/tool-result', { content: [], structuredContent: { presentation: 'threads' } });
    addEventListener('message', ({ data: r, source }) => {
      if (source !== frame.contentWindow) return;
      window.requests.push(r);
      if (r.method === 'ui/initialize') {
        if (options.early) window.initial();
        window.reply(r.id, { protocolVersion: '2026-01-26', hostInfo: { name: 'synthetic', version: '1' },
          hostContext: { displayMode: options.mode ?? 'inline', availableDisplayModes: options.unsupported ? ['inline'] : ['inline', 'fullscreen'] },
          hostCapabilities: { message: { text: {} }, updateModelContext: { text: {} }, ...(options.sampling ? { sampling: {} } : {}) } });
      }
      if (r.method === 'ui/notifications/initialized' && !options.early && !options.holdInitial) window.initial();
      if (r.method === 'tools/call') {
        const { name, arguments: args } = r.params;
        const text = name === 'get_data_catalog' ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': window.peers.map(peer => ({ id: 'MomentAnnotation/in', name: 'Mesh Outbox', fulcra_userid: peer })) })
          : name === 'list_shares' ? 'Shares: ' + JSON.stringify({ own_fulcra_userid: 'me', incoming: [], outgoing: [] })
          : `Records for ${args.data_type} from start to end: ` + JSON.stringify([{ id: 'one', note: 'Untrusted peer text' }]);
        window.reply(r.id, { content: [{ type: 'text', text }] });
      }
      if (r.method === 'ui/request-display-mode' && !window.options.holdDisplay) {
        if (options.error) frame.contentWindow.postMessage({ jsonrpc: '2.0', id: r.id, error: { code: -32603, message: 'Rejected' } }, '*');
        else window.reply(r.id, { mode: options.denied ? 'inline' : 'fullscreen' });
      }
      if (r.method === 'ui/update-model-context' && !window.options.holdContext) window.reply(r.id, {});
      if (r.method === 'ui/message') window.reply(r.id, {});
    });
    frame.srcdoc = bundle.replace('<meta name="mesh-presentation" content="global">', '<meta name="mesh-presentation" content="threads">');
    if (options.direct) frame.srcdoc = frame.srcdoc.replace('</head>', '<meta name="mesh-startup" content="resource"></head>');
  }, { bundle, options });
  return page.frameLocator('iframe');
}
async function noSideEffects(page) {
  expect(await page.evaluate(() => window.requests.filter(r => ['ui/message', 'sampling/createMessage'].includes(r.method)))).toEqual([]);
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'tools/call').every(r => ['get_data_catalog', 'list_shares', 'get_records'].includes(r.params.name)))).toBe(true);
}
test('direct resource boots without tool result and ignores late result', async ({ page }) => {
  const ui = await open(page, { direct: true, holdInitial: true });
  await expect(ui.locator('#mesh-status')).toContainText('2 threads returned');
  await expect(ui.locator('#entrypoint-status')).not.toContainText('Waiting');
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'tools/call').map(r => r.params.name))).toEqual(['get_data_catalog', 'list_shares']);
  await expect(ui.locator('#mesh-detail')).toBeHidden();
  await page.evaluate(() => window.initial());
  await page.clock.runFor(1000);
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'tools/call').length)).toBe(2);
  await noSideEffects(page);
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect(ui.locator('#messages')).toContainText('Untrusted');
  await noSideEffects(page);
});
for (const outcome of ['denied', 'unsupported', 'error']) test(`panel ${outcome} stays a read-only list`, async ({ page }) => {
  const ui = await open(page, { [outcome]: true });
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect(ui.locator('#entrypoint-status')).toContainText(outcome === 'denied' ? 'host kept inline' : outcome === 'unsupported' ? 'does not advertise fullscreen' : 'Could not confirm fullscreen');
  await expect(ui.locator('#mesh-detail')).toBeHidden();
  await expect(ui.locator('textarea')).toHaveCount(0);
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'tools/call' && r.params.name === 'get_records'))).toEqual([]);
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'ui/request-display-mode').length)).toBe(outcome === 'unsupported' ? 0 : 1);
  await noSideEffects(page);
});
for (const failure of ['error', 'timeout']) test(`display ${failure} does not claim the host panel stayed closed`, async ({ page }) => {
  const ui = await open(page, failure === 'timeout' ? { holdDisplay: true } : { error: true });
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  if (failure === 'timeout') {
    await expect(ui.locator('#entrypoint-status')).toContainText('Requesting');
    await page.clock.runFor(15001);
  }
  await expect(ui.locator('#entrypoint-status')).toContainText('Could not confirm');
  await expect(ui.locator('#entrypoint-status')).not.toContainText('No conversation panel was opened');
  await expect(ui.locator('#entrypoint-status')).toContainText('The thread list remains open');
  await expect(ui.locator('#mesh-detail')).toBeHidden();
  await expect(ui.locator('textarea')).toHaveCount(0);
  await noSideEffects(page);
});
for (const change of ['inline', 'revoked', 'revoked-returned', 'teardown']) test(`late fullscreen cannot select after ${change}`, async ({ page }) => {
  const ui = await open(page, { holdDisplay: true });
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect(ui.locator('#entrypoint-status')).toContainText('Requesting');
  if (change === 'inline') {
    await page.evaluate(() => window.notify('ui/notifications/host-context-changed', { displayMode: 'inline' }));
    await expect(ui.locator('#entrypoint-status')).toContainText('inline');
  } else if (change.startsWith('revoked')) {
    await page.evaluate(() => { window.peers = ['other']; });
    await ui.getByRole('button', { name: 'Refresh threads' }).click();
    await expect(ui.getByRole('button', { name: 'peer', exact: true })).toHaveCount(0);
    if (change === 'revoked-returned') {
      await page.evaluate(() => { window.peers = ['peer', 'other']; });
      await ui.getByRole('button', { name: 'Refresh threads' }).click();
      await expect(ui.getByRole('button', { name: 'peer', exact: true })).toBeVisible();
    }
  } else {
    await page.evaluate(() => document.querySelector('iframe').contentWindow.postMessage({ jsonrpc: '2.0', id: 'teardown', method: 'ui/resource-teardown', params: {} }, '*'));
    await expect.poll(() => page.evaluate(() => window.requests.some(r => r.id === 'teardown' && 'result' in r))).toBe(true);
  }
  await page.evaluate(() => window.reply(window.requests.find(r => r.method === 'ui/request-display-mode').id, { mode: 'fullscreen' }));
  // A subsequent bridge notification is a FIFO barrier for the late response.
  await page.evaluate(() => window.notify('ui/notifications/host-context-changed', { theme: 'dark' }));
  await page.clock.runFor(1000);
  await expect(ui.locator('#mesh-detail')).toBeHidden();
  await expect(ui.locator('textarea')).toHaveCount(0);
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'tools/call' && r.params.name === 'get_records'))).toEqual([]);
  await noSideEffects(page);
});
test('host inline return clears selected context and pending thread actions', async ({ page }) => {
  const ui = await open(page);
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect(ui.locator('#messages')).toContainText('Untrusted');
  await ui.locator('textarea').fill('unsent');
  await page.evaluate(() => window.notify('ui/notifications/host-context-changed', { displayMode: 'inline' }));
  await expect(ui.locator('#mesh-detail')).toBeHidden();
  await expect(ui.locator('textarea')).toHaveCount(0);
  await expect(ui.locator('#messages li')).toHaveCount(0);
  const reads = await page.evaluate(() => window.requests.filter(r => r.method === 'tools/call' && r.params.name === 'get_records').length);
  await page.clock.runFor(10000);
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'tools/call' && r.params.name === 'get_records').length)).toBe(reads);
  await noSideEffects(page);
});
test('back stays fullscreen and another peer uses shared composer without another request', async ({ page }) => {
  const ui = await open(page, { sampling: true });
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect(ui.locator('#messages')).toContainText('Untrusted');
  await ui.getByRole('button', { name: 'Back to threads' }).click();
  await ui.getByRole('button', { name: 'other', exact: true }).click();
  await expect(ui.locator('#message-title')).toHaveText('Thread with other');
  await expect(ui.getByRole('button', { name: 'Suggest replies', exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'ui/request-display-mode').length)).toBe(1);
  await noSideEffects(page);
});
test('inline return during attachment clears context and never sends', async ({ page }) => {
  const ui = await open(page, { holdContext: true });
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect(ui.locator('#messages')).toContainText('Untrusted');
  await ui.locator('textarea').fill('Do not send after navigation');
  await ui.getByRole('button', { name: 'talk with my agent about this thread', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.requests.filter(r => r.method === 'ui/update-model-context').length)).toBe(1);
  await page.evaluate(() => window.notify('ui/notifications/host-context-changed', { displayMode: 'inline' }));
  await expect(ui.locator('#mesh-detail')).toBeHidden();
  await page.evaluate(() => {
    window.options.holdContext = false;
    window.reply(window.requests.find(r => r.method === 'ui/update-model-context').id, {});
  });
  await expect(ui.locator('#context-status')).toContainText('cleared');
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'ui/update-model-context').at(-1).params)).toEqual({ content: [] });
  await noSideEffects(page);
});
test('late display response after timeout cannot replace a newer peer selection', async ({ page }) => {
  const ui = await open(page, { holdDisplay: true });
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect(ui.locator('#entrypoint-status')).toContainText('Requesting');
  await page.clock.runFor(15001);
  await expect(ui.locator('#entrypoint-status')).toContainText('Could not confirm fullscreen');
  await ui.getByRole('button', { name: 'other', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.requests.filter(r => r.method === 'ui/request-display-mode').length)).toBe(2);
  await page.evaluate(() => window.reply(window.requests.filter(r => r.method === 'ui/request-display-mode')[1].id, { mode: 'fullscreen' }));
  await expect(ui.locator('#messages')).toContainText('Untrusted');
  await page.evaluate(() => window.reply(window.requests.filter(r => r.method === 'ui/request-display-mode')[0].id, { mode: 'fullscreen' }));
  await page.clock.runFor(1000);
  await expect(ui.locator('#message-title')).toHaveText('Thread with other');
  await noSideEffects(page);
});
test('delayed initial result does not replace an explicit selected peer', async ({ page }) => {
  const ui = await open(page, { holdInitial: true });
  await expect(ui.locator('#entrypoint-status')).toContainText('Waiting');
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'tools/call'))).toEqual([]);
  await ui.getByRole('button', { name: 'Refresh threads' }).click();
  await ui.getByRole('button', { name: 'other', exact: true }).click();
  await expect(ui.locator('#messages')).toContainText('Untrusted');
  await page.evaluate(() => window.initial());
  await page.clock.runFor(1000);
  await expect(ui.locator('#message-title')).toHaveText('Thread with other');
  await noSideEffects(page);
});
for (const failure of ['error', 'cancelled']) test(`initial ${failure} remains a safe list with recovery`, async ({ page }) => {
  const ui = await open(page, { holdInitial: true });
  await expect(ui.locator('#entrypoint-status')).toContainText('Waiting');
  await page.evaluate(failure => window.notify(failure === 'error' ? 'ui/notifications/tool-result' : 'ui/notifications/tool-cancelled', failure === 'error' ? { content: [], isError: true } : {}), failure);
  await expect(ui.locator('#entrypoint-status')).toContainText('failed');
  await expect(ui.locator('#mesh-status')).toContainText('2 threads returned');
  await expect(ui.locator('textarea')).toHaveCount(0);
  await noSideEffects(page);
});

test('already fullscreen host needs no display request', async ({ page }) => {
  const ui = await open(page, { mode: 'fullscreen', unsupported: true });
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect(ui.locator('#messages')).toContainText('Untrusted');
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'ui/request-display-mode'))).toEqual([]);
  await noSideEffects(page);
});

for (const early of [true, false]) test(`inline initial result ${early ? 'before' : 'after'} initialization`, async ({ page }) => {
  const ui = await open(page, { early });
  await expect(ui.locator('#mesh-status')).toContainText('2 threads returned');
  expect(await page.evaluate(() => window.requests.find(r => r.method === 'ui/initialize').params.appCapabilities.availableDisplayModes)).toEqual(['inline', 'fullscreen']);
  await expect(ui.locator('textarea')).toHaveCount(0);
  await expect(ui.locator('#mesh-detail')).toBeHidden();
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'tools/call').map(r => r.params.name))).toEqual(['get_data_catalog', 'list_shares']);
  await noSideEffects(page);
});
for (const width of [320, 1120]) test(`compact inline list and exact-peer shared panel at ${width}`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1100 });
  const ui = await open(page, { holdDisplay: true });
  await expect(ui.locator('#mesh-status')).toContainText('2 threads returned');
  expect(await ui.locator('html').evaluate(e => e.scrollWidth <= e.clientWidth)).toBe(true);
  expect(await ui.locator('body').evaluate(e => parseFloat(getComputedStyle(e).paddingBottom))).toBeLessThan(40);
  if (process.env.INLINE_PREVIEW_DIR) await page.screenshot({ path: `${process.env.INLINE_PREVIEW_DIR}/mesh-inline-${width}.png` });
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.requests.filter(r => r.method === 'ui/request-display-mode').length)).toBe(1);
  await expect(ui.locator('textarea')).toHaveCount(0);
  await expect(ui.locator('#mesh-detail')).toBeHidden();
  await ui.getByRole('button', { name: 'peer', exact: true }).dispatchEvent('click');
  await page.evaluate(() => window.reply(window.requests.find(r => r.method === 'ui/request-display-mode').id, { mode: 'fullscreen' }));
  await expect(ui.locator('#messages')).toContainText('Untrusted peer text');
  await expect(ui.locator('#message-title')).toHaveText('Thread with peer');
  await expect(ui.getByRole('button', { name: 'talk with my agent about this thread', exact: true })).toBeVisible();
  await expect(ui.locator('#suggestion-status')).toHaveText('This host does not support reply suggestions (sampling).');
  await expect(ui.getByRole('button', { name: 'Suggest replies', exact: true })).toBeHidden();
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'ui/request-display-mode').map(r => r.params))).toEqual([{ mode: 'fullscreen' }]);
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'tools/call' && r.params.name === 'get_records').every(r => r.params.arguments.fulcra_userid === 'peer'))).toBe(true);
  if (process.env.INLINE_PREVIEW_DIR) await page.screenshot({ path: `${process.env.INLINE_PREVIEW_DIR}/mesh-inline-panel-${width}.png` });
  await noSideEffects(page);
});
