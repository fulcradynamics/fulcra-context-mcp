import { test, expect } from '@playwright/test';
import { open } from './harness.js';

const palettes = {
  dark: { chrome: 'rgb(18, 19, 24)', canvas: 'rgb(0, 0, 0)', surface: 'rgb(22, 22, 29)', raised: 'rgb(34, 34, 39)', text: 'rgb(255, 255, 255)', muted: 'rgb(138, 138, 142)', accent: 'rgb(86, 214, 183)' },
  light: { chrome: 'rgb(233, 236, 241)', canvas: 'rgb(255, 255, 255)', surface: 'rgb(255, 255, 255)', raised: 'rgb(244, 245, 247)', text: 'rgb(22, 22, 29)', muted: 'rgb(98, 106, 120)', accent: 'rgb(14, 125, 132)' },
};
const changeTheme = (page, theme) => page.evaluate(theme => {
  document.querySelector('iframe').contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/host-context-changed', params: { theme } }, '*');
}, theme);

async function expectPalette(ui, theme) {
  const palette = palettes[theme];
  await expect(ui.locator('html')).toHaveCSS('color-scheme', theme);
  await expect(ui.locator('html')).toHaveCSS('background-color', palette.canvas);
  await expect(ui.locator('h1')).toHaveCSS('color', palette.text);
  await expect(ui.locator('#invite')).toHaveCSS('color', palette.text);
  await expect(ui.locator('#invite')).toHaveCSS('background-color', palette.raised);
  await expect(ui.locator('#invite')).toHaveCSS('border-radius', '9999px');
  await expect(ui.locator('#invite .btn-icon')).toHaveCSS('color', palette.accent);
  await expect(ui.locator('#connection-list')).toHaveCSS('background-color', palette.chrome);
  await expect(ui.locator('.thread-name').first()).toHaveCSS('color', palette.text);
  await expect(ui.locator('.thread-preview').first()).toHaveCSS('color', palette.muted);
  await expect(ui.locator('#thread-composer')).toHaveCSS('background-color', palette.chrome);
  await expect(ui.locator('.composer-input')).toHaveCSS('color', palette.text);
  await expect(ui.locator('.incoming .bubble').first()).toHaveCSS('background-color', palette.raised);
  await expect(ui.locator('.incoming .bubble').first()).toHaveCSS('color', palette.text);
  await expect(ui.locator('.outgoing .bubble')).toHaveCSS('background-color', 'rgb(111, 82, 229)');
  await expect(ui.locator('.outgoing .bubble')).toHaveCSS('color', 'rgb(255, 255, 255)');
  await expect(ui.locator('.artifact-path')).toHaveCSS('color', 'rgb(255, 255, 255)');
}

for (const theme of ['dark', 'light']) test(`host ${theme} theme covers conversation, controls and invitation`, async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const ui = await open(page, 900, { theme, listOnly: true, ownRecords: [{ id: 'file', kind: 'message', sender: 'My agent', body: 'Here is the report.', start_time: '2026-10-13T11:05:00Z', artifacts: [{ path: '/shared/report.txt' }] }] });
  await page.locator('iframe').evaluate(el => el.style.height = '700px');
  await ui.locator('.thread-button').filter({ hasText: 'Weekend' }).click();
  await expectPalette(ui, theme);
  await ui.locator('.composer-input').fill('A draft that survives theme changes');
  await expect(ui.locator('.send-to-peer')).toBeEnabled();
  await expect(ui.locator('.send-to-peer')).toHaveCSS('color', 'rgb(255, 255, 255)');
  await page.screenshot({ path: `${process.env.TMPDIR}/contacts-theme-${theme}.png` });

  await ui.locator('#invite').click();
  const dialog = ui.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveCSS('color', palettes[theme].text);
  await expect(dialog).toHaveCSS('background-color', palettes[theme].surface);
  const field = dialog.locator('input[type=text]').first();
  await field.fill('Sura');
  await expect(field).toHaveCSS('color', palettes[theme].text);
  await expect(field).toHaveCSS('background-color', palettes[theme].raised);
  await page.screenshot({ path: `${process.env.TMPDIR}/contacts-invite-${theme}.png` });

  const other = theme === 'dark' ? 'light' : 'dark';
  await changeTheme(page, other);
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveCSS('color', palettes[other].text);
  await expect(field).toHaveValue('Sura');
  await expect(field).toHaveCSS('background-color', palettes[other].raised);
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expectPalette(ui, other);
  await expect(ui.locator('.composer-input')).toHaveValue('A draft that survives theme changes');
  await changeTheme(page, theme);
  await expectPalette(ui, theme);
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'send_agent_contact_message'))).toHaveLength(0);
});

test('missing host theme defaults to dark regardless of browser preference', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  const ui = await open(page, 900, { listOnly: true, autoSelect: false });
  await expect(ui.locator('html')).toHaveCSS('color-scheme', 'dark');
  await expect(ui.locator('#welcome-title')).toHaveCSS('color', palettes.dark.text);
  await changeTheme(page, 'light');
  await expect(ui.locator('#welcome-title')).toHaveCSS('color', palettes.light.text);
});

for (const theme of ['dark', 'light']) test(`status and error colors follow ${theme} appearance`, async ({ page }) => {
  const ui = await open(page, 900, { theme, listOnly: true, status: { attention: true, reason: 'Please review the report', assessed_at: '2026-10-13T11:00:00Z' } });
  await page.locator('iframe').evaluate(el => el.style.height = '700px');
  const warning = theme === 'light' ? 'rgb(118, 90, 0)' : 'rgb(255, 204, 0)';
  const error = theme === 'light' ? 'rgb(215, 0, 21)' : 'rgb(255, 59, 48)';
  await expect(ui.locator('.status-badge.attention')).toHaveCSS('color', warning);
  await page.evaluate(() => { window.failInvite = true; });
  await ui.locator('#invite').click();
  const dialog = ui.getByRole('dialog');
  const fields = dialog.locator('input[type=text]');
  await fields.nth(0).fill('Sura');
  await fields.nth(1).fill('Alex');
  await dialog.getByRole('button', { name: 'Create invitation' }).click();
  await expect(dialog.locator('.dialog-error')).not.toBeEmpty();
  await expect(dialog.locator('.dialog-error')).toHaveCSS('color', error);
});

for (const theme of ['light', 'dark']) test(`increased contrast retains readable ${theme} text`, async ({ page }) => {
  await page.emulateMedia({ contrast: 'more' });
  const ui = await open(page, 900, { theme, listOnly: true, autoSelect: false });
  await expect(ui.locator('html')).toHaveCSS('color-scheme', theme);
  await expect(ui.locator('.thread-preview').first()).toHaveCSS('color', theme === 'light' ? 'rgb(56, 56, 58)' : 'rgb(197, 197, 204)');
});
