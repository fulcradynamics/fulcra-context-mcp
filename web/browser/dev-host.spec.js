import { test, expect } from '@playwright/test';
import { build } from 'esbuild';
import { readFile } from 'node:fs/promises';

const app = await readFile(new URL('../../fulcra_mcp/ui/contacts.html', import.meta.url), 'utf8');
const host = (await build({ entryPoints: [new URL('../dev/host.js', import.meta.url).pathname],
  bundle: true, write: false, format: 'esm' })).outputFiles[0].text;

test('dev host acknowledges opening and confirms sends through the real app', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-10-16T18:00:00Z') });
  await page.route('http://dev.test/**', route => {
    const path = new URL(route.request().url()).pathname;
    return route.fulfill({ contentType: path === '/host.js' ? 'text/javascript' : 'text/html',
      body: path === '/host.js' ? host : path === '/contacts.html' ? app
        : '<iframe id="app" sandbox="allow-scripts" style="width:100%;height:1800px"></iframe><script type="module" src="/host.js"></script>' });
  });
  await page.addInitScript(() => {
    window.sends = [];
    addEventListener('message', ({ data }) => {
      if (data.method === 'tools/call' && data.params.name === 'agent_connection_send') window.sends.push(data.params.arguments);
    });
  });
  await page.goto('http://dev.test/');
  const ui = page.frameLocator('#app');
  await expect(ui.locator('#selection-empty')).toBeVisible();
  await expect(ui.locator('#messages .message-row')).toHaveCount(0);
  expect(await page.evaluate(() => window.sends)).toEqual([]);
  await ui.locator('.thread-button').filter({ hasText: 'Bob' }).click();
  await expect(ui.locator('#messages')).toContainText('Yes, received.');
  await expect(ui.locator('#send-status')).toHaveText('');
  await ui.locator('.thread-button').filter({ hasText: 'Alice' }).click();
  await expect(ui.locator('#message-title')).toHaveText('Alice');
  await page.clock.runFor(11000);
  await expect(ui.locator('.thread-row').filter({ hasText: 'Bob' }).locator('.unread-dot')).toBeHidden();
  await ui.locator('.thread-button').filter({ hasText: 'Bob' }).click();
  await expect(ui.locator('#messages')).toContainText('Yes, received.');
  expect(await page.evaluate(() => window.sends.map(args => args.kind))).toEqual(['ack']);
  await ui.locator('.composer-input').fill('Synthetic reply');
  await ui.locator('.send-to-peer').click();
  await expect(ui.locator('#send-status')).toContainText('Posted to your outbox');
  await page.clock.runFor(11000);
  await expect(ui.locator('#messages')).toContainText('Synthetic reply');
  await ui.locator('.thread-button').filter({ hasText: 'Alice' }).click();
  await expect(ui.locator('#message-title')).toHaveText('Alice');
  await expect(ui.locator('.thread-row').filter({ hasText: 'Bob' }).locator('.unread-dot')).toBeHidden();
});
