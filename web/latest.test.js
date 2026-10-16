import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readLatest } from './conversation.js';
import { contactPreview } from './contact-preview.js';

const now = Date.parse('2026-10-13T13:00:00Z');
const sources = [
  { id: 'Event/in', fulcra_userid: 'peer', direction: 'Incoming' },
  { id: 'Event/out', fulcra_userid: 'me', direction: 'Outgoing' },
];
const record = (id, hour, kind = 'message', in_reply_to) => ({ id, kind, in_reply_to, body: id, start_time: `2026-10-13T${hour}:00:00Z` });
function harness(incoming, outgoing, fault) {
  const calls = [];
  return { calls, app: { async callServerTool({ name, arguments: args }) {
    assert.equal(name, 'get_records');
    calls.push(args);
    assert.equal(args.fulcra_userid, args.data_type === 'Event/in' ? 'peer' : undefined);
    let records = args.data_type === 'Event/in' ? incoming : outgoing;
    if (args.latest) records = records.slice(-1); // Actual backend contract: ONE record.
    else {
      assert.deepEqual(Object.keys(args).sort(), ['data_type', 'end_time', 'start_time', ...(args.fulcra_userid ? ['fulcra_userid'] : [])].sort());
      assert.equal(Date.parse(args.end_time) - Date.parse(args.start_time), 30 * 86400000);
      records = records.filter(r => Date.parse(r.start_time) >= Date.parse(args.start_time) && Date.parse(r.start_time) < Date.parse(args.end_time));
    }
    if (fault === 'error' && !args.latest) throw new Error('offline');
    return { structuredContent: { result: `Records for ${args.data_type} from start to end${fault === 'truncated' ? ' (showing the first 1 of 3)' : ''}: ${JSON.stringify(records)}` } };
  } } };
}

for (const [name, incoming, outgoing, expected, acknowledged] of [
  ['own newer message hidden behind ack', [record('incoming', '10')], [record('outgoing', '11'), record('receipt', '12', 'ack', 'older')], 'outgoing', false],
  ['incoming hidden behind ack', [record('incoming', '10'), record('peer-receipt', '12', 'ack', 'older')], [record('outgoing', '09')], 'incoming', false],
  ['both latest records are acks', [record('incoming', '10'), record('peer-receipt', '12', 'ack', 'older')], [record('outgoing', '09'), record('receipt', '11', 'ack', 'incoming')], 'incoming', true],
  ['relevant receipt hidden behind unrelated ack', [record('incoming', '10')], [record('receipt', '11', 'ack', 'incoming'), record('other-receipt', '12', 'ack', 'older')], 'incoming', true],
]) test(name, async () => {
  const h = harness(incoming, outgoing);
  const summary = contactPreview(await readLatest(h.app, sources, now));
  assert.equal(summary?.message.record.id, expected);
  assert.equal(summary.acknowledged, acknowledged);
  assert.ok(h.calls.some(c => !c.latest));
  assert.ok(h.calls.length <= 4);
});

for (const fault of ['truncated', 'error']) test(`incomplete preview is explicit on ${fault}`, async () => {
  const h = harness([record('incoming', '10')], [record('receipt', '12', 'ack')], fault);
  await assert.rejects(readLatest(h.app, sources, now));
});

test('detail anchoring can read old latest records without resolving a preview', async () => {
  const oldAck = { ...record('receipt', '12', 'ack'), start_time: '2026-01-02T00:00:00Z' };
  const h = harness([oldAck], []);
  const latest = await readLatest(h.app, sources, now, { resolveContent: false });
  assert.equal(latest[0].record.id, 'receipt');
  assert.equal(h.calls.length, 2);
});

test('bounded history does not misrepresent older content as absent', async () => {
  const old = { ...record('old', '10'), start_time: '2026-01-01T00:00:00Z' };
  const h = harness([old, record('receipt', '12', 'ack')], []);
  await assert.rejects(readLatest(h.app, sources, now), /30.day|incomplete/i);
});
