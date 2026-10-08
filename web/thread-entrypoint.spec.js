import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
const bundle = await readFile(new URL('../fulcra_mcp/ui/mesh.html', import.meta.url), 'utf8');
async function open(page, options = {}) {
  await page.clock.install({ time: new Date('2026-01-10T12:00:00Z') });
  await page.clock.pauseAt(new Date('2026-01-10T12:00:01Z'));
  await page.setContent('<iframe sandbox="allow-scripts" style="width:100%;height:1000px"></iframe>');
  await page.evaluate(({ bundle, options }) => {
    const frame = document.querySelector('iframe');
    window.options = options; window.calls = []; window.contexts = []; window.sends = []; window.samples = [];
    window.peers = ['peer', 'other']; window.note = 'Untrusted peer text';
    window.reply = (id, result) => frame.contentWindow.postMessage({ jsonrpc: '2.0', id, result }, '*');
    window.reject = id => frame.contentWindow.postMessage({ jsonrpc: '2.0', id, error: { code: -32603, message: 'Rejected' } }, '*');
    window.initial = () => frame.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: {
      content: [], structuredContent: { presentation: 'thread', peer_fulcra_userid: options.peer ?? null },
    } }, '*');
    addEventListener('message', ({ data: r, source }) => {
      if (source !== frame.contentWindow) return;
      if (r.method === 'ui/initialize') {
        if (options.early) window.initial();
        window.reply(r.id, { protocolVersion: '2026-01-26', hostInfo: { name: 'synthetic', version: '1' }, hostContext: { displayMode: 'fullscreen' },
          hostCapabilities: { ...(options.noMessage ? {} : { message: { text: {} } }), ...(options.noContext ? {} : { updateModelContext: { text: {} } }), ...(options.noSampling ? {} : { sampling: {} }) } });
      }
      if (r.method === 'ui/notifications/initialized' && !options.early && !options.holdInitial) window.initial();
      if (r.method === 'tools/call') {
        window.calls.push(r);
        const { name, arguments: args } = r.params;
        const text = name === 'get_data_catalog' ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': window.peers.map(peer => ({ id: 'MomentAnnotation/in', name: 'Mesh Outbox', fulcra_userid: peer })) })
          : name === 'list_shares' ? 'Shares: ' + JSON.stringify({ own_fulcra_userid: 'me', incoming: [], outgoing: [] })
          : `Records for ${args.data_type} from start to end: ` + JSON.stringify([{ id: 'one', note: window.note }]);
        window.reply(r.id, { content: [{ type: 'text', text }] });
      }
      if (r.method === 'ui/update-model-context') { window.contexts.push(r); if (!window.options.holdContext) window.reply(r.id, {}); }
      if (r.method === 'ui/message') { window.sends.push(r); if (!window.options.holdSend) { if (window.options.failSend) window.reject(r.id); else window.reply(r.id, {}); } }
      if (r.method === 'sampling/createMessage') { window.samples.push(r); if (!window.options.holdSampling) { if (window.options.failSampling) window.reject(r.id); else window.reply(r.id, { role: 'assistant', model: 'synthetic', content: { type: 'text', text: '["Yes, thanks.","Could you clarify?"]' }, stopReason: 'endTurn' }); } }
    });
    frame.srcdoc = options.global ? bundle : bundle.replace('<meta name="mesh-presentation" content="global">', '<meta name="mesh-presentation" content="thread">');
  }, { bundle, options });
  return page.frameLocator('iframe');
}
for (const early of [true, false]) test(`initial exact peer consumed ${early ? 'before' : 'after'} connect without repeat opener`, async ({ page }) => {
  const ui = await open(page, { peer: 'peer', early });
  await expect(ui.locator('#message-title')).toContainText('Thread with peer');
  await expect(ui.locator('#messages')).toContainText('Untrusted peer text');
  await expect(ui.getByRole('button', { name: 'Tell my agent', exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.calls.every(r => ['get_data_catalog', 'list_shares', 'get_records'].includes(r.params.name)))).toBe(true);
  expect(await page.evaluate(() => [window.samples.length, window.sends.length, window.contexts.length])).toEqual([0, 0, 0]);
});
for (const peer of [null, 'missing', ' peer ']) test(`manual or unmatched exact peer stays on picker: ${peer}`, async ({ page }) => {
  const ui = await open(page, { peer });
  await expect(ui.locator('#mesh-status')).toContainText('threads returned');
  await expect(ui.locator('#mesh-detail')).toBeHidden();
  if (peer) await expect(ui.locator('#entrypoint-status')).toContainText('not available');
  await ui.getByRole('button', { name: 'other', exact: true }).click();
  await expect(ui.locator('#message-title')).toContainText('Thread with other');
});
test('delayed initial result selects requested peer, never guesses from display mode', async ({ page }) => {
  const ui = await open(page, { peer: 'other', holdInitial: true });
  await expect(ui.locator('#entrypoint-status')).toContainText('Waiting');
  await expect(ui.locator('#mesh-detail')).toBeHidden();
  await page.evaluate(() => window.initial());
  await expect(ui.locator('#message-title')).toContainText('Thread with other');
});
test('exact original nonblank text is sent once only after context ack', async ({ page }) => {
  const ui = await open(page, { peer: 'peer', holdContext: true });
  const draft = ui.locator('textarea');
  const send = ui.getByRole('button', { name: 'Tell my agent', exact: true });
  await expect(draft).toBeVisible();
  await draft.fill('   \n'); await expect(send).toBeDisabled();
  const text = '  Please draft a reply.\nKeep this whitespace.  ';
  await draft.fill(text); await send.click();
  await expect(send).toBeDisabled();
  expect(await page.evaluate(() => window.sends.length)).toBe(0);
  await page.evaluate(() => window.reply(window.contexts[0].id, {}));
  await expect(ui.locator('#send-status')).toContainText('accepted');
  expect(await page.evaluate(() => window.sends.map(r => r.params))).toEqual([{ role: 'user', content: [{ type: 'text', text }] }]);
  await expect(draft).toHaveValue('');
  const context = await page.evaluate(() => window.contexts[0].params.content[0].text);
  expect(context.length).toBeLessThanOrEqual(24000);
  expect(context).toContain('peer_fulcra_userid');
  expect(context).toContain('MomentAnnotation/in');
});
for (const noCapability of ['noMessage', 'noContext']) test(`send unavailable honestly: ${noCapability}`, async ({ page }) => {
  const ui = await open(page, { peer: 'peer', [noCapability]: true });
  await ui.locator('textarea').fill('request');
  await expect(ui.getByRole('button', { name: 'Tell my agent', exact: true })).toBeDisabled();
  await expect(ui.locator('#send-status')).toContainText('does not support');
});
test('failed delivery preserves draft and durable feedback across cleanup', async ({ page }) => {
  const ui = await open(page, { peer: 'peer', failSend: true });
  await ui.locator('textarea').fill('keep me');
  await ui.getByRole('button', { name: 'Tell my agent', exact: true }).click();
  await expect(ui.locator('#send-status')).toContainText('Check the conversation');
  await expect(ui.locator('textarea')).toHaveValue('keep me');
  await page.evaluate(() => { window.note = 'changed'; });
  await page.clock.runFor(10000);
  await expect(ui.locator('#context-status')).toContainText('cleared');
  await expect(ui.locator('#send-status')).toContainText('Check the conversation');
});
for (const change of ['navigation', 'poll']) test(`pending attachment revalidates ${change}, no send, keeps draft`, async ({ page }) => {
  const ui = await open(page, { peer: 'peer', holdContext: true });
  await ui.locator('textarea').fill('keep me');
  await ui.getByRole('button', { name: 'Tell my agent', exact: true }).click();
  if (change === 'navigation') {
    await ui.getByRole('button', { name: 'Back to threads' }).click();
    await ui.getByRole('button', { name: 'other', exact: true }).click();
    await ui.locator('textarea').fill('other draft');
    await expect(ui.getByRole('button', { name: 'Tell my agent', exact: true })).toBeDisabled();
  } else {
    await page.evaluate(() => { window.note = 'changed'; });
    await page.clock.runFor(10000);
    // Advancing the clock starts polling; postMessage replies still need to drain.
    await expect(ui.locator('#messages')).toContainText('changed');
  }
  await page.evaluate(() => window.reply(window.contexts[0].id, {}));
  await expect.poll(() => page.evaluate(() => window.contexts.length)).toBe(2);
  await page.evaluate(() => window.reply(window.contexts[1].id, {}));
  expect(await page.evaluate(() => window.sends.length)).toBe(0);
  if (change === 'navigation') {
    await ui.getByRole('button', { name: 'Back to threads' }).click();
    await ui.getByRole('button', { name: 'peer', exact: true }).click();
  }
  await expect(ui.locator('textarea')).toHaveValue('keep me');
});
test('accepted send cannot clear an edited current draft', async ({ page }) => {
  const ui = await open(page, { peer: 'peer', holdSend: true });
  await ui.locator('textarea').fill('first');
  await ui.getByRole('button', { name: 'Tell my agent', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.sends.length)).toBe(1);
  await ui.locator('textarea').fill('second');
  await page.evaluate(() => window.reply(window.sends[0].id, {}));
  await expect(ui.locator('#send-status')).toContainText('accepted');
  await expect(ui.locator('textarea')).toHaveValue('second');
});

for (const outcome of ['accept', 'reject']) test(`cross-navigation ${outcome} attributes submitted request, not new draft`, async ({ page }) => {
  const ui = await open(page, { peer: 'peer', holdSend: true });
  const text = '  Original request.\nPreserve exact whitespace.  ';
  await ui.locator('textarea').fill(text);
  await ui.getByRole('button', { name: 'Tell my agent', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.sends.length)).toBe(1);
  await ui.getByRole('button', { name: 'Back to threads' }).click();
  await ui.getByRole('button', { name: 'other', exact: true }).click();
  await ui.locator('textarea').fill('NEW private unsent draft');
  const pending = await ui.locator('#send-status').textContent();
  await page.evaluate(outcome => {
    if (outcome === 'accept') window.reply(window.sends[0].id, {});
    else window.reject(window.sends[0].id);
  }, outcome);
  const status = ui.locator('#send-status');
  await expect(status).toContainText(outcome === 'accept' ? 'accepted' : 'Could not confirm delivery');
  await expect(ui.locator('textarea')).toHaveValue('NEW private unsent draft');
  expect(await page.evaluate(() => window.sends.map(r => r.params))).toEqual([{ role: 'user', content: [{ type: 'text', text }] }]);
  const attribution = 'Submitted request #1 for peer ID "peer" (not the current draft):';
  await expect(status).toContainText(attribution);
  expect(pending).toContain(attribution);
  await expect(status).not.toContainText('NEW private unsent draft');
  await expect(status).not.toContainText('Untrusted peer text');
});

test('sampling is explicit, bounded, and suggestions only populate the draft', async ({ page }) => {
  const ui = await open(page, { peer: 'peer' });
  await expect(ui.locator('#messages')).toContainText('Untrusted');
  await page.clock.runFor(20000);
  expect(await page.evaluate(() => window.samples.length)).toBe(0);
  await ui.getByRole('button', { name: 'Suggest replies', exact: true }).click();
  const suggestion = ui.getByRole('button', { name: 'Yes, thanks.', exact: true });
  await expect(suggestion).toBeVisible();
  await expect(ui.locator('textarea')).toHaveValue('');
  await suggestion.click();
  await expect(ui.locator('textarea')).toHaveValue('Yes, thanks.');
  expect(await page.evaluate(() => [window.sends.length, window.contexts.length])).toEqual([0, 0]);
  const request = await page.evaluate(() => window.samples[0].params);
  expect(request.maxTokens).toBeLessThanOrEqual(400);
  expect(request.includeContext).toBe('none');
  expect(request.messages[0].content.text.length).toBeLessThanOrEqual(24000);
  expect(request.messages[0].content.text).toContain('peer_fulcra_userid');
  expect(request.messages[0].content.text).toContain('MomentAnnotation/in');
  expect(request.systemPrompt).toContain('untrusted');
});
for (const mode of ['noSampling', 'failSampling']) test(`sampling ${mode} is truthful`, async ({ page }) => {
  const ui = await open(page, { peer: 'peer', [mode]: true });
  const suggest = ui.getByRole('button', { name: 'Suggest replies', exact: true });
  if (mode === 'noSampling') await expect(suggest).toBeDisabled();
  else await suggest.click();
  await expect(ui.locator('#suggestion-status')).toContainText(mode === 'noSampling' ? 'does not support' : 'Could not');
  await expect(ui.locator('#reply-suggestions button')).toHaveCount(0);
});
for (const change of ['poll', 'navigation', 'draft']) test(`late sampling rejects ${change} results`, async ({ page }) => {
  const ui = await open(page, { peer: 'peer', holdSampling: true });
  await ui.getByRole('button', { name: 'Suggest replies', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.samples.length)).toBe(1);
  if (change === 'navigation') {
    await ui.getByRole('button', { name: 'Back to threads' }).click();
    await ui.getByRole('button', { name: 'other', exact: true }).click();
  } else if (change === 'poll') {
    await page.evaluate(() => { window.note = 'new current context'; });
    await page.clock.runFor(10000);
    await expect(ui.locator('#messages')).toContainText('new current context');
  } else await ui.locator('textarea').fill('my own draft');
  await page.evaluate(() => window.reply(window.samples[0].id, { role: 'assistant', model: 'synthetic', content: { type: 'text', text: '["Late reply"]' } }));
  await expect(ui.locator('#reply-suggestions button')).toHaveCount(0);
  await expect(ui.locator('textarea')).toHaveValue(change === 'draft' ? 'my own draft' : '');
});

test('sampling pending guard spans navigation and repeated clicks', async ({ page }) => {
  const ui = await open(page, { peer: 'peer', holdSampling: true });
  await ui.getByRole('button', { name: 'Suggest replies', exact: true }).click();
  await expect(ui.getByRole('button', { name: 'Suggest replies', exact: true })).toBeDisabled();
  await ui.getByRole('button', { name: 'Back to threads' }).click();
  await ui.getByRole('button', { name: 'other', exact: true }).click();
  await expect(ui.locator('#messages')).toContainText('Untrusted');
  await expect(ui.getByRole('button', { name: 'Suggest replies', exact: true })).toBeDisabled();
  await page.evaluate(() => window.reject(window.samples[0].id));
  await expect(ui.getByRole('button', { name: 'Suggest replies', exact: true })).toBeEnabled();
  expect(await page.evaluate(() => window.samples.length)).toBe(1);
});

test('late initial result cannot replace an explicit picker choice', async ({ page }) => {
  const ui = await open(page, { peer: 'peer', holdInitial: true });
  await ui.getByRole('button', { name: 'Refresh threads', exact: true }).click();
  await ui.getByRole('button', { name: 'other', exact: true }).click();
  await expect(ui.locator('#messages')).toContainText('Untrusted');
  await page.evaluate(() => window.initial());
  await expect(ui.locator('#message-title')).toContainText('Thread with other');
  await page.clock.runFor(10000);
  await expect(ui.locator('#message-title')).toContainText('Thread with other');
});

test('uncertain send and navigation preserve draft and app-wide pending guard', async ({ page }) => {
  const ui = await open(page, { peer: 'peer', holdSend: true });
  await ui.locator('textarea').fill('original');
  await ui.getByRole('button', { name: 'Tell my agent', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.sends.length)).toBe(1);
  await ui.getByRole('button', { name: 'Back to threads' }).click();
  await ui.getByRole('button', { name: 'other', exact: true }).click();
  await ui.locator('textarea').fill('other draft');
  await expect(ui.getByRole('button', { name: 'Tell my agent', exact: true })).toBeDisabled();
  await page.clock.runFor(15001);
  await expect(ui.locator('#send-status')).toContainText('Check the conversation');
  await expect(ui.getByRole('button', { name: 'Tell my agent', exact: true })).toBeEnabled();
  await ui.getByRole('button', { name: 'Back to threads' }).click();
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect(ui.locator('textarea')).toHaveValue('original');
  expect(await page.evaluate(() => window.sends.length)).toBe(1);
});
for (const text of ['["<img src=x onerror=alert(1)>"]', '["1","2","3","4"]', 'Here are some replies']) test(`sampling handles plain text and invalid formats: ${text}`, async ({ page }) => {
  const ui = await open(page, { peer: 'peer', holdSampling: true });
  await ui.getByRole('button', { name: 'Suggest replies', exact: true }).click();
  await page.evaluate(text => window.reply(window.samples[0].id, { role: 'assistant', model: 'synthetic', content: { type: 'text', text } }), text);
  if (text.includes('<img')) {
    await expect(ui.locator('#reply-suggestions button')).toHaveText('<img src=x onerror=alert(1)>');
    await expect(ui.locator('#reply-suggestions img')).toHaveCount(0);
  } else {
    await expect(ui.locator('#suggestion-status')).toContainText('Could not');
    await expect(ui.locator('#reply-suggestions button')).toHaveCount(0);
  }
  expect(await page.evaluate(() => window.sends.length)).toBe(0);
});

test('late rejected sampling reports invalidation instead of staying pending', async ({ page }) => {
  const ui = await open(page, { peer: 'peer', holdSampling: true });
  await ui.getByRole('button', { name: 'Suggest replies', exact: true }).click();
  await ui.locator('textarea').fill('new draft');
  await page.evaluate(() => window.reject(window.samples[0].id));
  await expect(ui.locator('#suggestion-status')).toContainText('discarded');
});
test('thread cleanup guidance names an action present in thread presentation', async ({ page }) => {
  const ui = await open(page, { peer: 'peer' });
  await ui.locator('textarea').fill('request');
  await ui.getByRole('button', { name: 'Tell my agent', exact: true }).click();
  await expect(ui.locator('#send-status')).toContainText('accepted');
  await page.evaluate(() => { window.note = 'changed'; });
  await page.clock.runFor(10000);
  await expect(ui.locator('#context-status')).toContainText('cleared');
  await expect(ui.locator('#context-status')).not.toContainText('Continue conversation in chat');
});

for (const width of [1120, 320]) test(`thread presentation layout at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1100 });
  const ui = await open(page, { peer: 'peer' });
  await page.evaluate(() => {
    document.body.style.margin = '0';
    document.querySelector('iframe').style.border = '0';
  });
  await expect(ui.locator('#messages')).toContainText('Untrusted');
  await ui.locator('textarea').fill('Please help me reply.');
  await ui.getByRole('button', { name: 'Suggest replies', exact: true }).click();
  await expect(ui.locator('#reply-suggestions button')).toHaveCount(2);
  expect(await ui.locator('html').evaluate(e => e.scrollWidth <= e.clientWidth)).toBe(true);
  expect((await ui.locator('textarea').boundingBox()).height).toBeLessThan(120);
  await ui.locator('#thread-composer').scrollIntoViewIfNeeded();
  if (process.env.THREAD_PREVIEW_DIR) await page.screenshot({ path: `${process.env.THREAD_PREVIEW_DIR}/mesh-thread-${width}.png` });
  expect(await page.evaluate(() => window.sends.length)).toBe(0);
});

test('global fullscreen remains context-only even with thread-shaped notification', async ({ page }) => {
  const ui = await open(page, { global: true, peer: 'peer' });
  await expect(ui.locator('#mesh-status')).toContainText('threads returned');
  await ui.getByRole('button', { name: 'peer', exact: true }).click();
  await expect(ui.getByRole('button', { name: 'Continue conversation in chat', exact: true })).toBeVisible();
  await expect(ui.locator('textarea')).toHaveCount(0);
});
