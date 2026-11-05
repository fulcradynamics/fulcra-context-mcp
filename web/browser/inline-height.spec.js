import { test, expect } from '@playwright/test';
import { open, readOnlyThread } from './harness.js';

// Claude shows the app inline and sizes the frame from the reported height.
const followFrom = async (page, height) => {
  await page.evaluate(h => { window.sizes=[]; window.followSize=true; document.querySelector('iframe').style.height=`${h}px`; }, height);
  await expect.poll(async () => {
    await page.clock.runFor(100);
    return page.locator('iframe').evaluate(el => el.clientHeight);
  }).toBe(640);
};

test('inline hosts without fullscreen grow the frame to the inline height', async ({page}) => {
  const ui = await open(page, 900, {...readOnlyThread, displayMode: 'inline'});
  await expect(ui.locator('html')).toHaveAttribute('data-display-mode', 'inline');
  await expect(ui.locator('#messages li')).toHaveCount(6);
  await followFrom(page, 300);
  expect(await page.evaluate(() => window.displayRequests)).toEqual([]);
  await expect(ui.locator('#thread-composer')).toBeInViewport();
});

test('inline hosts offering fullscreen are asked for it once', async ({page}) => {
  const ui = await open(page, 900, {...readOnlyThread, displayMode: 'inline', availableDisplayModes: ['inline', 'fullscreen']});
  await expect.poll(() => page.evaluate(() => window.displayRequests)).toEqual(['fullscreen']);
  await expect(ui.locator('html')).toHaveAttribute('data-display-mode', 'fullscreen');
});

test('fullscreen hosts are never asked to change mode', async ({page}) => {
  const ui = await open(page, 900, {...readOnlyThread, availableDisplayModes: ['inline', 'fullscreen']});
  await expect(ui.locator('#messages li')).toHaveCount(6);
  await page.clock.runFor(500);
  expect(await page.evaluate(() => window.displayRequests)).toEqual([]);
});

const hostContextChanged = (page, params) => page.evaluate(params => document.querySelector('iframe').contentWindow
  .postMessage({jsonrpc:'2.0',method:'ui/notifications/host-context-changed',params}, '*'), params);

test('closing fullscreen shows Expand, which asks for fullscreen again', async ({page}) => {
  const ui = await open(page, 900, {...readOnlyThread, displayMode: 'inline', availableDisplayModes: ['inline', 'fullscreen']});
  await expect.poll(() => page.evaluate(() => window.displayRequests)).toEqual(['fullscreen']);
  await expect(ui.locator('#expand')).toBeHidden();
  await hostContextChanged(page, {displayMode: 'inline'});
  await expect(ui.locator('html')).toHaveAttribute('data-display-mode', 'inline');
  await expect(ui.getByRole('button', {name: 'Expand', exact: true})).toBeVisible();
  await hostContextChanged(page, {theme: 'dark'});
  await expect(ui.locator('#expand')).toBeVisible();
  await ui.locator('#expand').click();
  await expect.poll(() => page.evaluate(() => window.displayRequests)).toEqual(['fullscreen', 'fullscreen']);
  await expect(ui.locator('#expand')).toBeHidden();
});

test('Expand stays hidden without a fullscreen mode to offer', async ({page}) => {
  const ui = await open(page, 900, {...readOnlyThread, displayMode: 'inline'});
  await expect(ui.locator('#messages li')).toHaveCount(6);
  await expect(ui.locator('#expand')).toBeHidden();
  const full = await open(page, 900, readOnlyThread);
  await expect(full.locator('#messages li')).toHaveCount(6);
  await expect(full.locator('#expand')).toBeHidden();
});
