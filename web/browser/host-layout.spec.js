import { test, expect } from '@playwright/test';
import { open, readOnlyThread } from './harness.js';

test('SDK size notifications converge when the host follows them after resize', async ({page}) => {
  const ui = await open(page,900,readOnlyThread);
  await expect(ui.locator('#messages li')).toHaveCount(6);
  await page.clock.runFor(100);
  await page.evaluate(() => { window.sizes=[]; window.followSize=true; document.querySelector('iframe').style.height='600px'; });
  await page.clock.runFor(100);
  await expect.poll(async () => {
    await page.clock.runFor(100);
    return page.evaluate(()=>window.sizes.at(-1)?.height);
  }).toBe(600);
  await ui.locator('#advanced-toggle').click();
  await ui.locator('#advanced-panel details').last().evaluate(el=>el.open=true);
  await page.clock.runFor(1000);
  expect(await page.locator('iframe').evaluate(el=>el.clientHeight)).toBe(600);
  expect(await page.evaluate(()=>window.sizes.every(s=>s.height===600))).toBe(true);
  expect(await ui.locator('html').evaluate(el=>el.scrollHeight===el.clientHeight)).toBe(true);
  await ui.locator('#message-area').evaluate(el=>el.scrollTop=el.scrollHeight);
  const last = await ui.locator('#messages li').last().boundingBox();
  const composer = await ui.locator('#thread-composer').boundingBox();
  expect(last.y+last.height).toBeLessThanOrEqual(composer.y);
});

test('motion, contrast and transparency preferences preserve readable disclosure', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce',contrast:'more'});
  const ui = await open(page,390,readOnlyThread);
  await ui.locator('.identity-info').hover();
  await expect(ui.locator('#contact-identity')).toHaveCSS('backdrop-filter','none');
  await expect(ui.locator('#contact-identity')).toHaveCSS('border-top-color','rgb(255, 255, 255)');
  await expect(ui.locator('.thread-row').first()).toHaveCSS('animation-name','none');
  await page.emulateMedia({contrast:'no-preference'});
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-transparency',value:'reduce'}]});
  await expect(ui.locator('#contact-identity')).toHaveCSS('backdrop-filter','none');
  await expect(ui.locator('#contact-identity')).toHaveCSS('background-color','rgb(34, 34, 39)');
});
