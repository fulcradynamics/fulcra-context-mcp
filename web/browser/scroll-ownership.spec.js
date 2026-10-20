import { test, expect } from '@playwright/test';
import { open, peer, readOnlyThread } from './harness.js';

for (const width of [320,900]) test(`short iframe keeps an ordinary message visible and independent rail reachability at ${width}`, async ({page}) => {
  const ui = await open(page,width,{listOnly:true,presentation:'thread',launchPeer:peer,direct:true});
  await expect(ui.locator('#messages li')).toHaveCount(3);
  await page.locator('iframe').evaluate(el => el.style.height = '500px');
  await page.clock.runFor(100);
  const visible = async () => {
    const m = await ui.locator('#messages li').last().boundingBox();
    const h = await ui.locator('.contact-header').boundingBox();
    const c = await ui.locator('#thread-composer').boundingBox();
    expect(m.y).toBeGreaterThanOrEqual(h.y+h.height-1);
    expect(m.y+m.height).toBeLessThanOrEqual(c.y);
  };
  await visible();
  if (width === 900) expect(await ui.locator('#connection-list').evaluate(el => el.scrollHeight === el.clientHeight)).toBe(true);
  await ui.locator('.composer-input').fill('One\nTwo\nThree\nFour\nFive');
  await page.clock.runFor(100);
  await visible();
  await ui.locator('#connection-list').evaluate(el => {
    const list = el.querySelector('#connections');
    for (let i=0;i<20;i++) list.append(list.firstElementChild.cloneNode(true));
    el.scrollTop = el.scrollHeight;
  });
  const rail = await ui.locator('#connection-list').boundingBox();
  const last = await ui.locator('#connections li').last().boundingBox();
  expect(last.y+last.height).toBeLessThanOrEqual(rail.y+rail.height-23);
  await ui.locator('#connection-list').evaluate(el => el.scrollTop = 0);
  const invite = await ui.locator('#invite').boundingBox();
  expect(invite.y).toBeGreaterThanOrEqual(rail.y);
  await visible();
  expect(await ui.locator('html').evaluate(el => el.scrollHeight === el.clientHeight && el.scrollWidth === el.clientWidth)).toBe(true);
});

for (const width of [320, 900]) test(`Advanced expansion reveals its beginning and retains reading intent at ${width}`, async ({ page }) => {
  const ownRecords = Array.from({ length: 40 }, (_, i) => ({
    id: `h${i}`, kind: 'message', sender: 'Me', body: `History ${i}`,
    start_time: `2026-10-13T10:${String(i).padStart(2, '0')}:00Z`,
  }));
  const ui = await open(page, width, { ...readOnlyThread, ownRecords });
  await expect(ui.locator('#messages li')).toHaveCount(46);
  await page.locator('iframe').evaluate(el => el.style.height = '600px');
  await page.clock.runFor(100);
  const pane = ui.locator('#message-area');
  expect(await pane.evaluate(el => el.scrollTop)).toBeGreaterThan(1000);
  const latest = await ui.locator('#messages li').last().boundingBox();
  const bounds = await pane.boundingBox();
  expect(latest.y + latest.height).toBeLessThanOrEqual(bounds.y + bounds.height);
  const railScroll = await ui.locator('#connection-list').evaluate(el => el.scrollTop);
  // Delayed scroll delivery must not be needed to cancel latest-edge following.
  await pane.evaluate(el => el.addEventListener('scroll', event => event.stopImmediatePropagation(), { capture: true }));
  await ui.locator('#advanced-toggle').click();
  const beginningVisible = async () => {
    const area = await pane.boundingBox();
    const panel = await ui.locator('#advanced-panel').boundingBox();
    expect(panel.y).toBeGreaterThanOrEqual(area.y);
    expect(panel.y).toBeLessThan(area.y + area.height);
    await expect(ui.locator('#advanced-toggle')).toHaveAttribute('aria-expanded', 'true');
  };
  await beginningVisible();
  await page.locator('iframe').evaluate(el => el.style.height = '650px');
  await page.clock.runFor(100);
  await beginningVisible();
  await page.evaluate(() => window.ownRecords.push({ id: 'new', kind: 'message', sender: 'Me', body: 'New poll message', start_time: '2026-10-13T12:01:00Z' }));
  await page.clock.runFor(11000);
  await expect(ui.locator('#messages')).toContainText('New poll message');
  await beginningVisible();
  expect(await ui.locator('#connection-list').evaluate(el => el.scrollTop)).toBe(railScroll);
  expect(await ui.locator('html').evaluate(el => el.scrollTop === 0 && el.scrollHeight === el.clientHeight)).toBe(true);
  expect(await page.evaluate(() => window.calls.filter(call => call.name === 'agent_connection_send'))).toEqual([]);
  expect(await page.evaluate(() => window.hostMessages)).toEqual([]);
});

test('real pane retains an older reader anchor through polling and new records', async ({page}) => {
  const ownRecords = Array.from({length:30},(_,i)=>({id:`history-${i}`,kind:'message',sender:'Me',body:`Historical message ${i}`,start_time:`2026-10-13T10:${String(i).padStart(2,'0')}:00Z`}));
  const ui = await open(page,900,{...readOnlyThread,ownRecords});
  await expect(ui.locator('#messages li')).toHaveCount(36);
  await page.locator('iframe').evaluate(el => el.style.height = '600px');
  await page.clock.runFor(100);
  await ui.locator('#message-area').evaluate(el => el.scrollTop = 500);
  await page.clock.runFor(100);
  const anchor = ui.locator('#messages li').filter({hasText:'Historical message 8'});
  const before = await anchor.boundingBox();
  const railScroll = await ui.locator('#connection-list').evaluate(el=>el.scrollTop);
  await page.evaluate(() => window.ownRecords.push({id:'new',kind:'message',sender:'Me',body:'New poll message',start_time:'2026-10-13T12:01:00Z'}));
  await page.clock.runFor(11000);
  await expect(ui.locator('#messages')).toContainText('New poll message');
  expect((await anchor.boundingBox()).y).toBe(before.y);
  expect(await ui.locator('#connection-list').evaluate(el=>el.scrollTop)).toBe(railScroll);
  expect(await ui.locator('html').evaluate(el=>el.scrollTop)).toBe(0);
  await ui.locator('#message-area').evaluate(el=>el.scrollTop=0);
  await expect(ui.locator('#message-more')).toBeInViewport();
});
