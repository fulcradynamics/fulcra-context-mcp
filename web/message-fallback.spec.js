import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { build } from 'esbuild';

// Exercise the renderer boundary directly: discovery currently requires names,
// but a missing source label must never fall back to a guessed name or an ID.
const html = await readFile(new URL('./index.html', import.meta.url), 'utf8');
const { outputFiles } = await build({ entryPoints: [new URL('./messages.js', import.meta.url).pathname], bundle: true, write: false, format: 'iife', globalName: 'messageUI' });
for (const name of [undefined, '', '  ', 42]) test(`missing catalog label (${JSON.stringify(name)}) has a truthful fallback`, async ({ page }) => {
  await page.setContent(html);
  await page.addScriptTag({ content: outputFiles[0].text });
  await page.evaluate(async name => {
    const source = { id: 'MomentAnnotation/exact-type', fulcra_userid: 'exact-peer', direction: 'Incoming', name };
    const thread = { peer: 'exact-peer', sources: [source], warnings: [] };
    const app = {
      getHostCapabilities: () => ({}),
      callServerTool: async () => ({ structuredContent: { result: `Records for ${source.id} from start to end: ${JSON.stringify([{ recorded_at: 'invalid', note: '  raw note\nkind: leave this alone  ' }])}` } }),
    };
    const view = window.messageUI.setupMessages(app, document, () => {});
    view.select(thread);
    await view.refresh({ threads: [thread] });
  }, name);
  await expect(page.locator('#messages li > p').first()).toHaveText('Incoming (Catalog name unavailable)');
  await expect(page.locator('.message-date')).toHaveText('Timestamp unavailable');
  expect(await page.locator('#messages pre').textContent()).toBe('Unrecognized mesh envelope — raw note:\n  raw note\nkind: leave this alone  ');
  await expect(page.locator('#thread-context')).toContainText('exact-peer');
  await expect(page.locator('#thread-context')).toContainText('MomentAnnotation/exact-type');
});
