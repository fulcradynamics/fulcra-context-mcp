import { test, expect } from '@playwright/test';
import { open, peer, other } from './harness.js';

test('IDs are private until the keyboard-accessible identity popover opens', async ({ page }) => {
  const ui = await open(page);
  expect(await ui.locator('body').innerText()).not.toContain(peer);
  await ui.getByRole('button', { name: 'Contact information', exact: true }).click();
  const popover = ui.getByRole('dialog', { name: 'Fulcra User ID' });
  await expect(popover.locator('input').nth(1)).toHaveValue(peer);
  await expect(popover.locator('input').nth(2)).toHaveValue(other);
  await popover.getByRole('button', { name: 'Copy ID' }).first().click();
  await expect(popover).toContainText('Select and copy');
  await page.keyboard.press('Escape');
  await expect(popover).toBeHidden();
});

test('handoff guidance is conditional and suppression survives navigation without storage', async ({ page }) => {
  const ui = await open(page);
  await ui.getByRole('button', { name: 'Discuss in synthetic' }).click();
  const guidance = ui.getByRole('dialog', { name: 'Continue in host chat' });
  await expect(guidance.locator('p')).toHaveText('Your request was sent to synthetic. Expand its input to see the conversation and check for a response.');
  await guidance.getByRole('button', { name: "Don't show again" }).click();
  await ui.locator('.thread-button').filter({hasText:'Weekend'}).click();
  await ui.getByRole('button', { name: 'Discuss in synthetic' }).click();
  await expect(guidance).toBeHidden();
  await expect(ui.locator('#send-status')).toContainText('Request accepted');
});

test('sidebar uses explicit unread badges without avatars on narrow screens', async ({ page }) => {
  const ui = await open(page, 390, { listOnly: true });
  await expect(ui.locator('.unread-dot.on')).toHaveText('Unread');
  await expect(ui.locator('.row-avatar').first()).toBeHidden();
  await ui.locator('.thread-button').filter({hasText:'Weekend'}).click();
  await expect(ui.locator('#connection-list')).toBeVisible();
  expect(await ui.locator('body').evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
});

test('empty history gives a readable contact-specific next step', async ({ page }) => {
  const ui = await open(page, 900, {listOnly:true});
  await page.evaluate(() => { window.emptyRecords = true; });
  await ui.locator('.thread-button').filter({hasText:'Weekend'}).click();
  await expect(ui.locator('#message-status')).toContainText('No messages with Weekend');
  await expect(ui.locator('#message-status')).toContainText('Send');
});

test('contact rows and compact header keep status visible', async ({ page }) => {
  const ui = await open(page);
  await expect(ui.locator('.relationship-state').first()).toHaveText('Connected');
  await expect(ui.locator('#contact-assessment')).toBeVisible();
});

test('latest message is not covered by the sticky composer', async ({ page }) => {
  const ui = await open(page, 390, {listOnly:true});
  await page.locator('iframe').evaluate(el => el.style.height = '700px');
  await ui.locator('.thread-button').filter({hasText:'Weekend'}).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  const last = await ui.locator('#messages .message-row').last().boundingBox();
  const composer = await ui.locator('#thread-composer').boundingBox();
  expect(last.y + last.height).toBeLessThanOrEqual(composer.y + 2);
});

for (const [width, height] of [[390, 600], [320, 700], [900, 700]]) {
  test(`ordinary latest message stays between header and composer at ${width}x${height}`, async ({page}) => {
    const ui = await open(page, width, {listOnly:true});
    await page.locator('iframe').evaluate((el, height) => el.style.height = `${height}px`, height);
    await ui.locator('.thread-button').filter({hasText:'Weekend'}).click();
    await expect(ui.locator('#messages .message-row')).toHaveCount(6);
    const visible = async () => {
      const last = await ui.locator('#messages .message-row').last().boundingBox();
      const header = await ui.locator('.contact-header').boundingBox();
      const composer = await ui.locator('#thread-composer').boundingBox();
      expect(last.y).toBeGreaterThanOrEqual(header.y + header.height);
      expect(last.y + last.height).toBeLessThanOrEqual(composer.y + 2);
      expect(await ui.locator('.footer-spacer').evaluate(el => el.offsetHeight)).toBeGreaterThanOrEqual(232);
      expect(await ui.locator('body').evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    };
    await visible();
    await ui.locator('.composer-input').fill('A draft\nwith several\nlines to expand\nthe input');
    await visible();
    await ui.locator('#message-title').click();
    await page.evaluate(() => window.ownRecords.push({id:'latest-poll', kind:'message', sender:'Me', body:'A new message', start_time:'2026-10-13T12:01:00Z'}));
    await page.clock.runFor(11000);
    await expect(ui.locator('#messages')).toContainText('A new message');
    await visible();
  });
}

test('long rail keeps Invite and first contact reachable at document bottom', async ({ page }) => {
  const ui = await open(page, 390, {listOnly:true});
  await page.locator('iframe').evaluate(el => el.style.height = '600px');
  await ui.locator('.thread-button').filter({hasText:'Weekend'}).click();
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await ui.locator('#connections').evaluate(el => {
    // DOM-only long-rail stress, not discovery coverage.
    for (let i = 0; i < 8; i++) el.append(el.firstElementChild.cloneNode(true));
    el.ownerDocument.querySelector('#context-status').textContent = 'Context updated';
    el.ownerDocument.defaultView.scrollTo(0, el.ownerDocument.documentElement.scrollHeight);
  });
  await ui.locator('#connection-list').evaluate(el => el.scrollTop = 0);
  const bounds = await ui.locator('#connection-list').boundingBox();
  expect(bounds.y).toBeGreaterThanOrEqual(8);
  const invite = await ui.locator('#invite').boundingBox();
  const first = await ui.locator('.thread-button').first().boundingBox();
  expect(invite.y).toBeGreaterThanOrEqual(bounds.y);
  expect(first.y + first.height).toBeLessThanOrEqual(bounds.y + bounds.height);
});

test('composer reserves host overlay clearance below history', async ({ page }) => {
  const ui = await open(page);
  expect(await ui.locator('.footer-spacer').evaluate(el => el.getBoundingClientRect().height)).toBeGreaterThanOrEqual(232);
  expect(await ui.locator('#thread-composer').evaluate(el => getComputedStyle(el).top)).toBe('auto');
});

test('uncertain host delivery is not retried across navigation', async ({ page }) => {
  const ui = await open(page);
  await page.evaluate(() => { window.holdMessages = true; });
  await ui.getByRole('button', {name:'Discuss in synthetic'}).click();
  await expect.poll(() => page.evaluate(() => window.hostMessages.length)).toBe(1);
  await page.clock.runFor(16000);
  await expect(ui.locator('#send-status')).toContainText('Could not confirm delivery');
  await expect(ui.getByRole('button', {name:'Discuss in synthetic'})).toBeDisabled();
  await ui.locator('.thread-button').filter({hasText:'Weekend'}).click();
  await expect(ui.getByRole('button', {name:'Discuss in synthetic'})).toBeDisabled();
  await expect(ui.locator('#host-guidance')).toHaveCount(0);
  expect(await page.evaluate(() => window.hostMessages.length)).toBe(1);
});

test('copy indicates success only after the clipboard resolves and closes outside', async ({ page }) => {
  const ui = await open(page);
  await ui.locator('body').evaluate(el => {
    Object.defineProperty(el.ownerDocument.defaultView.navigator, 'clipboard', {configurable:true, value:{writeText: text => new Promise(resolve => { el.ownerDocument.defaultView.copiedID = text; el.ownerDocument.defaultView.finishCopy = resolve; })}});
  });
  await ui.getByRole('button', {name:'Contact information',exact:true}).click();
  const dialog = ui.getByRole('dialog', {name:'Fulcra User ID'});
  await dialog.getByRole('button', {name:'Copy ID'}).nth(1).click();
  await expect(dialog.getByRole('button', {name:'Copied',exact:true})).toHaveCount(0);
  expect(await ui.locator('body').evaluate(el => el.ownerDocument.defaultView.copiedID)).toBe(peer);
  await ui.locator('body').evaluate(el => el.ownerDocument.defaultView.finishCopy());
  await expect(dialog.getByRole('button', {name:'Copied',exact:true})).toHaveText('✓');
  await ui.locator('#message-title').click();
  await expect(dialog).toBeHidden();
});

for (const width of [320, 900]) {
  test(`copy icon trails its ID on the same row at ${width}`, async ({page}) => {
    const ui = await open(page, width);
    await ui.getByRole('button', {name:'Contact information',exact:true}).click();
    const dialog = ui.getByRole('dialog', {name:'Fulcra User ID'});
    const input = await dialog.locator('input').first().boundingBox();
    const copy = await dialog.locator('button').first().boundingBox();
    expect(copy.x).toBeGreaterThanOrEqual(input.x + input.width);
    expect(Math.abs(copy.y + copy.height / 2 - input.y - input.height / 2)).toBeLessThan(2);
  });
}

test('repeat copy clears success while pending, on failure, and fences reopened attempts', async ({page}) => {
  const ui = await open(page);
  await ui.locator('body').evaluate(el => {
    const win = el.ownerDocument.defaultView;
    win.copies = [];
    Object.defineProperty(win.navigator, 'clipboard', {configurable:true, value:{writeText: () => new Promise((resolve,reject) => win.copies.push({resolve,reject}))}});
  });
  const info = ui.getByRole('button', {name:'Contact information',exact:true});
  await info.click();
  const dialog = ui.getByRole('dialog', {name:'Fulcra User ID'});
  const copy = dialog.locator('button').first();
  await copy.click();
  await ui.locator('body').evaluate(el => el.ownerDocument.defaultView.copies[0].resolve());
  await expect(copy).toHaveAttribute('aria-label','Copied');
  await copy.click();
  await expect(copy).toHaveAttribute('aria-label','Copy ID');
  await expect(copy).not.toHaveClass(/copy-success/);
  await ui.locator('body').evaluate(el => el.ownerDocument.defaultView.copies[1].reject(new Error('denied')));
  await expect(dialog).toContainText('Select and copy');
  await expect(copy).toHaveText('⧉');
  await expect(copy).toHaveAttribute('aria-label','Copy ID');
  await copy.click();
  await page.keyboard.press('Escape');
  await info.click();
  await copy.click();
  await ui.locator('body').evaluate(el => el.ownerDocument.defaultView.copies[2].resolve());
  await expect(copy).toHaveAttribute('aria-label','Copy ID');
  await ui.locator('body').evaluate(el => el.ownerDocument.defaultView.copies[3].resolve());
  await expect(copy).toHaveAttribute('aria-label','Copied');
});

test('rejected handoffs and direct sends do not show host guidance', async ({ page }) => {
  const ui = await open(page);
  await ui.locator('.composer-input').fill('Direct message');
  await ui.getByRole('button', {name:'Send',exact:true}).click();
  await expect(ui.locator('#send-status')).toContainText('Message not posted');
  await expect(ui.locator('#host-guidance')).toHaveCount(0);
  await page.evaluate(() => { window.rejectMessages = true; });
  await ui.getByRole('button', {name:'Discuss in synthetic'}).click();
  await expect(ui.locator('#send-status')).toContainText('Host rejected');
  await expect(ui.locator('.composer-input')).toHaveValue('Direct message');
  await expect(ui.locator('#host-guidance')).toHaveCount(0);
  await expect(ui.getByRole('button', {name:'Discuss in synthetic'})).toBeEnabled();
});

test('guidance stores only a preference when storage is available; OK does not suppress', async ({ page }) => {
  const ui = await open(page);
  await ui.locator('body').evaluate(el => {
    const data = new Map(); const win = el.ownerDocument.defaultView;
    win.preferenceWrites = [];
    Object.defineProperty(win, 'localStorage', {value:{getItem: key => data.get(key), setItem: (key,value) => { data.set(key,value); win.preferenceWrites.push([key,value]); }}});
  });
  const discuss = ui.getByRole('button', {name:'Discuss in synthetic'});
  await discuss.click();
  await ui.getByRole('button', {name:'OK',exact:true}).click();
  await discuss.click();
  await ui.getByRole('button', {name:"Don't show again"}).click();
  expect(await ui.locator('body').evaluate(el => el.ownerDocument.defaultView.preferenceWrites)).toEqual([['fulcra.contacts.hide-host-guidance','1']]);
  await discuss.click();
  await expect(ui.locator('#host-guidance')).toHaveCount(0);
});

test('user IDs in generated recipient headings remain private', async ({ page }) => {
  const ui = await open(page, 900, {listOnly:true, ownRecords:[{id:'outgoing-test',kind:'message',sender:peer,recipients:[other],body:'Ordinary message',start_time:'2026-10-13T11:30:00Z'}]});
  await ui.locator('.thread-button').filter({hasText:'Weekend'}).click();
  await expect(ui.locator('#messages')).toContainText('Ordinary message');
  expect(await ui.locator('#messages').innerText()).not.toContain(other);
});

test('an ID-valued contact label never becomes the visible name', async ({ page }) => {
  const ui = await open(page, 900, {listOnly:true});
  await page.evaluate(() => { window.unnamed = true; window.audience = [window.audience[0]]; });
  await page.clock.runFor(11000);
  const row = ui.locator('#connections .thread-button');
  await expect(row.locator('.thread-name')).toHaveText('Unnamed contact');
  await row.click();
  await expect(ui.locator('#message-title')).toHaveText('Unnamed contact');
  expect(await ui.locator('body').innerText()).not.toContain(peer);
  await ui.getByRole('button', {name:'Contact information',exact:true}).click();
  await expect(ui.getByRole('dialog', {name:'Fulcra User ID'}).locator('input')).toHaveValue(peer);
});

test('contacts stay selectable beside the thread and composer follows history', async ({ page }) => {
  const ui = await open(page);
  await expect(ui.locator('#connection-list')).toBeVisible();
  await expect(ui.locator('.thread-button[aria-current="true"]')).toContainText('Weekend');
  expect(await ui.locator('#thread-composer').evaluate(el => !!(el.previousElementSibling?.id === 'message-area'))).toBe(true);
});
