import { test, expect } from '@playwright/test';
import { open, readOnlyThread } from './harness.js';

for (const [width, height] of [[900,700], [390,600], [320,600]]) {
  test(`check status preserves bounded panes and read-only selection at ${width}x${height}`, async ({page}) => {
    const ui = await open(page, width, {...readOnlyThread, checkStatus:{status:'not_set_up'}});
    await page.locator('iframe').evaluate((el,h) => el.style.height = `${h}px`, height);
    await expect(ui.locator('#messages li')).toHaveCount(6);
    await expect(ui.getByRole('button', {name:'Start Checking'})).toBeVisible();
    const measure = () => ui.locator('body').evaluate(el => {
      const doc = el.ownerDocument, rect = selector => doc.querySelector(selector).getBoundingClientRect();
      return {overflow:doc.documentElement.scrollHeight > doc.defaultView.innerHeight,
        horizontal:el.scrollWidth > el.clientWidth, railBottom:rect('#connection-list').bottom,
        composerBottom:rect('#thread-composer').bottom, composerTop:rect('#thread-composer').top,
        headerBottom:rect('.contact-header').bottom, areaHeight:rect('#message-area').height,
        lastTop:rect('#messages li:last-child').top, lastBottom:rect('#messages li:last-child').bottom};
    });
    const assertLayout = async () => {
      await ui.locator('#message-area').evaluate(el => el.scrollTop = el.scrollHeight);
      const m = await measure();
      expect(m.overflow).toBe(false);
      expect(m.horizontal).toBe(false);
      expect(m.railBottom).toBe(height);
      expect(m.composerBottom).toBe(height - 24);
      expect(m.areaHeight).toBeGreaterThan(100);
      expect(m.lastTop).toBeGreaterThanOrEqual(m.headerBottom);
      expect(m.lastBottom).toBeLessThanOrEqual(m.composerTop);
    };
    await assertLayout();
    await ui.locator('.composer-input').fill('A draft that stays while status changes.');
    await page.evaluate(() => { window.checkStatus = {status:'checked',last_checked:'2026-10-13T11:40:00Z'}; });
    await page.clock.runFor(61000);
    await expect(ui.getByRole('button', {name:'Check Now', exact:true})).toBeVisible();
    await expect(ui.locator('#message-title')).toHaveText('Weekend');
    await expect(ui.locator('.composer-input')).toHaveValue('A draft that stays while status changes.');
    expect(await page.evaluate(() => window.calls.filter(c => !['get_data_catalog','list_shares','get_records','match_agent_invitations','fulcra_check_status'].includes(c.name)))).toEqual([]);
    expect(await page.evaluate(() => window.hostMessages)).toEqual([]);
    await assertLayout();
    await page.screenshot({path:`${process.env.TMPDIR}/contacts-integrated-${width}.png`});
    await ui.getByRole('button', {name:'Check Now', exact:true}).click();
    await expect(ui.locator('#status')).toContainText('Request sent');
    await assertLayout();
  });
}
