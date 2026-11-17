import { discoverThreads } from './connections-discovery.js';
import { parseRecords } from './records.js';

const timestamp = record => {
  const raw = record.recorded_at ?? record.start_time;
  const time = typeof raw === 'string' ? Date.parse(raw) : NaN;
  return Number.isFinite(time) ? time : Infinity;
};

// Latest content plus receipt evidence. A latest read returns ONE record, so
// receipt-ended channels need bounded history, not just client-side filtering.
export async function readLatest(app, sources, now = Date.now(), { resolveContent = true } = {}) {
  return createLatestReader(app, now)(sources, { resolveContent });
}

// One reader per discovered roster. Raw anchors and resolved previews share
// latest requests, but a slow ACK fallback never blocks the history anchor.
export function createLatestReader(app, now = Date.now()) {
  const latest = new Map(), history = new Map();
  async function read(source, range) {
    const args = { data_type: source.id, ...range };
    if (source.direction === 'Incoming') args.fulcra_userid = source.fulcra_userid;
    const { records } = parseRecords(await app.callServerTool({ name: 'get_records', arguments: args }, { timeout: 30000 }), source.id);
    return records;
  }
  return async (sources, { resolveContent = true } = {}) => {
    const results = await Promise.allSettled(sources.map(async ({ direction, identifier: _identifier, setupSession: _setupSession, ...source }) => {
      const key = JSON.stringify([source.fulcra_userid, source.id]);
      const channel = { ...source, direction };
      if (!latest.has(key)) latest.set(key, read(channel, { latest: true }));
      let records = await latest.get(key);
      if (resolveContent && records.some(record => record.kind === 'ack')) {
        if (!history.has(key)) history.set(key, read(channel, {
          start_time: new Date(now - 30 * 86400000).toISOString(), end_time: new Date(now).toISOString(),
        }));
        records = [...records, ...await history.get(key)];
      }
      return records.map(record => ({ record, source, direction }));
    }));
    const failed = results.find(r => r.status === 'rejected');
    if (failed) throw failed.reason;
    return results.flatMap(r => r.value).sort((a, b) => timestamp(b.record) - timestamp(a.record));
  };
}

export async function readConversation(app, selected, range, isCurrent = () => true, { discovery: supplied, previous, now } = {}) {
  let discovery;
  try {
    discovery = supplied ?? await discoverThreads(app);
  } catch {
    if (!isCurrent()) return;
    throw new Error('Thread discovery failed (get_data_catalog/list_shares or missing own user ID). No cached channels were read.');
  }
  if (!isCurrent()) return;
  const thread = discovery.threads.find(t => t.peer === selected.peer);
  if (!thread) throw new Error('Peer thread no longer available in refreshed discovery. No cached channels were read.');
  // Per-channel display metadata never enters record provenance.
  const results = await Promise.all(thread.sources.map(async ({ direction, identifier: _identifier, setupSession: _setupSession, assessment: _assessment, ...source }) => {
    const label = `${direction} (${source.fulcra_userid} / ${source.id})`;
    try {
      const args = { data_type: source.id, ...range };
      if (direction === 'Incoming') args.fulcra_userid = source.fulcra_userid;
      const result = await app.callServerTool({ name: 'get_records', arguments: args }, { timeout: 30000 });
      const { records, truncated } = parseRecords(result, source.id);
      return { messages: records.map(record => ({ record, source, direction, ...(now ? { last_success_at: now } : {}) })), warning: truncated
        ? `Partial result — ${label} truncated. Narrow the date range to see the rest.` : undefined };
    } catch {
      const retained = (previous?.messages ?? []).filter(m => m.source.id === source.id && m.source.fulcra_userid === source.fulcra_userid)
        .map(m => ({ ...m, stale: true }));
      return { messages: retained, warning: `Could not load messages — ${label} (get_records failed or returned an invalid result). Conversation incomplete; retrying automatically.`
        + (retained.length ? ' Stale last-good records retained; access and content not verified current.' : '') };
    }
  }));
  if (!isCurrent()) return;
  const warnings = [...thread.warnings, ...results.flatMap(r => r.warning ? [r.warning] : [])];
  const messages = results.flatMap(r => r.messages).sort((a, b) => timestamp(a.record) - timestamp(b.record));
  return { messages, warnings };
}
