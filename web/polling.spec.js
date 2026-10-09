import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
const html = await readFile(new URL('../fulcra_mcp/ui/mesh.html', import.meta.url), 'utf8');
const channel = (owner = 'peer', id = 'in') => ({ id: `MomentAnnotation/${id}`, name: 'Mesh Outbox', fulcra_userid: owner });
async function open(page, entries = []) {
  await page.clock.install({ time: new Date('2026-01-10T12:00:00Z') });
  await page.clock.pauseAt(new Date('2026-01-10T12:00:01Z'));
  await page.setContent('<iframe sandbox="allow-scripts" style="width:100%;height:850px;border:0"></iframe>');
  await page.evaluate(({ html, entries }) => {
    window.entries = entries; window.calls = []; window.sends = []; window.held = []; window.rows = {}; window.sizes = [];
    window.contexts = [];
    window.shares = { own_fulcra_userid: 'me', outgoing: [], incoming: [] };
    const frame = document.querySelector('iframe');
    window.reply = (id, result) => frame.contentWindow.postMessage({ jsonrpc: '2.0', id, result }, '*');
    window.answer = request => {
      const { name, arguments: args } = request.params;
      if (window.fail?.includes(name) || window.fail?.includes(args.data_type)) { window.reply(request.id, { isError: true }); return; }
      const text = name === 'get_data_catalog' ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': window.entries })
        : name === 'list_shares' ? 'Shares: ' + JSON.stringify(window.shares)
        : `Records for ${args.data_type} from start to end: ${JSON.stringify(window.rows[`${args.fulcra_userid ?? 'me'}/${args.data_type}`] ?? [])}`;
      window.reply(request.id, { content: [{ type: 'text', text }] });
    };
    addEventListener('message', ({ data: r, source }) => {
      if (source !== frame.contentWindow) return;
      if (r.id === 'teardown' && 'result' in r) window.teardownReply = true;
      if (r.method === 'ui/initialize') window.reply(r.id, { protocolVersion: '2026-01-26', hostInfo: { name: 'fixture', version: '1' }, hostCapabilities: { updateModelContext: { text: {} } }, hostContext: { displayMode: 'fullscreen' } });
      if (r.method === 'ui/notifications/size-changed') window.sizes.push(r.params);
      if (r.method === 'ui/message') window.sends.push(r);
      if (r.method === 'ui/update-model-context') { window.contexts.push(r); if (!window.holdContext) window.reply(r.id, {}); }
      if (r.method === 'tools/call') {
        window.calls.push(r);
        if (window.hold?.includes(r.params.name)) window.held.push(r); else window.answer(r);
      }
    });
    frame.srcdoc = html;
  }, { html, entries });
  const ui = page.frameLocator('iframe');
  await expect(ui.locator('#mesh-status')).toContainText('threads returned');
  return ui;
}
test('catalog label changes do not replace keyed rows or merge identically named sources', async ({ page }) => {
  const ui = await open(page, [channel('peer', 'a'), channel('peer', 'b')]);
  await page.evaluate(() => {
    window.rows['peer/MomentAnnotation/a'] = [{ id: 'same', note: 'first channel' }];
    window.rows['peer/MomentAnnotation/b'] = [{ id: 'same', note: 'second channel' }];
  });
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect(ui.locator('#messages li')).toHaveCount(2);
  await ui.locator('#messages li').evaluateAll(rows => rows.forEach((row, index) => { row.identityMarker = index; }));
  await page.evaluate(() => { window.entries[0].name = 'Mesh Outbox <b>renamed</b>'; });
  await page.clock.runFor(10000);
  const renamed = ui.locator('#messages li').filter({ hasText: 'first channel' });
  const unchanged = ui.locator('#messages li').filter({ hasText: 'second channel' });
  await expect(renamed.locator('p').first()).toHaveText('Incoming (Mesh Outbox <b>renamed</b>)');
  expect(await renamed.evaluate(row => row.identityMarker)).toBe(0);
  expect(await unchanged.evaluate(row => row.identityMarker)).toBe(1);
  await expect(ui.locator('#messages b')).toHaveCount(0);
  await expect(unchanged.locator('p').first()).toHaveText('Incoming (Mesh Outbox)');
});

test('refresh preserves focus, disclosures, pending attachment and last-good records with explicit stale state', async ({ page }) => {
  const ui = await open(page, [channel()]);
  await page.evaluate(() => { window.rows['peer/MomentAnnotation/in'] = [{ id: 'first', note: 'last good' }]; });
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect(ui.locator('#messages')).toContainText('last good');
  const disclosure = ui.locator('#thread-composer summary'), tell = ui.getByRole('button', { name: 'Continue conversation in chat', exact: true });
  await disclosure.click(); await disclosure.focus();
  await page.evaluate(() => { window.hold = ['get_records']; });
  await page.clock.runFor(10000);
  await expect(ui.locator('#messages')).toContainText('last good');
  await expect(disclosure).toBeFocused();
  await release(page);
  await expect(ui.locator('#thread-composer details')).toHaveAttribute('open', '');
  await expect(disclosure).toBeFocused();
  await page.evaluate(() => { window.holdContext = true; });
  await tell.click();
  await expect.poll(() => page.evaluate(() => window.contexts.length)).toBe(1);
  const submitted = await page.evaluate(() => window.contexts[0].params);
  await page.evaluate(() => { window.rows['peer/MomentAnnotation/in'].push({ id: 'second', note: 'next good' }); });
  await page.clock.runFor(10000);
  await expect(ui.locator('#messages')).toContainText('next good');
  await expect(tell).toBeDisabled();
  await expect(ui.locator('#context-status')).toContainText('Clearing');
  expect(await page.evaluate(() => window.contexts[0].params)).toEqual(submitted);
  await page.evaluate(() => { window.holdContext = false; window.reply(window.contexts[0].id, {}); });
  await expect(ui.locator('#context-status')).toContainText('cleared');
  await page.evaluate(() => { window.fail = ['get_records']; });
  await page.clock.runFor(10000);
  await expect(ui.locator('#messages')).toContainText('last good');
  await expect(ui.locator('#message-status')).toContainText('Stale');
  await expect(ui.locator('#messages')).not.toContainText('Stale; access not verified. Last success:');
  await expect(ui.locator('#message-status')).toContainText('Last success:');
  await expect(ui.locator('#thread-context')).toContainText('"stale":true');
  await page.evaluate(() => { window.fail = ['get_data_catalog']; });
  await page.clock.runFor(20000);
  await expect(ui.locator('#message-status')).toContainText('discovery failed');
  await expect(ui.locator('#messages')).toContainText('last good');
  await expect(tell).toBeEnabled();
  await tell.click();
  await expect.poll(() => page.evaluate(() => window.contexts.length)).toBe(3);
  const staleSend = await page.evaluate(() => window.contexts[2].params.content[0].text);
  expect(staleSend).toContain('last good');
  expect(staleSend).toContain('"stale":true');
  expect(staleSend).toContain('discovery failed');
  expect(await page.evaluate(() => window.sends.length)).toBe(0);
  await page.evaluate(() => { window.fail = []; window.entries = []; });
  await page.clock.runFor(40000);
  await expect(ui.locator('#message-status')).toContainText('no longer available');
  await expect(tell).toBeDisabled();
  await expect(ui.locator('#thread-context')).not.toContainText('last good');
});

test('two UTC calendar dates, top composer and both orders; polling never applies unsubmitted edits', async ({ page }) => {
  const ui = await open(page, [channel()]);
  await page.evaluate(() => { window.rows['peer/MomentAnnotation/in'] = [
    { id: 'older', recorded_at: '2026-01-09T12:00:00Z', note: 'older body' },
    { id: 'newer', recorded_at: '2026-01-10T12:00:00Z', note: 'newer body' },
  ]; });
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect(ui.locator('#message-start')).toHaveValue('2026-01-09');
  await expect(ui.locator('#message-end')).toHaveValue('2026-01-10');
  await expect(ui.locator('#messages li').first()).toContainText('newer body');
  expect(await ui.locator('#thread-composer').evaluate(el => Boolean(document.querySelector('#message-range').compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) && Boolean(el.compareDocumentPosition(document.querySelector('#messages')) & Node.DOCUMENT_POSITION_FOLLOWING))).toBe(true);
  await ui.getByLabel('Message order').selectOption('oldest');
  await expect(ui.locator('#messages li').first()).toContainText('older body');
  await ui.locator('#message-start').fill('2025-01-01'); await ui.locator('#message-end').fill('2025-01-02');
  await page.clock.runFor(10000);
  expect(await page.evaluate(() => window.calls.filter(c => c.params.name === 'get_records').at(-1).params.arguments.start_time)).toBe('2026-01-09T00:00:00.000Z');
  await expect(ui.locator('#thread-context')).toContainText('2026-01-09T00:00:00.000Z');
  await expect(ui.locator('#message-start')).toHaveValue('2025-01-01');
  await page.evaluate(() => { window.hold = ['get_records']; });
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect.poll(() => reads(page)).toBe(3);
  await ui.locator('#message-start').fill('2024-01-01');
  await release(page);
  await expect(ui.locator('#message-status')).toContainText('2025-01-01 through 2025-01-02 UTC');
  await expect(ui.locator('#thread-context')).toContainText('2025-01-01T00:00:00.000Z');
  await page.clock.runFor(10000);
  expect(await page.evaluate(() => window.calls.filter(c => c.params.name === 'get_records').at(-1).params.arguments.start_time)).toBe('2025-01-01T00:00:00.000Z');
  expect(await page.evaluate(() => window.sends.length)).toBe(0);
});

test('manual refresh coalesces, preserves keyed list focus and labels account names; spinner supports reduced motion', async ({ page }) => {
  const ui = await open(page, [channel(), channel('other')]);
  const peer = ui.getByRole('button', { name: 'peer', exact: true });
  await peer.focus();
  const id = await peer.getAttribute('id');
  expect(id).toBeTruthy();
  await page.evaluate(() => { window.hold = ['get_data_catalog']; window.shares.incoming = [{ sharing_fulcra_userid: 'peer', sharing_fulcra_user_name: 'Alex' }]; });
  await page.clock.runFor(10000);
  await expect(busy(ui)).toBeVisible();
  await expect(ui.locator('.refresh-spinner')).toHaveCSS('animation-name', 'refresh-spin');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(ui.locator('.refresh-spinner')).toHaveCSS('animation-name', 'none');
  await release(page);
  await expect(peer).toBeFocused(); expect(await peer.getAttribute('id')).toBe(id);
  await expect(ui.locator('#meshes')).toContainText('Account: Alex');
  await page.evaluate(() => { window.hold = ['list_shares']; window.fail = ['get_data_catalog']; });
  await ui.getByRole('button', { name: 'Refresh threads', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.held.length)).toBe(1);
  const before = await page.evaluate(() => window.calls.length);
  await ui.getByRole('button', { name: 'Refresh threads', exact: true }).click();
  await ui.getByRole('button', { name: 'Refresh threads', exact: true }).click();
  await page.clock.runFor(10000);
  expect(await page.evaluate(() => window.calls.length)).toBe(before);
  await expect(busy(ui)).toBeVisible();
  await page.evaluate(() => { window.fail = []; }); await release(page);
  await expect.poll(() => page.evaluate(() => window.calls.length)).toBe(before + 2);
  await expect(busy(ui)).toBeHidden();
  await peer.click();
  await expect(ui.locator('#message-title')).toContainText('Account: Alex');
  await ui.getByRole('button', { name: 'Back to threads' }).click();
  await expect(peer).toBeFocused();
});

for (const focus of ['none', 'back button']) for (const visibility of ['below viewport', 'partly visible']) {
  test(`poll preserves page-top controls with ${focus} focused and first message ${visibility}`, async ({ page }) => {
    const ui = await open(page, [channel()]);
    await page.evaluate(() => { window.rows['peer/MomentAnnotation/in'] = Array.from({ length: 30 }, (_, i) => ({ id: `m${i}`, recorded_at: new Date(Date.UTC(2026, 0, 10, 0, i)).toISOString(), note: `Message ${i}\n` + 'History content. '.repeat(30) })); });
    await ui.getByRole('button', { name: 'peer', exact: true }).click();
    await expect(ui.locator('#messages li')).toHaveCount(30);
    const frame = page.frames()[1];
    if (visibility === 'below viewport') {
      const height = await ui.locator('#messages li').first().evaluate(el => Math.floor(scrollY + el.getBoundingClientRect().top));
      await page.setViewportSize({ width: 1280, height: height + 32 });
      await page.locator('iframe').evaluate((el, height) => { el.style.height = `${height}px`; }, height);
    }
    if (visibility === 'partly visible') {
      const height = await ui.locator('#messages li').first().evaluate(el => {
        const rect = el.getBoundingClientRect();
        return Math.ceil(scrollY + rect.top + rect.height / 2);
      });
      await page.setViewportSize({ width: 1280, height: height + 32 });
      await page.locator('iframe').evaluate((el, height) => { el.style.height = `${height}px`; }, height);
    }
    await frame.evaluate(focus => {
      if (focus === 'back button') document.querySelector('#message-back').focus({ preventScroll: true });
      else document.activeElement.blur();
      scrollTo(0, 0);
    }, focus);
    const geometry = () => frame.evaluate(() => ({
      scroll: scrollY,
      firstTop: document.querySelector('#messages li').getBoundingClientRect().top,
      firstBottom: document.querySelector('#messages li').getBoundingClientRect().bottom,
      composerBottom: document.querySelector('#thread-composer').getBoundingClientRect().bottom,
      height: innerHeight,
      focused: document.activeElement.id || document.activeElement.tagName,
    }));
    const before = await geometry();
    expect(before.scroll).toBe(0);
    expect(before.focused).toBe(focus === 'back button' ? 'message-back' : 'BODY');
    expect(before.composerBottom).toBeGreaterThan(0);
    expect(before.composerBottom).toBeLessThan(before.height);
    if (visibility === 'partly visible') {
      expect(before.firstTop).toBeLessThan(before.height);
      expect(before.firstBottom).toBeGreaterThan(before.height);
    } else expect(before.firstTop).toBeGreaterThanOrEqual(before.height);
    await page.evaluate(() => { window.rows['peer/MomentAnnotation/in'].push({ id: 'new', recorded_at: '2026-01-10T12:00:00Z', note: 'New arrival' }); });
    await page.clock.runFor(10000);
    await expect(ui.locator('#messages li')).toHaveCount(31);
    const after = await geometry();
    expect(after.scroll).toBe(before.scroll);
    expect(after.composerBottom).toBe(before.composerBottom);
    expect(after.focused).toBe(before.focused);
    await expect(ui.locator('#new-activity')).toBeVisible();
  });
}

for (const expanded of [false, true]) for (const order of ['latest', 'oldest']) test(`preserves visible keyed message and offset in ${order} order (context ${expanded ? 'expanded' : 'collapsed'}); new activity follows latest edge`, async ({ page }) => {
  const ui = await open(page, [channel()]);
  await page.evaluate(() => { window.rows['peer/MomentAnnotation/in'] = Array.from({ length: 30 }, (_, i) => ({ id: `m${i}`, recorded_at: new Date(Date.UTC(2026, 0, 10, 0, i)).toISOString(), note: `Message ${i}\n` + 'History content. '.repeat(30) })); });
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect(ui.locator('#messages li')).toHaveCount(30);
  await ui.getByLabel('Message order').selectOption(order);
  if (expanded) await ui.locator('#thread-composer summary').click();
  const row = ui.locator('#messages li').nth(14);
  await row.evaluate(el => { el.scrollIntoView(); scrollBy(0, 25); window.anchor = el; });
  const before = await row.evaluate(el => el.getBoundingClientRect().top);
  await page.evaluate(() => { window.rows['peer/MomentAnnotation/in'].push({ id: 'new', recorded_at: '2026-01-10T12:00:00Z', note: 'New arrival' }); });
  await page.clock.runFor(10000);
  await expect(ui.locator('#messages li')).toHaveCount(31);
  expect(await page.frames()[1].evaluate(() => window.anchor.isConnected)).toBe(true);
  expect(Math.abs(await page.frames()[1].evaluate(() => window.anchor.getBoundingClientRect().top) - before)).toBeLessThan(2);
  await ui.getByRole('button', { name: 'New activity', exact: true }).click();
  const latest = order === 'latest' ? ui.locator('#messages li').first() : ui.locator('#messages li').last();
  await expect(latest).toBeInViewport();
  await expect(ui.getByRole('button', { name: 'New activity', exact: true })).toBeHidden();
  await page.evaluate(() => { window.rows['peer/MomentAnnotation/in'].push({ id: 'new2', recorded_at: '2026-01-10T13:00:00Z', note: 'Followed arrival' }); });
  await page.clock.runFor(10000);
  await expect(latest).toContainText('Followed arrival');
  await expect(latest).toBeInViewport();
});

test('discovery and partial-message failures back off, reset on success, and manual retry bypasses delay', async ({ page }) => {
  const ui = await open(page, [channel()]);
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect.poll(() => reads(page)).toBe(1);
  await page.evaluate(() => { window.fail = ['get_records']; });
  await page.clock.runFor(10000);
  await expect(ui.locator('#message-status')).toContainText('Could not load');
  let count = await reads(page);
  for (const delay of [20000, 40000, 80000, 80000]) {
    await page.clock.runFor(delay - 1); expect(await reads(page)).toBe(count);
    await page.clock.runFor(1); await expect.poll(() => reads(page)).toBe(++count);
    await expect(busy(ui)).toBeHidden();
  }
  await page.evaluate(() => { window.fail = []; });
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect.poll(() => reads(page)).toBe(++count);
  await expect(busy(ui)).toBeHidden();
  await page.clock.runFor(10000); await expect.poll(() => reads(page)).toBe(++count);
  await page.evaluate(() => { window.fail = ['list_shares']; });
  await page.clock.runFor(10000);
  await expect(ui.locator('#message-status')).toContainText('discovery failed');
  const calls = await page.evaluate(() => window.calls.length);
  await page.clock.runFor(19999); expect(await page.evaluate(() => window.calls.length)).toBe(calls);
  await page.clock.runFor(1); await expect.poll(() => page.evaluate(() => window.calls.length)).toBe(calls + 2);
  expect(await reads(page)).toBe(count);
});

test('hidden discovery drains without message reads; SDK teardown stops queued requests and late rendering', async ({ page }) => {
  const ui = await open(page, [channel()]);
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect.poll(() => reads(page)).toBe(1);
  await expect(busy(ui)).toBeHidden();
  await page.evaluate(() => { window.hold = ['get_data_catalog']; });
  await page.clock.runFor(10000);
  await expect(busy(ui)).toBeVisible();
  await visibility(page, 'hidden');
  await release(page);
  await expect(busy(ui)).toBeHidden();
  expect(await reads(page)).toBe(1);
  const count = await page.evaluate(() => window.calls.length);
  await page.clock.runFor(160000);
  expect(await page.evaluate(() => window.calls.length)).toBe(count);
  await page.evaluate(() => { window.hold = ['get_records']; });
  await visibility(page, 'visible');
  await expect.poll(() => reads(page)).toBe(2);
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await page.evaluate(() => document.querySelector('iframe').contentWindow.postMessage({ jsonrpc: '2.0', id: 'teardown', method: 'ui/resource-teardown', params: {} }, '*'));
  await expect.poll(() => page.evaluate(() => window.teardownReply)).toBe(true);
  await page.evaluate(() => { window.rows['peer/MomentAnnotation/in'] = [{ id: 'late', note: 'never render after teardown' }]; });
  await release(page);
  await expect(busy(ui)).toBeHidden();
  await page.clock.runFor(160000);
  await visibility(page, 'visible');
  expect(await reads(page)).toBe(2);
  await expect(ui.locator('#messages')).not.toContainText('never render');
});

test('all message calls drain on partial failure before coalesced manual rerun; one discovery per batch', async ({ page }) => {
  const ui = await open(page, [channel('peer', 'one'), channel('peer', 'two')]);
  await page.evaluate(() => { window.hold = ['get_records']; });
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.held.length)).toBe(2);
  await page.evaluate(() => window.reply(window.held.shift().id, { isError: true }));
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  const before = await page.evaluate(() => window.calls.length);
  await page.clock.runFor(10000);
  expect(await page.evaluate(() => window.calls.length)).toBe(before);
  await expect(busy(ui)).toBeVisible();
  await release(page);
  await expect.poll(() => page.evaluate(() => window.calls.length)).toBe(before + 4);
  await expect(busy(ui)).toBeHidden();
  expect(await page.evaluate(() => window.calls.filter(c => c.params.name === 'get_data_catalog').length)).toBe(3);
  expect(await reads(page)).toBe(4);
});

test('revoked source is removed even while a changed range fails; retained range and context remain honest', async ({ page }) => {
  const ui = await open(page, [channel('peer', 'one'), channel('peer', 'two')]);
  await page.evaluate(() => {
    window.rows['peer/MomentAnnotation/one'] = [{ id: 'one', note: 'revoked content' }];
    window.rows['peer/MomentAnnotation/two'] = [{ id: 'two', note: 'retained content' }];
  });
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect(ui.locator('#messages li')).toHaveCount(2);
  await page.evaluate(entries => { window.entries = entries; window.hold = ['get_records']; window.fail = ['get_records']; }, [channel('peer', 'two')]);
  await ui.locator('#message-start').fill('2025-01-01');
  await ui.locator('#message-end').fill('2025-01-02');
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect(ui.locator('#messages')).not.toContainText('revoked content');
  await expect(ui.locator('#thread-context')).not.toContainText('revoked content');
  await release(page);
  await expect(ui.locator('#messages')).toContainText('retained content');
  await expect(ui.locator('#message-status')).toContainText('Showing previous applied range');
  await expect(ui.locator('#thread-context')).toContainText('2026-01-09T00:00:00.000Z');
  await expect(ui.locator('#thread-context')).toContainText('"stale":true');
  const tell = ui.getByRole('button', { name: 'Continue conversation in chat', exact: true });
  await expect(tell).toBeEnabled();
  await tell.click();
  await expect.poll(() => page.evaluate(() => window.contexts.length)).toBe(1);
  const sent = await page.evaluate(() => window.contexts[0].params.content[0].text);
  expect(sent).toContain('retained content');
  expect(sent).not.toContain('revoked content');
  expect(sent).toContain('2026-01-09T00:00:00.000Z');
  expect(sent).toContain('Showing previous applied range');
});

test('discovery failure permits a previously loaded empty thread but not an unloaded thread', async ({ page }) => {
  const ui = await open(page, [channel()]);
  await page.evaluate(() => { window.fail = ['list_shares']; });
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect(ui.locator('#message-status')).toContainText('discovery failed');
  const tell = ui.getByRole('button', { name: 'Continue conversation in chat', exact: true });
  await expect(tell).toBeDisabled();
  await page.evaluate(() => { window.fail = []; });
  await ui.getByRole('button', { name: 'Load messages', exact: true }).click();
  await expect(ui.locator('#message-status')).toContainText('0 messages shown');
  await expect(tell).toBeEnabled();
  await page.evaluate(() => { window.fail = ['list_shares']; });
  await page.clock.runFor(10000);
  await expect(ui.locator('#message-status')).toContainText('discovery failed');
  await expect(tell).toBeEnabled();
  const preview = await ui.locator('#thread-context').textContent();
  await page.clock.runFor(20000);
  await expect(busy(ui)).toBeHidden();
  await expect(tell).toBeEnabled();
  await expect(ui.locator('#thread-context')).toHaveText(preview);
  expect(await page.evaluate(() => window.sends.length)).toBe(0);
});

const reads = page => page.evaluate(() => window.calls.filter(c => c.params.name === 'get_records').length);
const busy = ui => ui.locator('#refresh-status');
async function release(page) { await page.evaluate(() => { window.hold = []; for (const r of window.held.splice(0)) window.answer(r); }); }
async function visibility(page, state) {
  await page.frames()[1].evaluate(state => { Object.defineProperty(document, 'visibilityState', { configurable: true, value: state }); document.dispatchEvent(new Event('visibilitychange')); }, state);
}

test('visible polling discovers first thread from empty, reads only selected peer, shows actual busy state, resumes and stops', async ({ page }) => {
  const ui = await open(page);
  await expect(ui.locator('#meshes li')).toHaveCount(0);
  await page.evaluate(entries => { window.entries = entries; window.hold = ['get_data_catalog']; }, [channel(), channel('other')]);
  await page.clock.runFor(10000);
  await expect(busy(ui)).toBeVisible();
  await expect(busy(ui)).toContainText('Refreshing');
  await release(page);
  await expect(ui.locator('#meshes li')).toHaveCount(2);
  await expect(busy(ui)).toBeHidden();
  expect(await reads(page)).toBe(0);
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect.poll(() => reads(page)).toBe(1);
  await expect(ui.locator('#message-status')).toContainText('0 messages');
  await page.evaluate(() => { window.rows['peer/MomentAnnotation/in'] = [{ id: 'new', recorded_at: '2026-01-10T12:00:00Z', note: 'newly arrived' }]; window.hold = ['get_records']; });
  await page.clock.runFor(10000);
  await expect(busy(ui)).toBeVisible();
  await release(page);
  await expect(ui.locator('#messages')).toContainText('newly arrived');
  expect(await page.evaluate(() => window.calls.filter(c => c.params.name === 'get_records').every(c => c.params.arguments.fulcra_userid === 'peer'))).toBe(true);
  await visibility(page, 'hidden');
  const before = await page.evaluate(() => window.calls.length);
  await page.clock.runFor(60000); expect(await page.evaluate(() => window.calls.length)).toBe(before);
  await visibility(page, 'visible'); await expect.poll(() => reads(page)).toBe(3);
  await expect(busy(ui)).toBeHidden();
  await page.frames()[1].evaluate(() => dispatchEvent(new Event('pagehide')));
  const stopped = await page.evaluate(() => window.calls.length);
  await page.clock.runFor(60000); expect(await page.evaluate(() => window.calls.length)).toBe(stopped);
  expect(await page.evaluate(() => window.sends.length)).toBe(0);
});
