import { discoverThreads } from './meshes.js';
import { parseRecords } from './records.js';

const timestamp = record => {
  const raw = record.recorded_at ?? record.start_time;
  const time = typeof raw === 'string' ? Date.parse(raw) : NaN;
  return Number.isFinite(time) ? time : Infinity;
};

export async function readConversation(app, selected, range, isCurrent = () => true) {
  let discovery;
  try {
    discovery = await discoverThreads(app);
  } catch {
    if (!isCurrent()) return;
    throw new Error('Thread discovery failed (get_data_catalog/list_shares or missing own user ID). No cached channels were read.');
  }
  if (!isCurrent()) return;
  const thread = discovery.threads.find(t => t.peer === selected.peer);
  if (!thread) throw new Error('Peer thread no longer available in refreshed discovery. No cached channels were read.');
  const results = await Promise.all(thread.sources.map(async ({ direction, ...source }) => {
    const label = `${direction} (${source.fulcra_userid} / ${source.id})`;
    try {
      const args = { data_type: source.id, ...range };
      if (direction === 'Incoming') args.fulcra_userid = source.fulcra_userid;
      const result = await app.callServerTool({ name: 'get_records', arguments: args }, { timeout: 30000 });
      const { records, truncated } = parseRecords(result, source.id);
      return { messages: records.map(record => ({ record, source, direction })), warning: truncated
        ? `Partial result — ${label} truncated. Narrow the date range to see the rest.` : undefined };
    } catch {
      return { messages: [], warning: `Could not load messages — ${label} (get_records failed or returned an invalid result). Conversation incomplete; retry Load messages.` };
    }
  }));
  if (!isCurrent()) return;
  const warnings = [...thread.warnings, ...results.flatMap(r => r.warning ? [r.warning] : [])];
  const messages = results.flatMap(r => r.messages).sort((a, b) => timestamp(a.record) - timestamp(b.record));
  return { messages, warnings };
}
