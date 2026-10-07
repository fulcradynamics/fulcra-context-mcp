import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

const html = await readFile(new URL('../fulcra_mcp/ui/hello.html', import.meta.url), 'utf8');

for (const scenario of [
  { name: 'empty', result: { content: [{ type: 'text', text: 'Available data types, grouped by compatible tool: {}' }] }, expected: '0 mesh outboxes' },
  { name: 'populated', result: { content: [{ type: 'text', text: 'Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': [{ id: 'MomentAnnotation/00000000-0000-0000-0000-000000000001', name: 'Mesh Outbox <b>Peer</b>' }] }) }] }, expected: '1 mesh outbox' },
  { name: 'error', result: { isError: true, content: [{ type: 'text', text: 'Access denied' }] }, expected: 'Could not load' },
]) {
test(`real SDK loads meshes (${scenario.name}) on open; invitation still works`, async ({ page }) => {
  await page.setContent('<iframe title="AICQ" sandbox="allow-scripts"></iframe>');
  await page.evaluate((html) => {
    window.requests = [];
    window.rejectMessage = false;
    const frame = document.querySelector('iframe');
    window.addEventListener('message', (event) => {
      if (event.source !== frame.contentWindow) return;
      const message = event.data;
      window.requests.push(message);
      let result;
      if (message.method === 'ui/initialize') {
        result = { protocolVersion: '2026-01-26', hostInfo: { name: 'test', version: '1' },
          hostCapabilities: { message: { text: {} } }, hostContext: { displayMode: 'fullscreen' } };
      } else if (message.method === 'ui/message') {
        result = window.rejectMessage ? { isError: true } : {};
      } else return;
      event.source.postMessage({ jsonrpc: '2.0', id: message.id, result }, '*');
    });
    frame.srcdoc = html;
  }, html);
  const ui = page.frameLocator('iframe');
  const button = ui.getByRole('button', { name: 'Invite someone' });
  await expect(button).toBeEnabled();
  await expect(ui.locator('#mesh-status')).toContainText('Loading mesh outboxes');
  await expect.poll(() => page.evaluate(() => window.requests.filter(r => r.method === 'tools/call').length)).toBe(1);
  await page.evaluate((result) => {
    const request = window.requests.find(r => r.method === 'tools/call');
    document.querySelector('iframe').contentWindow.postMessage({ jsonrpc: '2.0', id: request.id, result }, '*');
  }, scenario.result);
  await expect(ui.locator('#mesh-status')).toContainText(scenario.expected);
  if (scenario.name === 'populated') {
    await expect(ui.locator('#meshes li')).toHaveText(/Mesh Outbox <b>Peer<\/b>/);
    await expect(ui.locator('#meshes b')).toHaveCount(0);
  }
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'ui/message'))).toHaveLength(0);
  await button.click();
  await expect(ui.locator('#status')).toContainText('Request sent');
  const messages = await page.evaluate(() => window.requests.filter(r => r.method === 'ui/message'));
  expect(messages).toHaveLength(1);
  expect(messages[0].params.role).toBe('user');
  expect(messages[0].params.content[0].text).toContain('fulcra-mesh');
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'tools/call'))).toHaveLength(1);
  await page.evaluate(() => { window.rejectMessage = true; });
  await button.click();
  await expect(ui.locator('#status')).toContainText('Could not send');
  await expect(button).toBeEnabled();
});
}
