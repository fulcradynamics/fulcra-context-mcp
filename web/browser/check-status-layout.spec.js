import { test, expect } from '@playwright/test';
import { open, readOnlyThread } from './harness.js';

// Validates bottom safe-area clearance (host chrome) and bounded panes across sizes.
for (const [width, height] of [[900,700], [390,600], [320,600]]) {
  test(`message view stays bounded with host-chrome clearance at ${width}x${height}`, async ({page}) => {
    const ui = await open(page, width, {...readOnlyThread, checkStatus:{status:'checked', last_checked:'2026-10-13T11:40:00Z'}});
    await page.locator('iframe').evaluate((el,h) => el.style.height = `${h}px`, height);
    await expect(ui.locator('#messages li')).toHaveCount(6);
    // A schedule exists, so no onboarding card competes for space.
    await expect(ui.locator('#onboarding-thread')).toBeHidden();
    await ui.locator('#message-area').evaluate(el => el.scrollTop = el.scrollHeight);
    const m = await ui.locator('body').evaluate(el => {
      const doc = el.ownerDocument, rect = selector => doc.querySelector(selector).getBoundingClientRect();
      return {overflow:doc.documentElement.scrollHeight > doc.defaultView.innerHeight,
        horizontal:el.scrollWidth > el.clientWidth, railBottom:rect('#connection-list').bottom,
        composerBottom:rect('#thread-composer').bottom, composerTop:rect('#thread-composer').top,
        headerBottom:rect('.contact-header').bottom, areaHeight:rect('#message-area').height,
        lastTop:rect('#messages li:last-child').top, lastBottom:rect('#messages li:last-child').bottom};
    });
    expect(m.overflow).toBe(false);
    expect(m.horizontal).toBe(false);
    expect(m.railBottom).toBe(height);
    // Fullscreen fallback clearance keeps the composer above the host's bottom chrome.
    expect(m.composerBottom).toBe(height - 48);
    expect(m.areaHeight).toBeGreaterThan(100);
    expect(m.lastTop).toBeGreaterThanOrEqual(m.headerBottom);
    expect(m.lastBottom).toBeLessThanOrEqual(m.composerTop);
    await page.screenshot({path:`${process.env.TMPDIR}/contacts-integrated-${width}.png`});
  });
}
