import { test, expect } from '@playwright/test';
import { open } from './harness.js';

for (const [width, height] of [[390,600], [320,700], [900,700]]) {
  test(`panes own scrolling and pin empty/short composer at ${width}x${height}`, async ({page}) => {
    const ui = await open(page, width, {listOnly:true});
    await expect(ui.locator('#messages .message-row')).toHaveCount(6);
    await page.locator('iframe').evaluate((el,h) => el.style.height = `${h}px`, height);
    const measure = () => ui.locator('body').evaluate(el => {
      const doc = el.ownerDocument, rect = id => doc.querySelector(id).getBoundingClientRect();
      return {height:doc.defaultView.innerHeight, railBottom:rect('#connection-list').bottom,
        composerBottom:rect('#thread-composer').bottom, headerBottom:rect('.contact-header').bottom,
        lastTop:rect('#messages li:last-child').top, lastBottom:rect('#messages li:last-child').bottom,
        composerTop:rect('#thread-composer').top, documentOverflow:doc.documentElement.scrollHeight > doc.defaultView.innerHeight,
        horizontal:el.scrollWidth > el.clientWidth};
    });
    await expect.poll(async () => (await measure()).railBottom).toBe(height);
    let m = await measure();
    expect(m.documentOverflow).toBe(false);
    expect(m.horizontal).toBe(false);
    expect(m.composerBottom).toBe(height - 72);
    await ui.locator('#message-area').evaluate(el => el.scrollTop = el.scrollHeight);
    m = await measure();
    expect(m.lastTop).toBeGreaterThanOrEqual(m.headerBottom);
    expect(m.lastBottom).toBeLessThanOrEqual(m.composerTop);
    await page.evaluate(() => {window.emptyRecords = true;});
    await page.clock.runFor(11000);
    await expect(ui.locator('#messages li')).toHaveCount(0);
    expect(await ui.locator('#thread-composer').evaluate(el => el.getBoundingClientRect().bottom)).toBe(height - 72);
    // Host insets are separate, dynamic, and do not shorten the rail.
    await page.evaluate(() => document.querySelector('iframe').contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/host-context-changed',params:{safeAreaInsets:{top:0,right:12,bottom:20,left:16}}},'*'));
    await expect.poll(() => ui.locator('#thread-composer').evaluate(el => el.getBoundingClientRect().bottom)).toBe(height - 92);
    expect(await ui.locator('#connection-list').evaluate(el => el.getBoundingClientRect().bottom)).toBe(height);
    expect(await ui.locator('main').evaluate(el=>parseFloat(getComputedStyle(el).paddingLeft))).toBe(width <= 520 ? 24 : 40);
  });
}
