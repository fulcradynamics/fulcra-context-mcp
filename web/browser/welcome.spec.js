import { test, expect } from '@playwright/test';
import { open } from './harness.js';

for (const width of [320, 390, 900]) test(`instructional layout and aligned rail at ${width}`, async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const ui = await open(page, width, { listOnly: true, autoSelect: false });
  await page.locator('iframe').evaluate(el => el.style.height = '700px');
  await page.setViewportSize({ width, height: 720 });
  await expect(ui.locator('.app-intro')).toHaveText('Connect your agent with other people’s agents to share messages and work together. Manage your connections and follow conversations here.');
  await expect(ui.locator('#connections-title')).toHaveText('Agent Chats');
  await ui.locator('#invite-welcome').scrollIntoViewIfNeeded();
  expect(await ui.locator('html').evaluate(el => el.scrollWidth <= el.clientWidth && el.scrollHeight <= el.clientHeight)).toBe(true);
  await page.screenshot({ path: `${process.env.TMPDIR}/contacts-welcome-dark-${width}.png` });
  await page.evaluate(() => document.querySelector('iframe').contentWindow.postMessage({ jsonrpc:'2.0', method:'ui/notifications/host-context-changed', params:{theme:'light'} }, '*'));
  // This app retains its dark palette even when the host reports a light theme.
  await expect(ui.locator('html')).toHaveCSS('color-scheme', 'dark');
  await expect(ui.locator('html')).toHaveCSS('background-color', 'rgb(0, 0, 0)');
  const chatInset = await ui.locator('#connections .thread-button').first().evaluate(el => el.getBoundingClientRect().left + parseFloat(getComputedStyle(el).paddingLeft));
  await page.evaluate(() => { window.excludeOut = true; });
  await page.clock.runFor(11000);
  const pendingInset = await ui.locator('.pending-label').first().evaluate(el => el.getBoundingClientRect().left);
  expect(pendingInset).toBe(chatInset);
  // Exercise the legacy row's production CSS at the same real rail width.
  await ui.locator('#legacy-connections').evaluate(el => {
    el.parentElement.hidden = false;
    el.innerHTML = '<li class="thread-row"><div class="thread-button"><div class="thread-text"><span class="thread-name">Legacy connection</span></div><button class="legacy-convert">Update connection</button></div></li>';
  });
  const name = await ui.locator('#legacy-connections .thread-name').boundingBox();
  const action = await ui.locator('.legacy-convert').boundingBox();
  expect(action.y).toBeGreaterThanOrEqual(name.y + name.height);
  expect(name.width).toBeGreaterThan(75);
  await ui.locator('.legacy-convert').scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${process.env.TMPDIR}/contacts-rail-${width}.png` });
});

test('untargeted launch stays instructional through polls and invites without forms', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, autoSelect: false });
  await expect(ui.locator('#selection-empty')).toBeVisible();
  await expect(ui.locator('#selection-empty h2')).toHaveText('A shared conversation between agents you know.');
  await expect(ui.locator('#connection-detail')).toBeHidden();
  await page.clock.runFor(11000);
  await expect(ui.locator('#selection-empty')).toBeVisible();
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'agent_connection_send'))).toHaveLength(0);
  await ui.locator('#invite-welcome').click();
  await expect(ui.getByRole('dialog')).toBeVisible();
});
