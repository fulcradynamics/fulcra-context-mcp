import { test, expect } from '@playwright/test';
import { readFile, mkdir } from 'node:fs/promises';
const bundle = await readFile(new URL('../fulcra_mcp/ui/mesh.html', import.meta.url), 'utf8');
const peer = 'a1234567-1234-4234-8234-123456789abc';
const other = 'b1234567-1234-4234-8234-123456789abc';
const screenshots = process.env.PLAT670_SCREENSHOTS;

for (const presentation of ['global', 'thread', 'threads', 'direct']) for (const width of [320, 1120]) {
  test(`identifier list/detail in ${presentation} at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.setContent('<style>body{margin:0}iframe{width:100%;height:900px;border:0}</style><iframe sandbox="allow-scripts"></iframe>');
    await page.evaluate(({ bundle, presentation, peer, other }) => {
      const frame = document.querySelector('iframe');
      const mode = presentation === 'threads' || presentation === 'direct' ? 'threads' : presentation;
      window.requests = [];
      const reply = (id, result) => frame.contentWindow.postMessage({ jsonrpc: '2.0', id, result }, '*');
      addEventListener('message', ({ data: r, source }) => {
        if (source !== frame.contentWindow) return;
        window.requests.push(r);
        if (r.method === 'ui/initialize') reply(r.id, { protocolVersion: '2026-01-26', hostInfo: { name: 'synthetic', version: '1' }, hostContext: { displayMode: mode === 'threads' ? 'inline' : 'fullscreen', availableDisplayModes: ['inline', 'fullscreen'] }, hostCapabilities: { message: { text: {} }, updateModelContext: { text: {} } } });
        if (r.method === 'ui/notifications/initialized' && presentation !== 'direct') frame.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: { content: [], structuredContent: { presentation: mode } } }, '*');
        if (r.method === 'ui/request-display-mode') reply(r.id, { mode: 'fullscreen' });
        if (r.method === 'tools/call') {
          const { name, arguments: args } = r.params;
          const entry = (id, owner, label) => ({ id: `MomentAnnotation/${id}`, fulcra_userid: owner, name: 'Mesh Outbox — unchanged catalog name', description: label ? `Original prose [mesh_identifier: ${JSON.stringify(label)}]` : 'No marker' });
          const text = name === 'get_data_catalog' ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': [entry('own', 'me', 'Summer travel'), entry('in', peer, 'Different incoming label'), entry('in', other, 'Summer travel'), entry('fallback', 'c1234567-1234-4234-8234-123456789abc')] })
            : name === 'list_shares' ? 'Shares: ' + JSON.stringify({ own_fulcra_userid: 'me', outgoing: [{ share_all_data: false, data_types: ['MomentAnnotation/own'], with_user_ids: [peer] }], incoming: [{ sharing_fulcra_userid: peer, sharing_fulcra_user_name: 'Alex (account owner)' }] })
            : `Records for ${args.data_type} from start to end: ` + JSON.stringify([{ id: 'message', recorded_at: new Date().toISOString(), note: JSON.stringify({ v: 1, body: 'Shall we compare the travel options tomorrow?' }) }]);
          reply(r.id, { content: [{ type: 'text', text }] });
        }
      });
      frame.srcdoc = bundle.replace('<meta name="mesh-presentation" content="global">', `<meta name="mesh-presentation" content="${mode}">`);
      if (presentation === 'direct') frame.srcdoc = frame.srcdoc.replace('</head>', '<meta name="mesh-startup" content="resource"></head>');
    }, { bundle, presentation, peer, other });
    const ui = page.frameLocator('iframe');
    await expect(ui.locator('#meshes li')).toHaveCount(3);
    await expect(ui.getByRole('button', { name: `Summer travel (${other})`, exact: true })).toBeVisible();
    await expect(ui.getByRole('button', { name: 'c1234567-1234-4234-8234-123456789abc', exact: true })).toBeVisible();
    const shot = async stage => {
      if (screenshots) { await mkdir(screenshots, { recursive: true }); await page.screenshot({ path: `${screenshots}/${presentation}-${width}-${stage}.png`, fullPage: true }); }
      expect(await ui.locator('html').evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    };
    const named = ui.getByRole('button', { name: `Summer travel (${peer})`, exact: true });
    await expect(named.locator('.identity-secondary')).toHaveText(` (${peer})`);
    const style = await named.locator('.identity-secondary').evaluate(el => ({
      size: parseFloat(getComputedStyle(el).fontSize),
      parentSize: parseFloat(getComputedStyle(el.parentElement).fontSize),
      color: getComputedStyle(el).color,
      parentColor: getComputedStyle(el.parentElement).color,
    }));
    expect(style.size).toBeLessThan(style.parentSize);
    expect(style.color).not.toBe(style.parentColor);
    await expect(ui.getByRole('button', { name: 'c1234567-1234-4234-8234-123456789abc', exact: true }).locator('.identity-secondary')).toBeHidden();
    await shot('list');
    await ui.getByRole('button', { name: `Summer travel (${peer})`, exact: true }).click();
    await expect(ui.locator('#message-title')).toHaveText(`Thread with Summer travel (${peer}) — Account: Alex (account owner)`);
    await expect(ui.locator('#messages li')).toHaveCount(2);
    await expect(ui.locator('#messages')).toContainText('Mesh Outbox — unchanged catalog name');
    await expect(ui.locator('#message-title .identity-secondary')).toHaveText(` (${peer})`);
    await expect(ui.locator('#thread-composer > label .identity-secondary')).toHaveText(` (${peer})`);
    await ui.getByText('Delivery address', { exact: true }).click();
    await expect(ui.locator('#thread-composer details select option:checked')).toHaveText('Mesh Outbox — unchanged catalog name');
    await expect(ui.locator('.outbox-id')).toHaveText('MomentAnnotation/own');
    await shot('detail');
    await ui.locator('#message-back').click();
    const fallback = 'c1234567-1234-4234-8234-123456789abc';
    await ui.getByRole('button', { name: fallback, exact: true }).click();
    await expect(ui.locator('#message-title')).toHaveText(`Thread with ${fallback}`);
    await expect(ui.locator('#message-title .identity-secondary')).toBeHidden();
    await expect(ui.locator('#thread-composer > label .identity-secondary')).toBeHidden();
    await shot('fallback');
    const calls = await page.evaluate(() => window.requests.filter(r => r.method === 'tools/call').map(r => r.params));
    expect(calls.every(c => ['get_data_catalog', 'list_shares', 'get_records'].includes(c.name))).toBe(true);
    expect(calls.filter(c => c.name === 'get_records').every(c => ['MomentAnnotation/own', 'MomentAnnotation/in', 'MomentAnnotation/fallback'].includes(c.arguments.data_type))).toBe(true);
    expect(await page.evaluate(() => window.requests.filter(r => ['ui/message', 'sampling/createMessage'].includes(r.method)))).toEqual([]);
  });
}
