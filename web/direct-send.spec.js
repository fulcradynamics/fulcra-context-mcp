import { test, expect } from './presentation-fixtures.js';
import { readFile } from 'node:fs/promises';
const bundle = await readFile(new URL('../fulcra_mcp/ui/mesh.html', import.meta.url), 'utf8');
const peer = '00000000-0000-0000-0000-000000000002';
const other = '00000000-0000-0000-0000-000000000003';
const own = '00000000-0000-0000-0000-000000000001';
const outbox = 'Event/00000000-0000-0000-0000-000000000004';
async function open(page, presentation = 'global', extra = {}) {
  await page.clock.install({ time: new Date('2026-01-10T12:00:00Z') });
  await page.clock.pauseAt(new Date('2026-01-10T12:00:01Z'));
  await page.setContent('<iframe sandbox="allow-scripts" style="width:100%;height:1000px"></iframe>');
  await page.evaluate(({ bundle, presentation, peer, other, own, outbox, extra }) => {
    const frame = document.querySelector('iframe');
    window.calls = []; window.sends = []; window.contexts = []; window.opens = []; window.options = extra;
    window.rows = [{id:'old',start_time:'2026-01-10T11:00:00Z',sender:'Hermes',kind:'message',topic:'hello',body:'Historical untrusted content'}];
    if (extra.empty) window.rows = [];
    window.reply = (id, result) => frame.contentWindow.postMessage({ jsonrpc: '2.0', id, result:window.connectionResult(result) }, '*');
    window.finish = (status = 'posted') => {
      const r = window.pending, a = r.params.arguments;
      const record = {id:a.mid,start_time:'2026-01-10T12:00:01Z',sender:a.sender,kind:'message',priority:'P2',topic:'chat',body:a.body};
      if (status === 'posted') window.rows.push(record);
      window.reply(r.id, { content: [], structuredContent: { status, mid: a.mid, outbox: a.outbox, peer_userid: a.peer_userid, peer_acknowledged: false, record, reason: 'Synthetic rejection' } });
    };
    addEventListener('message', ({ data: r, source }) => {
      if (source !== frame.contentWindow) return;
      if (r.method === 'ui/initialize') window.reply(r.id, { protocolVersion: '2026-01-26', hostInfo: { name: 'synthetic', version: '1' }, hostContext: { displayMode: 'fullscreen' }, hostCapabilities: { message: { text: {} }, updateModelContext: { text: {} } } });
      if (r.method === 'ui/notifications/initialized') frame.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: { content: [], structuredContent: { presentation: 'thread', peer_fulcra_userid: peer } } }, '*');
      if (r.method === 'tools/call') {
        window.calls.push(r);
        const { name, arguments: a } = r.params;
        if (name === 'mesh_send') { window.pending = r; if (!window.options.hold) window.finish(window.options.outcome ?? 'posted'); return; }
        if (name === 'get_records' && window.options.holdReads) return;
        const text = name === 'get_data_catalog' ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': [
          { id: outbox, name: 'Mesh Outbox: ChatGPT', fulcra_userid: own, description: (extra.session ? `[connection_setup_session: "${extra.session}"]\n` : '') + '[mesh_identifier: "Treecle"]' },
          ...(extra.secondSession ? [{ id: 'Event/second', name: 'Mesh Outbox: Second', fulcra_userid: own, description: `[connection_setup_session: "${extra.secondSession}"]\n[mesh_identifier: "Treecle"]` }] : []),
          { id: 'Event/in', name: 'Mesh Outbox', fulcra_userid: other },
          ...(extra.incoming ? [{ id: 'Event/peer-in', name: 'Mesh Outbox', fulcra_userid: peer }] : []),
        ] }) : name === 'list_shares' ? 'Shares: ' + JSON.stringify({ own_fulcra_userid: own, incoming: [], outgoing: window.options.revoke ? [] : [outbox, ...(extra.secondSession ? ['Event/second'] : [])].map(id => ({ data_types: [id], with_user_ids: [peer], share_all_data: false })) })
          : `Records for ${a.data_type} from start to end: ` + JSON.stringify(a.data_type === outbox ? window.rows : []);
        window.reply(r.id, { content: [{ type: 'text', text }] });
      }
      if (r.method === 'ui/message') { window.sends.push(r); window.reply(r.id, {}); }
      if (r.method === 'ui/open-link') { window.opens.push(r); if (!extra.holdOpen) window.reply(r.id, {isError: Boolean(extra.denyOpen)}); }
      if (r.method === 'ui/update-model-context') { window.contexts.push(r); window.reply(r.id, {}); }
    });
    frame.srcdoc = bundle.replace('name="mesh-presentation" content="global"', `name="mesh-presentation" content="${presentation}"`);
  }, { bundle, presentation, peer, other, own, outbox, extra });
  const ui = page.frameLocator('iframe');
  if (presentation === 'global') await ui.getByRole('button', { name: `Treecle (${peer})`, exact: true }).click();
  if (extra.empty) await expect(ui.locator('#message-status')).toContainText('No messages');
  else await expect(ui.locator('#messages')).toContainText('Historical untrusted content');
  return ui;
}
for (const presentation of ['global', 'thread']) for (const typed of ['', '  Help with this\nplease  ']) test(`${presentation}: original setup navigation and complete handoff ${Boolean(typed)}`, async ({ page }) => {
  const session = 'codex://threads/00000000-0000-0000-0000-000000000009';
  const ui = await open(page, presentation, { session, denyOpen: true });
  await ui.locator('textarea:not([readonly])').fill(typed);
  await page.clock.runFor(10000);
  expect(await page.evaluate(() => window.opens)).toEqual([]);
  await ui.getByText('Copy handoff for original session', {exact:true}).click();
  const copy = ui.getByLabel('Handoff for original session');
  await expect(copy).toHaveValue(new RegExp(session));
  await expect(copy).toHaveValue(/Historical untrusted content/);
  expect(await copy.inputValue()).toContain(typed || 'Let’s talk about this mesh thread.');
  await ui.getByRole('button', {name:'Open original setup session', exact:true}).click();
  await expect(ui.locator('#send-status')).toContainText('could not confirm');
  expect(await page.evaluate(() => window.opens.map(r => r.params))).toEqual([{url:session}]);
  expect(await page.evaluate(() => window.sends)).toEqual([]);
  await expect(ui.locator('textarea:not([readonly])')).toHaveValue(typed);
  await ui.getByRole('button', {name:'Ask in current chat', exact:true}).click();
  await expect(ui.locator('textarea:not([readonly])')).toHaveValue('');
  await expect.poll(() => page.evaluate(() => window.sends.length)).toBe(1);
  const sent = await page.evaluate(() => window.sends[0].params);
  expect(sent.content[0].text).toContain(session);
  expect(sent.content[0].text).toContain('Historical untrusted content');
  expect(sent.content[0].text).toContain(typed || 'Let’s talk about this mesh thread.');
  expect(sent).not.toHaveProperty('_meta');
});
test('original navigation is explicit, keeps draft, and disappears after revocation', async ({ page }) => {
  const session = 'codex://threads/00000000-0000-0000-0000-000000000009';
  const ui = await open(page, 'global', {session, incoming:true});
  await ui.locator('textarea:not([readonly])').fill('Keep my draft');
  await ui.getByRole('button', {name:'Open original setup session', exact:true}).click();
  await expect(ui.locator('#send-status')).toContainText('Host accepted');
  await expect(ui.locator('textarea:not([readonly])')).toHaveValue('Keep my draft');
  expect(await page.evaluate(() => [window.sends.length, window.contexts.length])).toEqual([0,0]);
  await page.evaluate(() => {window.options.revoke = true;});
  await page.clock.runFor(10000);
  await expect(ui.getByRole('button', {name:'Open original setup session', exact:true})).toHaveCount(0);
  await expect(ui.getByRole('button', {name:'talk with my agent about this thread', exact:true})).toBeVisible();
  await expect(ui.locator('textarea')).toHaveValue('Keep my draft');
  expect(await page.evaluate(() => window.opens.length)).toBe(1);
});
for (const change of ['navigation', 'outbox', 'outbox roundtrip', 'revocation']) for (const rejected of [false, true]) test(`delayed original navigation: ${change}, rejected=${rejected}`, async ({ page }) => {
  const session = 'codex://threads/00000000-0000-0000-0000-000000000009';
  const secondSession = 'codex://threads/00000000-0000-0000-0000-000000000008';
  const multiple = change.startsWith('outbox');
  const ui = await open(page, 'global', { session, holdOpen: true, incoming: true, ...(multiple ? { secondSession } : {}) });
  if (multiple) {
    await expect(ui.getByRole('button', {name:'Open original setup session', exact:true})).toHaveCount(0);
    await ui.getByText('Delivery address', {exact:true}).click();
    await ui.getByRole('combobox', {name:/Your outbox/}).selectOption('Event/second');
    await expect(ui.getByLabel('Handoff for original session')).toHaveValue(new RegExp(secondSession));
  }
  await ui.locator('textarea:not([readonly])').fill('Keep this draft');
  await ui.getByRole('button', {name:'Open original setup session', exact:true}).click();
  await expect.poll(() => page.evaluate(() => window.opens.length)).toBe(1);
  expect(await page.evaluate(() => window.opens[0].params)).toEqual({url: multiple ? secondSession : session});
  if (change === 'navigation') {
    await ui.getByRole('button', {name:'Back to threads'}).click();
    await ui.getByRole('button', {name:other, exact:true}).click();
  } else if (multiple) {
    await ui.getByRole('combobox', {name:/Your outbox/}).selectOption(outbox);
    if (change === 'outbox roundtrip') await ui.getByRole('combobox', {name:/Your outbox/}).selectOption('Event/second');
    await expect(ui.getByLabel('Handoff for original session')).toHaveValue(new RegExp(change === 'outbox' ? session : secondSession));
  } else {
    await page.evaluate(() => { window.options.revoke = true; });
    await page.clock.runFor(10000);
    await expect(ui.getByRole('button', {name:'Open original setup session', exact:true})).toHaveCount(0);
  }
  // A later display owns this shared status; the old host response must not replace it.
  await ui.locator('#send-status').evaluate(el => { el.textContent = 'Current display status'; });
  await page.evaluate(rejected => {
    const id = window.opens[0].id;
    if (rejected) document.querySelector('iframe').contentWindow.postMessage({jsonrpc:'2.0', id, error:{code:-32000, message:'Synthetic rejection'}}, '*');
    else window.reply(id, {});
  }, rejected);
  const handoff = ui.getByRole('button', {name:multiple ? 'Ask in current chat' : 'talk with my agent about this thread', exact:true});
  await expect(handoff).toBeEnabled(); // Completion must release the app-wide pending lock.
  await expect(ui.locator('#send-status')).toHaveText('Current display status');
  if (change !== 'navigation') await expect(ui.locator('textarea:not([readonly])')).toHaveValue('Keep this draft');
  expect(await page.evaluate(() => [window.sends.length, window.contexts.length])).toEqual([0, 0]);
});
test('unsafe setup URL retains the exact no-link handoff', async ({ page }) => {
  const ui = await open(page, 'global', {session:'https://chatgpt.com/share/secret'});
  await expect(ui.getByRole('button', {name:'Open original setup session', exact:true})).toHaveCount(0);
  await ui.locator('textarea').fill('  Exact request  ');
  await ui.getByRole('button', {name:'talk with my agent about this thread', exact:true}).click();
  await expect.poll(() => page.evaluate(() => window.sends.length)).toBe(1);
  expect(await page.evaluate(() => window.sends[0].params.content[0].text)).toBe('  Exact request  ');
  expect(await page.evaluate(() => window.opens.length)).toBe(0);
});
for (const presentation of ['global', 'thread']) test(`${presentation}: direct exact send, optimistic badge, polling reconciliation, no LLM`, async ({ page }) => {
  const ui = await open(page, presentation, { hold: true });
  await expect(ui.getByLabel(`Talk to Treecle (${peer})`, { exact: true })).toBeVisible();
  await ui.locator('textarea').fill('  Hello directly\nwith whitespace  ');
  await ui.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(ui.locator('#messages')).toContainText('sending…');
  await expect(ui.locator('textarea')).toHaveValue('');
  await expect(ui.getByRole('button', { name: 'Send', exact: true })).toBeDisabled();
  expect(await page.evaluate(() => [window.sends.length, window.contexts.length])).toEqual([0, 0]);
  await page.clock.runFor(10000);
  await expect(ui.locator('#messages')).toContainText('sending…');
  await page.evaluate(() => window.finish());
  await expect(ui.locator('textarea')).toHaveValue('');
  await expect(ui.locator('#send-status')).toContainText('Posted');
  await expect(ui.locator('#messages')).not.toContainText('sending…');
  await page.clock.runFor(10000);
  await expect(ui.locator('#messages li')).toHaveCount(2);
  expect(await page.evaluate(() => window.calls.filter(r => r.params.name === 'mesh_send').length)).toBe(1);
  expect(await page.evaluate(() => window.pending.params.arguments)).toMatchObject({ peer_userid: peer, outbox, sender: 'Hermes', body: '  Hello directly\nwith whitespace  ' });
});
test('sending badge stays readable on narrow screens', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 1100 });
  const ui = await open(page, 'global', { hold: true });
  await ui.locator('textarea').fill('Hello directly');
  await ui.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(ui.locator('.send-badge')).toHaveCSS('white-space', 'nowrap');
  await expect(ui.locator('.send-badge')).toHaveCSS('flex-shrink', '0');
});
for (const outcome of ['rejected', 'uncertain']) test(`${outcome}: draft preserved and no automatic duplicate`, async ({ page }) => {
  const ui = await open(page, 'global', { outcome });
  await ui.locator('textarea').fill('keep this');
  await ui.getByRole('button', { name: 'Send', exact: true }).click();
  if (outcome === 'uncertain') {
    await page.clock.runFor(59999);
    await expect(ui.locator('.send-badge')).toHaveText('sending…');
    await expect(ui.locator('#send-status')).not.toContainText('unconfirmed');
    await page.clock.runFor(1);
    await expect(ui.locator('.send-badge')).toHaveText('unconfirmed');
  }
  await expect(ui.locator('#send-status')).toContainText(outcome === 'rejected' ? 'not posted' : 'unconfirmed');
  await expect(ui.locator('textarea')).toHaveValue('keep this');
  if (outcome === 'uncertain') await expect(ui.getByRole('button', { name: 'Send', exact: true })).toBeDisabled();
  await page.clock.runFor(10000);
  expect(await page.evaluate(() => window.calls.filter(r => r.params.name === 'mesh_send').length)).toBe(1);
});
test('delayed uncertainty uses click-time deadline without overwriting another peer handoff', async ({ page }) => {
  const ui = await open(page, 'global', { hold: true });
  await ui.locator('textarea').fill('keep this');
  await ui.getByRole('button', { name: 'Send', exact: true }).click();
  await page.clock.runFor(20000);
  await page.evaluate(() => window.finish('uncertain'));
  await expect(ui.locator('#send-status')).toContainText('Waiting for confirmation');
  await ui.getByRole('button', { name: 'Back to threads' }).click();
  await ui.getByRole('button', { name: other, exact: true }).click();
  await ui.getByRole('button', { name: 'talk with my agent about this thread', exact: true }).click();
  await expect(ui.locator('#send-status')).toContainText('Request accepted');
  await page.clock.runFor(40000);
  await expect(ui.locator('#send-status')).toContainText('Request accepted');
  await ui.getByRole('button', { name: 'Back to threads' }).click();
  await ui.getByRole('button', { name: `Treecle (${peer})`, exact: true }).click();
  await expect(ui.locator('.send-badge')).toHaveText('unconfirmed');
  await expect(ui.locator('textarea')).toHaveValue('keep this');
  expect(await page.evaluate(() => window.calls.filter(r => r.params.name === 'mesh_send').length)).toBe(1);
});
test('late direct completion preserves other peer and newer draft', async ({ page }) => {
  const ui = await open(page, 'global', { hold: true });
  await ui.locator('textarea').fill('first'); await ui.getByRole('button', { name: 'Send', exact: true }).click();
  await ui.locator('textarea').fill('new draft');
  await ui.getByRole('button', { name: 'Back to threads' }).click();
  await ui.getByRole('button', { name: other, exact: true }).click();
  await ui.locator('textarea').fill('other draft');
  await page.evaluate(() => window.finish());
  await expect(ui.locator('textarea')).toHaveValue('other draft');
  await expect(ui.locator('#messages')).not.toContainText('first');
  await expect(ui.locator('#send-status')).toContainText(peer);
  await ui.getByRole('button', { name: 'Back to threads' }).click();
  await ui.getByRole('button', { name: `Treecle (${peer})`, exact: true }).click();
  await expect(ui.locator('textarea')).toHaveValue('new draft');
});
test('missing agent requires explicit routing, partial revocation immediately removes optimistic context', async ({ page }) => {
  const ui = await open(page, 'global', { hold: true, empty: true, incoming: true });
  await ui.locator('textarea').fill('pending first message');
  await expect(ui.getByRole('button', { name: 'Send', exact: true })).toBeEnabled();
  await ui.getByText('Delivery address', { exact: true }).click();
  await ui.getByLabel('Your sending agent name').fill('Hermes');
  await ui.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(ui.locator('#messages')).toContainText('pending first message');
  await page.evaluate(() => { window.options.revoke = true; window.options.holdReads = true; });
  await page.clock.runFor(10000);
  await expect(ui.locator('#thread-context')).not.toContainText('pending first message');
  await expect(ui.locator('#messages')).not.toContainText('pending first message');
});

test('revoked peer removes optimistic content, even after late write response', async ({ page }) => {
  const ui = await open(page, 'global', { hold: true });
  await ui.locator('textarea').fill('private pending text');
  await ui.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(ui.locator('#messages')).toContainText('private pending text');
  await page.evaluate(() => { window.options.revoke = true; });
  await page.clock.runFor(10000);
  await expect(ui.locator('#message-status')).toContainText('no longer available');
  await expect(ui.locator('#messages')).not.toContainText('private pending text');
  await expect(ui.locator('#thread-context')).not.toContainText('private pending text');
  await page.evaluate(() => window.finish());
  await expect(ui.locator('#send-status')).toContainText('Posted');
  await expect(ui.locator('#messages')).not.toContainText('private pending text');
  await expect(ui.getByRole('button', { name: 'Send', exact: true })).toBeDisabled();
});

test('readback during the grace period confirms immediately and stays confirmed past the deadline', async ({ page }) => {
  const ui = await open(page, 'global', { outcome: 'uncertain' });
  await ui.locator('textarea').fill('recover me');
  await ui.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(ui.locator('.send-badge')).toHaveText('sending…');
  await page.evaluate(() => window.finish('posted'));
  await page.clock.runFor(10000);
  await expect(ui.locator('#messages li')).toHaveCount(2);
  await expect(ui.locator('textarea')).toHaveValue('');
  await expect(ui.locator('#send-status')).toContainText('Posted');
  await expect(ui.locator('#send-status')).not.toContainText('unconfirmed');
  await page.clock.runFor(60000);
  await expect(ui.locator('#send-status')).toContainText('Posted');
  await expect(ui.locator('#messages')).not.toContainText('unconfirmed');
});

test('unconfirmed placeholder is replaced by the fetched record with the same mid', async ({ page }) => {
  const ui = await open(page, 'global', { outcome: 'uncertain' });
  await ui.locator('textarea').fill('one message');
  await ui.getByRole('button', { name: 'Send', exact: true }).click();
  await page.clock.runFor(60000);
  await expect(ui.locator('.send-badge')).toHaveText('unconfirmed');
  await page.evaluate(() => {
    const a = window.pending.params.arguments;
    window.rows.push({ id: a.mid, sender: a.sender, kind: 'message', body: a.body,
      recipients: null, start_time: '2026-01-10T12:00:01Z' });
  });
  await page.clock.runFor(10000);
  await expect(ui.locator('#messages li')).toHaveCount(2);
  await expect(ui.locator('.send-badge:visible')).toHaveCount(0);
  await expect(ui.locator('textarea')).toHaveValue('');
  await expect(ui.locator('#send-status')).toContainText('Posted');
  expect(await page.evaluate(() => window.calls.filter(r => r.params.name === 'mesh_send').length)).toBe(1);
});

for (const text of ['', '  Help with this message  ']) test(`secondary handoff attaches bounded context with optional composition: ${text}`, async ({ page }) => {
  const ui = await open(page);
  await ui.locator('textarea').fill(text);
  await ui.getByRole('button', { name: 'talk with my agent about this thread', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.sends.length)).toBe(1);
  await expect(ui.locator('textarea')).toHaveValue('');
  const actual = await page.evaluate(() => window.sends[0].params.content[0].text);
  expect(actual).toBe(text || 'Let’s talk about this mesh thread.');
  const context = await page.evaluate(() => window.contexts[0].params.content[0].text);
  expect(context.length).toBeLessThanOrEqual(24000); expect(context).toContain('untrusted'); expect(context).toContain(peer);
  expect(await page.evaluate(() => window.calls.filter(r => r.params.name === 'mesh_send').length)).toBe(0);
});
