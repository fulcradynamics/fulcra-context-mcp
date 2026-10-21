import { test, expect } from '@playwright/test';
import { open, peer, other } from './harness.js';

test('IDs are private until the keyboard-accessible identity popover opens', async ({ page }) => {
  const ui = await open(page);
  expect(await ui.locator('body').innerText()).not.toContain(peer);
  await ui.getByRole('button', { name: 'Contact information', exact: true }).click();
  const popover = ui.getByRole('dialog', { name: 'Fulcra User ID' });
  await expect(popover.locator('.identity-id').nth(1)).toHaveText(peer);
  await expect(popover.locator('.identity-id').nth(2)).toHaveText(other);
  await popover.getByRole('button', { name: 'Copy ID' }).first().click();
  await expect(popover).toContainText('Select and copy');
  await page.keyboard.press('Escape');
  await expect(popover).toBeHidden();
});

test('a successful handoff shows a host-named toast', async ({ page }) => {
  const ui = await open(page, 900, { acceptAck: true });
  await ui.getByRole('button', { name: 'Continue in synthetic' }).click();
  await expect(ui.locator('.toast')).toContainText('Request sent to synthetic');
});

test('sidebar uses explicit unread badges without avatars on narrow screens', async ({ page }) => {
  const ui = await open(page, 390, { listOnly: true });
  await expect(ui.locator('.unread-dot.on')).toHaveText('Unread');
  await expect(ui.locator('.row-avatar, .row-avatar-wrap')).toHaveCount(0);
  await expect(ui.locator('.unread-dot.on')).toBeVisible();
  await ui.locator('.thread-button').filter({hasText:'Weekend'}).click();
  await expect(ui.locator('#connection-list')).toBeVisible();
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await expect(ui.locator('.contact-avatar, .bubble-avatar')).toHaveCount(0);
  expect(await ui.locator('body').evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
});

test('empty history gives a readable contact-specific next step', async ({ page }) => {
  const ui = await open(page, 900, {listOnly:true});
  await page.evaluate(() => { window.emptyRecords = true; });
  await ui.locator('.thread-button').filter({hasText:'Weekend'}).click();
  await expect(ui.locator('#message-status')).toContainText('No messages with Weekend');
  await expect(ui.locator('#message-status')).toContainText('Send');
});

test('contact assessment remains available in Advanced without redundant row labels', async ({ page }) => {
  const ui = await open(page);
  await expect(ui.locator('.relationship-state')).toBeHidden();
  await ui.locator('#advanced-toggle').click();
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

test('uncertain host delivery is not retried across navigation', async ({ page }) => {
  const ui = await open(page, 900, { acceptAck: true });
  await page.evaluate(() => { window.holdMessages = true; });
  await ui.getByRole('button', {name:'Continue in synthetic'}).click();
  await expect.poll(() => page.evaluate(() => window.hostMessages.length)).toBe(1);
  await page.clock.runFor(16000);
  await expect(ui.locator('.toast')).toContainText('Couldn’t confirm your request');
  await expect(ui.getByRole('button', {name:'Continue in synthetic'})).toBeDisabled();
  await ui.locator('.thread-button').filter({hasText:'Weekend'}).click();
  await expect(ui.getByRole('button', {name:'Continue in synthetic'})).toBeDisabled();
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
  await expect(dialog.getByRole('button', {name:'Copied',exact:true})).toHaveClass(/copy-success/);
  await ui.locator('#message-title').click();
  await expect(dialog).toBeHidden();
});

for (const width of [320, 900]) {
  test(`copy icon trails its ID on the same row at ${width}`, async ({page}) => {
    const ui = await open(page, width);
    await ui.getByRole('button', {name:'Contact information',exact:true}).click();
    const dialog = ui.getByRole('dialog', {name:'Fulcra User ID'});
    const id = await dialog.locator('.identity-id').first().boundingBox();
    const copy = await dialog.locator('.identity-copy').first().boundingBox();
    expect(copy.x).toBeGreaterThanOrEqual(id.x + id.width);
    expect(Math.abs(copy.y + copy.height / 2 - id.y - id.height / 2)).toBeLessThan(2);
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
  const copy = dialog.locator('.identity-copy').first();
  await copy.click();
  await ui.locator('body').evaluate(el => el.ownerDocument.defaultView.copies[0].resolve());
  await expect(copy).toHaveAttribute('aria-label','Copied');
  await copy.click();
  await expect(copy).toHaveAttribute('aria-label','Copy ID');
  await expect(copy).not.toHaveClass(/copy-success/);
  await ui.locator('body').evaluate(el => el.ownerDocument.defaultView.copies[1].reject(new Error('denied')));
  await expect(dialog).toContainText('Select and copy');
  await expect(copy).not.toHaveClass(/copy-success/);
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

test('a rejected direct send and a rejected handoff each surface an error toast', async ({ page }) => {
  const ui = await open(page, 900, { acceptAck: true });
  await ui.locator('.composer-input').fill('Direct message');
  await ui.getByRole('button', {name:'Send',exact:true}).click();
  await expect(ui.locator('.toast')).toContainText('Couldn’t send');
  // The draft returns to the composer so it can be retried.
  await expect(ui.locator('.composer-input')).toHaveValue('Direct message');
  await page.evaluate(() => { window.rejectMessages = true; });
  await ui.getByRole('button', {name:'Continue in synthetic'}).click();
  await expect(ui.locator('.toast').last()).toContainText('Couldn’t reach synthetic');
  await expect(ui.getByRole('button', {name:'Continue in synthetic'})).toBeEnabled();
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
  await expect(ui.getByRole('dialog', {name:'Fulcra User ID'}).locator('.identity-id')).toHaveText(peer);
});

test('contacts stay selectable beside the thread and composer follows history', async ({ page }) => {
  const ui = await open(page);
  await expect(ui.locator('#connection-list')).toBeVisible();
  await expect(ui.locator('.thread-button[aria-current="true"]')).toContainText('Weekend');
  // The composer scrolls with the conversation as the last item of the message pane.
  expect(await ui.locator('#thread-composer').evaluate(el => el.parentElement.id === 'message-area' && !el.nextElementSibling)).toBe(true);
});
