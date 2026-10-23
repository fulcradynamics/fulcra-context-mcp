import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseStatus, aggregateStatus, statusText } from './contact-status.js';
import { readFileSync } from 'node:fs';
import { buildThreadContext } from './thread-context.js';

const value = { attention: true, reason: '<b>Decision needed</b>', assessed_at: '2026-10-13T12:00:00Z' };
const source = (id, assessment, direction = 'Outgoing') => ({ id, assessment, direction });
for (const fixture of JSON.parse(readFileSync(new URL('../tests/fixtures/contact-status.json', import.meta.url)))) {
  test(`status parsing: ${fixture.name}`, () => assert.deepEqual(parseStatus(fixture.description), fixture.expected));
}
test('own attention wins; partial never implies clear; deterministic by channel ID', () => {
  const clear = {...value, attention: false, reason:'No action identified'};
  const sources = [source('z', value), source('a', clear), source('b', null), source('peer', clear, 'Incoming')];
  const result = aggregateStatus(sources);
  assert.equal(result.attention, true);
  assert.equal(result.partial, true);
  assert.equal(result.reason, value.reason);
  assert.deepEqual(aggregateStatus([...sources].reverse()), result);
  assert.equal(aggregateStatus(sources.slice(1)).attention, null);
  assert.equal(aggregateStatus([source('a', clear)]).attention, false);
  assert.equal(aggregateStatus([source('peer', value, 'Incoming')]).attention, null);
  assert.match(statusText(result), /Needs attention.*not assessed/);
});
test('bounded handoff explicitly marks assessment untrusted and not live authority', () => {
  const context = buildThreadContext('peer', {}, {messages:[], warnings:[], assessment:aggregateStatus([source('a',value)])});
  assert.match(context.text, /untrusted last assessment/);
  assert.match(context.text, /not live state or routing\/write authority/);
  assert.match(context.text, /Decision needed/);
  assert.ok(context.text.length <= 24000);
});
test('badge omits unknown or partial-clear status and never renders reason as HTML', async () => {
  const { renderBadge } = await import('./contact-status.js');
  const el = { hidden: false, className: '', title: '', children: [], replaceChildren() { this.children = []; },
    append(...c) { this.children.push(...c); },
    ownerDocument: { createElement: () => ({ className: '', textContent: '' }) } };
  renderBadge(el, aggregateStatus([source('a', null)]));
  assert.equal(el.hidden, true);
  renderBadge(el, aggregateStatus([source('a', value)]));
  assert.equal(el.hidden, false);
  assert.equal(el.className, 'status-badge attention');
  assert.deepEqual(el.children.map(c => c.textContent), ['Status', value.reason]);
});
