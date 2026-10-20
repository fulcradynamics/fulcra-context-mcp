import { test, expect } from '@playwright/test';
import { open, readOnlyThread } from './harness.js';

for (const [width, height] of [[390,600], [320,700], [900,700]]) {
  test(`panes own scrolling; composer scrolls into its bottom gap at ${width}x${height}`, async ({page}) => {
    const ui = await open(page, width, readOnlyThread);
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
    // The composer scrolls at the end of the conversation, not pinned; scroll to the
    // bottom to bring it into its half-screen gap above the window edge.
    await ui.locator('#message-area').evaluate(el => el.scrollTop = el.scrollHeight);
    const m = await measure();
    expect(m.documentOverflow).toBe(false);
    expect(m.horizontal).toBe(false);
    expect(m.composerBottom).toBe(height / 2);
    expect(m.lastTop).toBeGreaterThanOrEqual(m.headerBottom);
    expect(m.lastBottom).toBeLessThanOrEqual(m.composerTop);
    // Host insets are separate and do not shorten the rail.
    expect(await ui.locator('#connection-list').evaluate(el => el.getBoundingClientRect().bottom)).toBe(height);
    expect(await ui.locator('main').evaluate(el=>parseFloat(getComputedStyle(el).paddingLeft))).toBe(width <= 520 ? 24 : 40);
  });
}
