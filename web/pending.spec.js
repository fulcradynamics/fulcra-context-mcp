import { test, expect } from '@playwright/test';
import { readFile, mkdir } from 'node:fs/promises';
const html = await readFile(new URL('../fulcra_mcp/ui/mesh.html', import.meta.url), 'utf8');

async function open(page, width, mixed = false) {
  await page.setViewportSize({ width, height: 900 });
  await page.clock.install({ time: new Date('2026-01-10T12:00:00Z') });
  await page.clock.pauseAt(new Date('2026-01-10T12:00:01Z'));
  await page.setContent('<style>body{margin:0}iframe{width:100%;height:900px;border:0}</style><iframe sandbox="allow-scripts"></iframe>');
  await page.evaluate(({ html, mixed }) => {
    const entry = (id, owner, description) => ({ id: `MomentAnnotation/${id}`, name: 'Mesh Outbox same name', fulcra_userid: owner, description });
    window.entries = [entry('a', 'me', '[mesh_identifier: "<b>Travel</b>"]'), entry('a', 'me', '[mesh_identifier: "<b>Travel</b>"]'), entry('b', 'me'), entry('c', 'me', '[mesh_identifier: invalid]')];
    if (mixed) window.entries.push(entry('a', 'peer', '[mesh_identifier: "<b>Travel</b>"]'));
    window.shares = { own_fulcra_userid: 'me', outgoing: [], incoming: mixed ? [{ sharing_fulcra_userid: 'peer' }] : [] };
    window.requests = [];
    const frame = document.querySelector('iframe');
    const reply = (id, result) => frame.contentWindow.postMessage({ jsonrpc: '2.0', id, result }, '*');
    addEventListener('message', ({ data: r, source }) => {
      if (source !== frame.contentWindow) return;
      window.requests.push(r);
      if (r.method === 'ui/initialize') reply(r.id, { protocolVersion: '2026-01-26', hostInfo: { name: 'fixture', version: '1' }, hostCapabilities: { message: { text: {} }, updateModelContext: { text: {} } }, hostContext: { displayMode: 'fullscreen' } });
      if (r.method === 'tools/call') {
        const { name, arguments: args } = r.params;
        if (window.fail === name) { reply(r.id, { isError: true }); return; }
        const text = name === 'get_data_catalog' ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': window.entries })
          : name === 'list_shares' ? 'Shares: ' + JSON.stringify(window.shares)
          : `Records for ${args.data_type} from start to end: []`;
        reply(r.id, { content: [{ type: 'text', text }] });
      }
    });
    frame.srcdoc = html;
  }, { html, mixed });
  const ui = page.frameLocator('iframe');
  await expect(ui.locator('#mesh-status')).toContainText('threads returned');
  return ui;
}

test('polling reconciles exact pending sources without guessing peers or disrupting selection', async ({ page }) => {
  const ui = await open(page, 1120, true);
  await expect(ui.locator('#pending-meshes li')).toHaveCount(3);
  await ui.locator('#pending-meshes li').first().evaluate(el => { el.marker = true; });
  await page.evaluate(() => { window.entries[1].description = '[mesh_identifier: "Renamed"]'; });
  await page.clock.runFor(10000);
  await expect(ui.locator('#pending-meshes .pending-label').first()).toHaveText('Renamed');
  expect(await ui.locator('#pending-meshes li').first().evaluate(el => el.marker)).toBe(true);
  const peer = ui.getByRole('button', { name: '<b>Travel</b> (peer)', exact: true });
  await peer.evaluate(el => { el.marker = true; });
  await peer.click();
  await expect(ui.locator('#message-status')).toContainText('No messages');
  const draft = ui.locator('#thread-composer textarea');
  await draft.fill('Keep this draft');
  await page.evaluate(() => { window.shares.outgoing = ['a', 'b'].map(id => ({ share_all_data: false, data_types: [`MomentAnnotation/${id}`], with_user_ids: ['peer'] })); });
  await page.clock.runFor(10000);
  await expect(ui.locator('#pending-meshes li')).toHaveCount(1);
  await expect(ui.locator('#mesh-count')).toHaveText('1');
  await expect(ui.locator('#message-title')).toContainText('Renamed (peer)');
  await expect(draft).toHaveValue('Keep this draft');
  await ui.getByRole('button', { name: 'Back to threads' }).click();
  expect(await ui.locator('#meshes button').evaluate(el => el.marker)).toBe(true);
  await expect(ui.locator('#meshes button')).toBeFocused();
  await page.evaluate(() => { window.shares.outgoing.push({ share_all_data: false, data_types: ['MomentAnnotation/c'], with_user_ids: ['peer'] }); });
  await ui.getByRole('button', { name: 'Refresh threads', exact: true }).click();
  await expect(ui.locator('#pending-section')).toBeHidden();
  await expect(ui.locator('#pending-meshes li')).toHaveCount(0);
  await expect(ui.locator('#meshes li')).toHaveCount(1);
  expect(await page.evaluate(() => window.requests.filter(r => ['ui/message', 'sampling/createMessage'].includes(r.method)))).toEqual([]);
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'tools/call').every(r => ['get_data_catalog', 'list_shares', 'get_records'].includes(r.params.name)))).toBe(true);
});

for (const failedTool of ['get_data_catalog', 'list_shares']) test(`failed ${failedTool} retains pending until successful discovery`, async ({ page }) => {
  const ui = await open(page, 320);
  await expect(ui.locator('#pending-meshes li')).toHaveCount(3);
  await page.evaluate(name => { window.fail = name; window.entries = []; }, failedTool);
  await page.clock.runFor(10000);
  await expect(ui.locator('#mesh-status')).toContainText('discovery failed');
  await expect(ui.locator('#pending-meshes li')).toHaveCount(3);
  await page.evaluate(() => { window.fail = undefined; });
  await ui.getByRole('button', { name: 'Refresh threads', exact: true }).click();
  await expect(ui.locator('#pending-section')).toBeHidden();
  await expect(ui.locator('#pending-meshes li')).toHaveCount(0);
});

for (const width of [320, 1120]) for (const mixed of [false, true]) {
  test(`pending ${mixed ? 'mixed' : 'only'} list at ${width}px is read-only`, async ({ page }) => {
    const ui = await open(page, width, mixed);
    await expect(ui.getByRole('heading', { name: 'Pending', exact: true })).toBeVisible();
    await expect(ui.locator('#pending-meshes li')).toHaveCount(3);
    await expect(ui.locator('#pending-meshes .pending-label')).toHaveText(['<b>Travel</b>', 'Mesh Outbox same name', 'Mesh Outbox same name']);
    await expect(ui.locator('#pending-meshes .meta')).toHaveText(['Not shared yet', 'Not shared yet', 'Not shared yet']);
    await expect(ui.locator('#pending-meshes button, #pending-meshes a, #pending-meshes b')).toHaveCount(0);
    await expect(ui.locator('#mesh-count')).toHaveText(mixed ? '1' : '0');
    await expect(ui.locator('#meshes li')).toHaveCount(mixed ? 1 : 0);
    await expect(ui.locator('#mesh-detail')).toBeHidden();
    expect(await ui.locator('html').evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    if (process.env.PENDING_SCREENSHOTS) {
      await mkdir(process.env.PENDING_SCREENSHOTS, { recursive: true });
      await page.screenshot({ path: `${process.env.PENDING_SCREENSHOTS}/pending-${mixed ? 'mixed' : 'only'}-${width}.png`, fullPage: true });
    }
    await page.clock.runFor(10000);
    await expect.poll(() => page.evaluate(() => window.requests.filter(r => r.method === 'tools/call').length)).toBe(4);
    expect(await page.evaluate(() => window.requests.filter(r => r.method === 'tools/call').map(r => r.params.name))).toEqual(['get_data_catalog', 'list_shares', 'get_data_catalog', 'list_shares']);
    expect(await page.evaluate(() => window.requests.filter(r => ['ui/message', 'sampling/createMessage', 'ui/update-model-context'].includes(r.method)))).toEqual([]);
  });
}
