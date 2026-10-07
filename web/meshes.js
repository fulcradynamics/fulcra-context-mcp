const prefix = 'Available data types, grouped by compatible tool: ';

export function parseMeshes(result) {
  if (result.isError) throw new Error('Tool failed');
  const text = result.structuredContent?.result ?? result.content?.find(p => p.type === 'text')?.text;
  if (typeof text !== 'string' || !text.startsWith(prefix)) throw new Error('Unexpected result');
  const catalog = JSON.parse(text.slice(prefix.length));
  if (!catalog || Array.isArray(catalog) || typeof catalog !== 'object'
    || !Object.values(catalog).every(Array.isArray)) throw new Error('Invalid catalog');
  const entries = Object.entries(catalog)
    .filter(([group]) => group.startsWith('data types usable with: ') && group.slice('data types usable with: '.length).split(' | ').includes('get_records'))
    .flatMap(([, entries]) => entries);
  if (!entries.every(e => e && typeof e.id === 'string' && typeof e.name === 'string'
    && (e.fulcra_userid === undefined || typeof e.fulcra_userid === 'string'))) throw new Error('Invalid entry');
  return [...new Map(entries
    .filter(e => e.id.startsWith('MomentAnnotation/') && /\bmesh outbox\b/i.test(e.name))
    .map(e => [JSON.stringify([e.fulcra_userid ?? '', e.id]), e])).values()]
    .sort((a, b) => a.name.localeCompare(b.name));
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
function directRecipient(share) {
  return share.share_all_data === false && !share.group_id
    && ['with_group_ids', 'file_paths', 'file_history_paths'].every(k => share[k] === undefined || (Array.isArray(share[k]) && share[k].length === 0))
    && Array.isArray(share.data_types) && share.data_types.length === 1
    && Array.isArray(share.with_user_ids) && share.with_user_ids.length === 1
    && typeof share.with_user_ids[0] === 'string' && share.with_user_ids[0];
}

export async function discoverThreads(app) {
  const call = (name, args) => app.callServerTool({ name, arguments: args }, { timeout: 30000 });
  const [catalog, shares] = await Promise.all([
    call('get_data_catalog', { name: 'Mesh Outbox' }).then(parseMeshes),
    call('list_shares', { direction: 'both' }).then(parseShares),
  ]);
  const own = shares.own_fulcra_userid;
  const threads = new Map();
  const seen = new Set();
  let omitted = 0;
  for (const entry of catalog) {
    const owner = entry.fulcra_userid || own;
    const key = JSON.stringify([owner, entry.id]);
    if (seen.has(key)) continue;
    seen.add(key);
    let peer = owner;
    const direction = owner === own ? 'Outgoing' : 'Incoming';
    if (owner === own) {
      const covering = shares.outgoing.filter(s => s.share_all_data === true
        || (Array.isArray(s.data_types) && s.data_types.includes(entry.id)));
      const recipients = covering.map(directRecipient);
      if (!recipients.length || recipients.some(p => !p || p === own || p !== recipients[0])) {
        omitted++;
        continue;
      }
      [peer] = recipients;
    }
    if (!threads.has(peer)) threads.set(peer, { peer, sources: [], warnings: [] });
    threads.get(peer).sources.push({ id: entry.id, fulcra_userid: owner, direction });
  }
  const warnings = omitted ? [`Discovery warning — ${omitted} own outboxes omitted: no unambiguous narrow direct peer (or self-only).`] : [];
  for (const thread of threads.values()) {
    thread.warnings.push(...warnings);
    for (const direction of ['Incoming', 'Outgoing']) {
      if (!thread.sources.some(s => s.direction === direction)) thread.warnings.push(`Conversation incomplete — missing ${direction.toLowerCase()} channel for this peer.`);
    }
  }
  return { threads: [...threads.values()].sort((a, b) => a.peer < b.peer ? -1 : a.peer > b.peer ? 1 : 0), warnings };
}

export async function loadMeshes(app, status, list, onSelect) {
  status.textContent = 'Loading threads — calling get_data_catalog/list_shares…';
  list.replaceChildren();
  try {
    const { threads, warnings } = await discoverThreads(app);
    for (const thread of threads) {
      const row = list.ownerDocument.createElement('li');
      const button = list.ownerDocument.createElement('button');
      button.type = 'button';
      button.textContent = thread.peer;
      button.addEventListener('click', () => onSelect(thread));
      row.append(button);
      list.append(row);
    }
    status.textContent = `get_data_catalog/list_shares completed — ${threads.length} threads returned.${warnings.length ? ' ' + warnings.join(' ') : ''}`;
  } catch {
    list.replaceChildren();
    status.textContent = 'Could not load threads (get_data_catalog/list_shares failed, invalid result, or missing own user ID). Reopen the app to retry.';
  }
}
