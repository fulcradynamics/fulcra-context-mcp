import { parseContactIdentifier, threadIdentifier, threadTitle } from './contact-identifier.js';
import { LEGACY_OUTBOX_PATTERN, CONVERSION_PREFIX } from './connection-compatibility.js';
import { compatibleSchema } from './connection-schema.js';
import { parseSetupSession } from './setup-session.js';
import { parseStatus, aggregateStatus } from './contact-status.js';

const prefix = 'Available data types, grouped by compatible tool: ';

export function parseConnections(result) {
  if (result.isError) throw new Error('Tool failed');
  const text = result.structuredContent?.result ?? result.content?.find(p => p.type === 'text')?.text;
  if (typeof text !== 'string' || !text.startsWith(prefix)) throw new Error('Unexpected result');
  const catalog = JSON.parse(text.slice(prefix.length));
  if (!catalog || Array.isArray(catalog) || typeof catalog !== 'object'
    || !Object.values(catalog).every(Array.isArray)) throw new Error('Invalid catalog');
  const entries = Object.entries(catalog)
    .filter(([group]) => group.startsWith('data types usable with: ') && group.slice('data types usable with: '.length).split(' | ').includes('get_records'))
    .flatMap(([, entries]) => entries)
    .map(e => e && e.name === undefined ? { ...e, name: e.id } : e);
  if (!entries.every(e => e && typeof e.id === 'string' && typeof e.name === 'string'
    && (e.fulcra_userid === undefined || typeof e.fulcra_userid === 'string'))) throw new Error('Invalid entry');
  return [...new Map(entries
    .filter(e => isConnection(e) || isLegacy(e))
    .map(e => [JSON.stringify([e.fulcra_userid ?? '', e.id]), e])).values()]
    .sort((a, b) => a.name.localeCompare(b.name));
}

export const isConnection = e => e.id.startsWith('Event/') && e.description?.startsWith('connect-agents-with-anyone channel');
const isLegacy = e => e.id.startsWith('MomentAnnotation/') && LEGACY_OUTBOX_PATTERN.test(e.name);
const namedShare = s => s.datashare_name?.startsWith('connect-agents-with-anyone');
const covers = (s, id) => s.share_all_data === true || s.data_types?.some(t => [id, id.split('/')[0], '*', id.split('/')[0] + '/*'].includes(t));

export function conversionSources(description, own, peer) {
  const lines = (description ?? '').split('\n').filter(l => l.startsWith(CONVERSION_PREFIX));
  if (lines.length !== 1) return [];
  try {
    const refs = JSON.parse(lines[0].slice(CONVERSION_PREFIX.length));
    const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
    if (!Array.isArray(refs) || refs.length > 32 || !refs.every(r => r && new RegExp('^MomentAnnotation/' + uuid + '$').test(r.id)
      && [own, peer].includes(r.fulcra_userid))) return [];
    return refs.map(({ id, fulcra_userid }) => ({ id, fulcra_userid }));
  } catch { return []; }
}

function parseShares(result) {
  if (result.isError) throw new Error('Tool failed');
  const text = result.structuredContent?.result ?? result.content?.find(p => p.type === 'text')?.text;
  if (typeof text !== 'string' || !text.startsWith('Shares: ')) throw new Error('Invalid shares');
  const shares = JSON.parse(text.slice('Shares: '.length));
  if (!shares || typeof shares.own_fulcra_userid !== 'string' || !shares.own_fulcra_userid
    || !['outgoing', 'incoming'].every(key => Array.isArray(shares[key])
      && shares[key].every(s => s && typeof s === 'object' && !Array.isArray(s)))) throw new Error('Invalid shares or missing own user ID');
  return shares;
}

// _slim_share omits empty lists. Only exact, single-channel direct grants
// establish outgoing recipients. Inspect ALL covering grants, not just narrow ones.
function directRecipients(share) {
  return share.share_all_data === false && !share.group_id && !share.time_start && !share.time_end
    && ['with_group_ids', 'file_paths', 'file_history_paths'].every(k => share[k] === undefined || (Array.isArray(share[k]) && share[k].length === 0))
    && Array.isArray(share.data_types) && share.data_types.length === 1
    && Array.isArray(share.with_user_ids) && share.with_user_ids.length > 0
    && share.with_user_ids.every(p => typeof p === 'string' && p)
    && share.with_user_ids;
}

export async function discoverThreads(app) {
  const call = async (name, args) => app.callServerTool({ name, arguments: args }, { timeout: 30000 });
  const results = await Promise.allSettled([
    call('get_data_catalog', {}).then(parseConnections),
    call('list_shares', { direction: 'both' }).then(parseShares),
  ]);
  if (results.some(r => r.status === 'rejected')) throw new Error('Thread discovery failed (get_data_catalog/list_shares or missing own user ID). No cached channels were read.');
  const [catalog, shares] = results.map(r => r.value);
  const own = shares.own_fulcra_userid;
  const threads = new Map();
  const legacy = new Map();
  const pending = [];
  const seen = new Set();
  let omitted = 0;
  for (const entry of catalog) {
    const owner = entry.fulcra_userid || own;
    const key = JSON.stringify([owner, entry.id]);
    if (seen.has(key)) continue;
    seen.add(key);
    let peer = owner;
    const direction = owner === own ? 'Outgoing' : 'Incoming';
    const identifier = parseContactIdentifier(entry.description);
    const source = { id: entry.id, name: entry.name, fulcra_userid: owner, direction,
      ...(identifier ? { identifier } : {}) };
    const connection = isConnection(entry);
    if (owner === own) {
      const covering = shares.outgoing.filter(s => covers(s, entry.id));
      if (!covering.length) {
        if (connection) pending.push(source);
        continue;
      }
      const grants = covering.map(s => s.data_types?.[0] === entry.id && directRecipients(s));
      const recipients = [...new Set(grants.flat())].sort();
      if (recipients.some(p => !p || p === own) || recipients.length > 32
        || (!connection && recipients.length !== 1)
        || (connection && !covering.every(namedShare))) {
        omitted++;
        continue;
      }
      [peer] = recipients;
      if (connection && recipients.length > 1) {
        source.expectedPeerUserids = recipients;
        peer = 'connection:' + JSON.stringify([own, ...recipients].sort());
      }
    } else if (!shares.incoming.some(s => s.sharing_fulcra_userid === owner
      && s.grant_type === 'user' && (!connection || namedShare(s)) && !s.share_all_data && !s.group_id && !s.time_start && !s.time_end
      && s.data_types?.length === 1 && s.data_types[0] === entry.id)) {
      omitted++; continue;
    }
    if (connection) {
      const exact = entry.fields ? [entry] : parseConnections(await call('get_data_catalog', { data_type: entry.id, fulcra_userid: owner }));
      const schema = exact.find(e => e.id === entry.id && (e.fulcra_userid || own) === owner);
      if (!schema || !compatibleSchema(schema)) { omitted++; continue; }
      const setupSession = owner === own && parseSetupSession(entry.description);
      if (setupSession) source.setupSession = setupSession;
      if (owner === own) source.assessment = parseStatus(entry.description);
      source.conversionClaims = conversionSources(entry.description, own, peer);
    }
    const collection = connection ? threads : legacy;
    if (!collection.has(peer)) collection.set(peer, { peer, sources: [], warnings: [] });
    collection.get(peer).sources.push(source);
    if (source.expectedPeerUserids) {
      const thread = collection.get(peer);
      thread.participants = [own, ...source.expectedPeerUserids].sort().map(id => {
        const names = new Set(shares.incoming.filter(s => s.sharing_fulcra_userid === id)
          .map(s => s.sharing_fulcra_user_name).filter(n => typeof n === 'string' && n.trim()));
        return { id, name: id === own ? 'You' : names.size === 1 ? [...names][0] : id };
      });
      thread.expectedPeerUserids = source.expectedPeerUserids;
    }
  }
  const warnings = omitted ? [`Discovery warning — ${omitted} own outboxes omitted: no unambiguous narrow direct peer (or self-only).`] : [];
  // Own audience bounds discovery. Incoming grants prove readable owner/type,
  // not association or remote audiences; never follow their outgoing audiences.
  for (const thread of threads.values()) {
    if (!thread.expectedPeerUserids) continue;
    for (const member of thread.expectedPeerUserids) {
      for (const source of threads.get(member)?.sources ?? []) {
        if (source.direction === 'Incoming') thread.sources.push({ ...source, association: 'unverified' });
      }
    }
  }
  for (const thread of threads.values()) {
    const identifier = threadIdentifier(thread.participants ? thread.sources.filter(s => s.direction === 'Outgoing') : thread.sources);
    thread.assessment = aggregateStatus(thread.sources);
    if (identifier) thread.identifier = identifier;
    // tools.py _slim_share exposes an account-owner name, not an agent name.
    const names = new Set(shares.incoming.filter(s => s.sharing_fulcra_userid === thread.peer
      && typeof s.sharing_fulcra_user_name === 'string' && s.sharing_fulcra_user_name.trim())
      .map(s => s.sharing_fulcra_user_name));
    if (names.size === 1) thread.accountName = [...names][0];
    thread.warnings.push(...warnings);
    if (thread.participants) thread.warnings.push('Own audience only. Available incoming channels from these owners are shared with us; their association and remote audiences are not verified. Select which incoming channels to read below. Matching names are not proof.');
    else if (thread.sources.some(s => s.direction === 'Incoming')) thread.warnings.push('Incoming channel co-recipients are not disclosed by the service; this is not a verified complete roster.');
    for (const direction of ['Incoming', 'Outgoing']) {
      if (!thread.sources.some(s => s.direction === direction)) thread.warnings.push(`Conversation incomplete — missing ${direction.toLowerCase()} channel for this peer.`);
    }
  }
  for (const thread of threads.values()) {
    const old = legacy.get(thread.peer);
    // A description is only a claim. Verify owner/type and this exact peer's
    // legacy relationship before exposing history or suppressing conversion.
    for (const source of thread.sources) {
      const verified = (source.conversionClaims ?? []).filter(r => old?.sources.some(s => s.id === r.id && s.fulcra_userid === r.fulcra_userid));
      if (verified.length) source.convertedFrom = verified;
      delete source.conversionClaims;
    }
    thread.convertedFrom = thread.sources.flatMap(s => s.convertedFrom ?? []);
    const converted = new Set(thread.sources.filter(s => s.direction === 'Outgoing')
      .flatMap(s => s.convertedFrom ?? []).map(r => JSON.stringify([r.fulcra_userid,r.id])));
    if (old && old.sources.every(s => converted.has(JSON.stringify([s.fulcra_userid,s.id])))) legacy.delete(thread.peer);
  }
  return { threads: [...threads.values()].sort((a, b) => a.peer < b.peer ? -1 : a.peer > b.peer ? 1 : 0), legacy: [...legacy.values()], pending, warnings };
}

export async function loadConnections(app, status, list, onSelect) {
  status.textContent = 'Loading Agent Contacts — calling get_data_catalog/list_shares…';
  list.replaceChildren();
  try {
    const { threads, warnings } = await discoverThreads(app);
    for (const thread of threads) {
      const row = list.ownerDocument.createElement('li');
      const button = list.ownerDocument.createElement('button');
      button.type = 'button';
      button.textContent = threadTitle(thread);
      button.addEventListener('click', () => onSelect(thread));
      row.append(button);
      list.append(row);
    }
    status.textContent = `get_data_catalog/list_shares completed — ${threads.length} Agent Contacts returned.${warnings.length ? ' ' + warnings.join(' ') : ''}`;
  } catch {
    list.replaceChildren();
    status.textContent = 'Could not load Agent Contacts (get_data_catalog/list_shares failed, invalid result, or missing own user ID). Reopen the app to retry.';
  }
}
