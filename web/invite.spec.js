import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

const html = await readFile(new URL('../fulcra_mcp/ui/hello.html', import.meta.url), 'utf8');

test('real SDK handshake and button send a user message, not a tool call', async ({ page }) => {
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
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'ui/message'))).toHaveLength(0);
  await button.click();
  await expect(ui.getByRole('status')).toContainText('Request sent');
  const messages = await page.evaluate(() => window.requests.filter(r => r.method === 'ui/message'));
  expect(messages).toHaveLength(1);
  expect(messages[0].params.role).toBe('user');
  expect(messages[0].params.content[0].text).toContain('fulcra-mesh');
  expect(await page.evaluate(() => window.requests.some(r => r.method === 'tools/call'))).toBe(false);
  await page.evaluate(() => { window.rejectMessage = true; });
  await button.click();
  await expect(ui.getByRole('status')).toContainText('Could not send');
  await expect(button).toBeEnabled();
});
