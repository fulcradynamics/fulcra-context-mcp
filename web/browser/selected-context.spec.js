import { test, expect } from '@playwright/test';
import { open, readOnlyThread, own, peer, out } from './harness.js';

const latest = page => page.evaluate(() => window.contexts.at(-1)?.content?.[0]?.text ?? '');
const quiet = async page => {
  expect(await page.evaluate(() => window.hostMessages)).toEqual([]);
  expect(await page.evaluate(() => window.calls.filter(c => c.name === 'agent_connection_send'))).toEqual([]);
};

test('context-only host gets loading identity then displayed context without a turn', async ({ page }) => {
  const ui = await open(page, 900, { ...readOnlyThread, holdReads: true, chat: false, contextOnly: true, sampling: true });
  await expect.poll(() => latest(page)).toContain('Weekend');
  const loading = await latest(page);
  expect(loading).toContain(own); expect(loading).toContain(peer); expect(loading).toContain(out);
  expect(loading).toContain('loading'); expect(loading).not.toContain('Broadcast message');
  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  await expect(ui.locator('#messages .message-row')).toHaveCount(6);
  await expect.poll(() => latest(page)).toContain('Broadcast message');
  expect(await latest(page)).toContain('untrusted');
  expect((await latest(page)).length).toBeLessThanOrEqual(24000);
  await expect(ui.getByRole('button', { name: 'Continue in synthetic' })).toBeDisabled();
  await quiet(page);
});

test('refresh replaces context, failed reads retain stale provenance, revocation clears', async ({ page }) => {
  const ui = await open(page, 900, readOnlyThread);
  await expect.poll(() => latest(page)).toContain('Broadcast message');
  await page.evaluate(() => { window.ownRecords = [{ id: 'fresh', sender: 'chatgpt', kind: 'message', body: 'Fresh displayed content', start_time: '2026-10-13T12:00:00Z' }]; });
  await page.clock.runFor(10000);
  await expect.poll(() => latest(page)).toContain('Fresh displayed content');
  await page.evaluate(() => { window.failReads = true; });
  await page.clock.runFor(10000);
  await expect.poll(() => latest(page)).toContain('stale');
  expect(await latest(page)).toContain('Fresh displayed content');
  await page.evaluate(() => { window.excludeOut = true; window.excludeIncoming = true; });
  await page.clock.runFor(30000);
  await expect.poll(() => latest(page)).toBe('');
  await quiet(page);
});

test('switch fences a delayed rejected attachment and teardown clears the replacement', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true });
  await page.evaluate(() => { window.navigationContact = true; });
  await page.clock.runFor(10000);
  await page.evaluate(() => { window.holdContexts = true; });
  await ui.locator('.thread-button').filter({ hasText: 'Weekend' }).click();
  await expect.poll(() => page.evaluate(() => window.heldContexts.length)).toBe(1);
  await ui.locator('.thread-button').filter({ hasText: 'Quiet contact' }).click();
  await page.evaluate(() => { window.holdContexts = false; window.releaseContexts(true); });
  await expect.poll(() => latest(page)).toContain('navigation-peer');
  expect(await latest(page)).not.toContain('Broadcast message');
  await page.evaluate(() => document.querySelector('iframe').contentWindow.postMessage({ jsonrpc: '2.0', id: 'dispose', method: 'ui/resource-teardown', params: {} }, '*'));
  await expect.poll(() => latest(page)).toBe('');
  expect(await page.evaluate(() => window.hostMessages)).toEqual([]);
});

test('unsupported host never receives context or messages', async ({ page }) => {
  await open(page, 900, { ...readOnlyThread, chat: false });
  await page.clock.runFor(10000);
  expect(await page.evaluate(() => window.contexts)).toEqual([]);
  await quiet(page);
});

test('source deselection replaces passive context without a chat handoff', async ({ page }) => {
  const ui = await open(page, 900, readOnlyThread);
  await expect.poll(() => latest(page)).toContain(peer + '-1');
  await ui.locator('#advanced-toggle').click();
  await ui.locator('.incoming-sources summary').click();
  await page.evaluate(() => { window.holdDiscovery = true; });
  await ui.locator('.incoming-sources input').first().uncheck();
  await expect.poll(() => latest(page)).not.toContain(peer + '-1');
  await expect.poll(() => latest(page)).toContain('Broadcast message');
  const snapshot = JSON.parse((await latest(page)).split('\n').slice(1).join('\n'));
  expect(snapshot.selected_sources.some(s => s.fulcra_userid === peer)).toBe(false);
  await quiet(page);
});

test('rejected passive history retries only on a later unchanged poll', async ({ page }) => {
  await open(page, 900, { ...readOnlyThread, holdReads: true });
  await expect.poll(() => latest(page)).toContain('Messages loading');
  await page.evaluate(() => { window.holdContexts = true; window.holdReads = false; window.releaseReads(); });
  await expect.poll(() => page.evaluate(() => window.heldContexts.length)).toBe(1);
  await page.evaluate(() => window.releaseContexts());
  await expect.poll(() => latest(page)).toContain('Broadcast message');
  await page.evaluate(() => { window.holdContexts = false; window.releaseContexts(true); });
  await expect.poll(() => latest(page)).toBe('');
  const count = await page.evaluate(() => window.contexts.length);
  await page.clock.runFor(1000);
  expect(await page.evaluate(() => window.contexts.length)).toBe(count);
  await page.clock.runFor(20000);
  await expect.poll(() => latest(page)).toContain('Broadcast message');
  await quiet(page);
});

for (const action of ['check', 'file']) {
  for (const changed of [false, true]) test(`${action} owns context until settlement then restores selection; changed=${changed}`, async ({ page }) => {
    const ui = await open(page, 900, { ...readOnlyThread, checkStatus: { status: 'not_set_up' },
      ownRecords: [{ id: 'file', sender: 'chatgpt', kind: 'message', body: 'File message', start_time: '2026-10-13T11:05:00Z', artifacts: [{ path: '/shared/file.txt' }] }] });
    await expect.poll(() => latest(page)).toContain('Broadcast message');
    await page.evaluate(() => { window.holdMessages = true; });
    if (action === 'check') await ui.locator('#onboarding-thread').getByRole('button', { name: 'Set up automatic checking' }).click();
    else await ui.getByRole('button', { name: 'Open file in synthetic' }).click();
    await expect.poll(() => page.evaluate(() => window.hostMessages.length)).toBe(1);
    expect(await latest(page)).toBe('');
    const count = await page.evaluate(() => window.contexts.length);
    if (changed) await page.evaluate(() => window.ownRecords.push({ id: 'fresh', sender: 'chatgpt', kind: 'message', body: 'Changed during handoff', start_time: '2026-10-13T12:00:00Z' }));
    await page.clock.runFor(10000);
    if (changed) await expect(ui.locator('#messages')).toContainText('Changed during handoff');
    expect(await page.evaluate(() => window.contexts.length)).toBe(count);
    await page.evaluate(() => { window.holdMessages = false; window.releaseMessage(); });
    await expect.poll(() => latest(page)).toContain(changed ? 'Changed during handoff' : 'Broadcast message');
    expect(await page.evaluate(() => window.hostMessages.length)).toBe(1);
  });
}

test('initial source removal stays filtered when temporary ownership ends before reads settle', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, presentation: 'thread', second: true, checkStatus: { status: 'not_set_up' } });
  const remaining = out.slice(0, -1) + '8';
  // Drain initial previews before revoking a source; only the selection's fresh
  // reads belong in the assertions below, not a detached older preview request.
  await expect(ui.locator('#connections .thread-time .refresh-spinner')).toHaveCount(0);
  await page.evaluate(() => { window.excludeOut = true; window.holdReads = true; window.holdMessages = true; window.calls = []; });
  await ui.locator('.thread-button').filter({ hasText: 'Weekend' }).click();
  await expect.poll(() => page.evaluate(() => window.heldReads.length)).toBeGreaterThan(0);
  const reads = await page.evaluate(() => window.calls.filter(c => c.name === 'get_records'));
  expect(reads.some(c => c.arguments.data_type === remaining)).toBe(true);
  expect(reads.some(c => c.arguments.data_type === out)).toBe(false);
  await expect.poll(() => page.evaluate(() => window.contexts.some(c => c.content.length === 0))).toBe(true);
  const beforeHandoff = await latest(page);
  const initial = await page.evaluate(() => window.contexts.find(c => c.content.length)?.content[0].text);
  expect(initial).toContain(out);
  expect(initial).toContain(remaining);
  await expect(ui.locator('#messages .message-row')).toHaveCount(0);

  await ui.locator('#onboarding-thread').getByRole('button', { name: 'Set up automatic checking' }).click();
  await expect.poll(() => page.evaluate(() => window.hostMessages.length)).toBe(1);
  expect(await latest(page)).toBe('');
  await page.evaluate(() => { window.holdMessages = false; window.releaseMessage(); });
  await expect.poll(() => latest(page)).toContain('Messages loading');
  const restored = JSON.parse((await latest(page)).split('\n').slice(1).join('\n'));
  expect(restored.selected_sources.some(s => s.id === out)).toBe(false);
  expect(restored.selected_sources.some(s => s.id === remaining && s.fulcra_userid === own)).toBe(true);
  expect(restored.messages).toEqual([]);
  expect(await latest(page)).not.toContain(out);
  expect(await latest(page)).toContain(remaining);
  expect(beforeHandoff).toContain('Messages loading');
  expect(beforeHandoff).not.toContain(out);
  await expect(ui.locator('#messages .message-row')).toHaveCount(0);
  expect(await page.evaluate(() => window.heldReads.length)).toBeGreaterThan(0);

  await page.evaluate(() => { window.holdReads = false; window.releaseReads(); });
  await expect.poll(() => latest(page)).toContain('Broadcast message');
  expect(await latest(page)).not.toContain(out);
  expect(await latest(page)).toContain(remaining);
  expect(await page.evaluate(() => window.hostMessages.length)).toBe(1);
  // The explicit click can now acknowledge through the newest eligible outbox.
  const sends = await page.evaluate(() => window.calls.filter(c => c.name === 'agent_connection_send').map(c => c.arguments));
  expect(sends).toHaveLength(1);
  expect(sends[0].kind).toBe('ack');
  expect(sends[0].outbox).toBe(remaining);
});

test('reopening applies saved source exclusions before delayed discovery', async ({ page }) => {
  const ui = await open(page, 900, readOnlyThread);
  await expect.poll(() => latest(page)).toContain('Broadcast message');
  await page.evaluate(() => { window.navigationContact = true; });
  await page.clock.runFor(10000);
  await ui.locator('#advanced-toggle').click();
  await ui.locator('.incoming-sources summary').click();
  await ui.locator('.incoming-sources input').first().uncheck();
  await expect.poll(() => latest(page)).not.toContain(peer + '-1');
  await ui.locator('.thread-button').filter({ hasText: 'Quiet contact' }).click();
  await expect.poll(() => latest(page)).toContain('navigation-peer');
  await page.evaluate(() => { window.holdDiscovery = true; });
  await ui.locator('.thread-button').filter({ hasText: 'Weekend' }).click();
  await expect.poll(() => latest(page)).toContain('Messages loading');
  const snapshot = JSON.parse((await latest(page)).split('\n').slice(1).join('\n'));
  expect(snapshot.selected_sources.some(s => s.fulcra_userid === peer)).toBe(false);
  expect(await latest(page)).toContain('excluded by the viewer');
  await expect(ui.locator('.incoming-sources input').first()).not.toBeChecked();
});

test('unchanged polling does not repeat passive attachment', async ({ page }) => {
  await open(page, 900, readOnlyThread);
  await expect.poll(() => latest(page)).toContain('Broadcast message');
  const count = await page.evaluate(() => window.contexts.length);
  await page.clock.runFor(21000);
  expect(await page.evaluate(() => window.contexts.length)).toBe(count);
  await quiet(page);
});

test('host mode changes preserve full-panel selection context without a turn', async ({ page }) => {
  const ui = await open(page, 900, { listOnly: true, presentation: 'thread' });
  await expect.poll(() => latest(page)).toContain('Broadcast message');
  await page.evaluate(() => document.querySelector('iframe').contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/host-context-changed', params: { displayMode: 'inline' } }, '*'));
  await expect(ui.locator('html')).toHaveAttribute('data-display-mode', 'inline');
  await expect(ui.locator('#connection-detail')).toBeVisible();
  await expect.poll(() => latest(page)).toContain('Broadcast message');
  await page.clock.runFor(11000);
  expect(await latest(page)).toContain('Broadcast message');
  expect(await page.evaluate(() => window.hostMessages)).toEqual([]);
});
