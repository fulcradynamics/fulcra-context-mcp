import { test, expect } from '@playwright/test';
import { open, readOnlyThread } from './harness.js';

for (const [width, height] of [[900, 700], [390, 600], [320, 600]]) {
  test(`debug display preserves explicit selection and pane ownership at ${width}x${height}`, async ({ page }) => {
    const ui = await open(page, width, readOnlyThread);
    await page.locator('iframe').evaluate((el, h) => el.style.height = `${h}px`, height);
    await expect(ui.locator('#messages li')).toHaveCount(6);
    const row = ui.locator('.thread-button[aria-current="true"]');
    await expect(row).toContainText('Weekend');
    await expect(row.locator('.relationship-state')).toBeHidden();
    const nameWidth = (await row.locator('.thread-name').boundingBox()).width;
    await ui.locator('.composer-input').fill('Preserve this draft');
    const before = await page.evaluate(() => ({ calls: calls.length, contexts: contexts.length, messages: hostMessages.length }));
    await ui.locator('#advanced-toggle').click();
    await ui.locator('#debug-preview summary').click();
    await ui.getByLabel('Relationship', { exact: true }).selectOption('pending');
    await ui.getByLabel('Messages', { exact: true }).selectOption('outgoing');
    await ui.getByLabel('Message body', { exact: true }).fill('Display-only sample');
    await ui.getByLabel('Acknowledgement', { exact: true }).selectOption('posted');
    await expect(row.locator('.relationship-state')).toBeVisible();
    await expect(row.locator('.relationship-state')).toHaveText('Pending');
    expect((await row.locator('.thread-name').boundingBox()).width).toBe(nameWidth);
    await expect(ui.locator('#messages .bubble-body')).toHaveText('Display-only sample');
    expect(await page.evaluate(() => ({ calls: calls.length, contexts: contexts.length, messages: hostMessages.length }))).toEqual(before);
    // The last debug control must be reachable within the message scroll pane.
    await ui.getByRole('button', { name: 'Reset to live', exact: true }).scrollIntoViewIfNeeded();
    const resetBounds = await ui.getByRole('button', { name: 'Reset to live', exact: true }).boundingBox();
    const composerBounds = await ui.locator('#thread-composer').boundingBox();
    expect(resetBounds.y + resetBounds.height).toBeLessThanOrEqual(composerBounds.y);
    await ui.locator('#advanced-toggle').click();
    await page.clock.runFor(11000);
    await expect(row).toContainText('Weekend');
    await expect(ui.locator('.composer-input')).toHaveValue('Preserve this draft');
    await expect(ui.locator('#messages .bubble-body')).toHaveText('Display-only sample');
    await ui.locator('#message-area').evaluate(el => el.scrollTop = el.scrollHeight);
    const bounds = await ui.locator('body').evaluate(el => {
      const doc = el.ownerDocument, rect = s => doc.querySelector(s).getBoundingClientRect();
      return { horizontal: el.scrollWidth > el.clientWidth,
        documentOverflow: doc.documentElement.scrollHeight > doc.defaultView.innerHeight,
        railBottom: rect('#connection-list').bottom, composerBottom: rect('#thread-composer').bottom,
        composerTop: rect('#thread-composer').top, messageBottom: rect('#messages li:last-child').bottom };
    });
    expect(bounds.horizontal).toBe(false);
    expect(bounds.documentOverflow).toBe(false);
    expect(bounds.railBottom).toBe(height);
    expect(Math.abs(bounds.composerBottom - height / 2)).toBeLessThan(1);
    expect(bounds.messageBottom).toBeLessThanOrEqual(bounds.composerTop);
    await page.screenshot({ path: `${process.env.TMPDIR}/plat808-debug-${width}.png` });
    await ui.locator('#advanced-toggle').click();
    await ui.getByRole('button', { name: 'Reset to live', exact: true }).click();
    await expect(ui.locator('#messages li')).toHaveCount(6);
    await expect(row.locator('.relationship-state')).toBeHidden();
    await expect(ui.locator('#debug-preview-active')).toBeHidden();
    await expect(ui.locator('.composer-input')).toHaveValue('Preserve this draft');
    expect(await page.evaluate(() => calls.filter(c => !['get_data_catalog', 'list_shares', 'get_records', 'match_agent_invitations', 'get_message_check_status'].includes(c.name)))).toEqual([]);
    expect(await page.evaluate(() => hostMessages)).toEqual([]);
  });
}
