import { parseMeshes } from './meshes.js';
import { parseRecords } from './records.js';

function parseShares(result) {
  if (result.isError) throw new Error('Tool failed');
  const text = result.structuredContent?.result ?? result.content?.find(p => p.type === 'text')?.text;
  if (typeof text !== 'string' || !text.startsWith('Shares: ')) throw new Error('Invalid shares');
  const shares = JSON.parse(text.slice('Shares: '.length));
  if (!shares || !['outgoing', 'incoming'].every(key => Array.isArray(shares[key])
    && shares[key].every(s => s && typeof s === 'object' && !Array.isArray(s)))) throw new Error('Invalid shares');
  return shares;
}

// _slim_share omits empty lists. Never use share names or envelope routing to pair.
function narrow(share) {
  return share.share_all_data === false && !share.group_id
    && ['with_group_ids', 'file_paths', 'file_history_paths'].every(k => share[k] === undefined || (Array.isArray(share[k]) && share[k].length === 0))
    && Array.isArray(share.data_types) && share.data_types.length === 1
    && typeof share.data_types[0] === 'string';
}
function pair(selected, catalog, shares) {
  const same = entry => entry.id === selected.id && entry.fulcra_userid === selected.fulcra_userid;
  if (!catalog.some(same)) return { warning: 'selected outbox missing from refreshed catalog' };
  const outgoing = shares.outgoing.filter(s => narrow(s) && Array.isArray(s.with_user_ids)
    && s.with_user_ids.length === 1 && typeof s.with_user_ids[0] === 'string' && s.with_user_ids[0]
    && s.with_user_ids[0] !== shares.own_fulcra_userid);
  const incoming = shares.incoming.filter(s => narrow(s) && s.grant_type === 'user'
    && typeof s.sharing_fulcra_userid === 'string' && s.sharing_fulcra_userid
    && s.sharing_fulcra_userid !== shares.own_fulcra_userid);
  let peer = selected.fulcra_userid;
  if (!peer) {
    const peers = new Set(outgoing.filter(s => s.data_types[0] === selected.id).map(s => s.with_user_ids[0]));
    if (peers.size !== 1) return { warning: 'missing or ambiguous direct recipient for selected outbox' };
    [peer] = peers;
  } else if (!incoming.some(s => s.sharing_fulcra_userid === peer && s.data_types[0] === selected.id)) {
    return { warning: 'selected outbox has no narrow direct incoming share' };
  }
  const candidates = catalog.filter(entry => selected.fulcra_userid
    ? !entry.fulcra_userid && outgoing.some(s => s.with_user_ids[0] === peer && s.data_types[0] === entry.id)
    : entry.fulcra_userid === peer && incoming.some(s => s.sharing_fulcra_userid === peer && s.data_types[0] === entry.id));
  if (candidates.length !== 1) return { warning: 'missing or ambiguous counterpart for this peer' };
  const ownId = selected.fulcra_userid ? candidates[0].id : selected.id;
  // Narrow grants establish a peer, but must not hide wider access to that
  // same channel. Such a channel cannot safely be called one conversation.
  const covering = shares.outgoing.filter(s => s.share_all_data === true
    || (Array.isArray(s.data_types) && s.data_types.includes(ownId)));
  if (covering.some(s => !narrow(s) || !Array.isArray(s.with_user_ids)
    || s.with_user_ids.length !== 1 || s.with_user_ids[0] !== peer)) {
    return { warning: 'ambiguous or broad sharing for own outbox' };
  }
  return { counterpart: candidates[0] };
}

const timestamp = record => {
  const raw = record.recorded_at ?? record.start_time;
  const time = typeof raw === 'string' ? Date.parse(raw) : NaN;
  return Number.isFinite(time) ? time : Infinity;
};

export async function readConversation(app, selected, range, isCurrent = () => true) {
  const call = (name, args) => app.callServerTool({ name, arguments: args }, { timeout: 30000 });
  const warnings = [];
  let counterpart;
  try {
    const [catalog, shares] = await Promise.all([
      call('get_data_catalog', { name: 'Mesh Outbox' }).then(parseMeshes),
      call('list_shares', { direction: 'both' }).then(parseShares),
    ]);
    const pairing = pair(selected, catalog, shares);
    counterpart = pairing.counterpart;
    if (pairing.warning) warnings.push(`Conversation incomplete — ${pairing.warning}. Showing selected outbox only.`);
  } catch {
    warnings.push('Conversation unavailable — discovery failed (get_data_catalog/list_shares). Showing selected outbox only.');
  }
  if (!isCurrent()) return { messages: [], warnings };
  const sources = counterpart ? [selected, counterpart] : [selected];
  const results = await Promise.all(sources.map(async source => {
    const direction = source.fulcra_userid ? 'Incoming' : 'Outgoing';
    const label = `${direction} (${source.fulcra_userid ?? 'your outbox'} / ${source.id})`;
    try {
      const args = { data_type: source.id, ...range };
      if (source.fulcra_userid) args.fulcra_userid = source.fulcra_userid;
      const { records, truncated } = parseRecords(await call('get_records', args), source.id);
      return { messages: records.map(record => ({ record, source, direction })), warning: truncated
        ? `Partial result — ${label} truncated. Narrow the date range to see the rest.` : undefined };
    } catch {
      return { messages: [], warning: `Could not load messages — ${label} (get_records failed or returned an invalid result). Conversation incomplete; retry Load messages.` };
    }
  }));
  warnings.push(...results.flatMap(r => r.warning ? [r.warning] : []));
  const messages = results.flatMap(r => r.messages).sort((a, b) => timestamp(a.record) - timestamp(b.record));
  return { messages, warnings };
}
