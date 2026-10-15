// Presentation only: grants/schema discovery remains the source of authority.
export function pendingContacts(discovery) {
  const threads = [], pending = new Map(discovery.pending.map(s => [JSON.stringify([s.fulcra_userid, s.id]), s]));
  const add = (source, thread) => pending.set(JSON.stringify([source.fulcra_userid, source.id]),
    { ...source, peer: thread.peer, state: source.direction === 'Incoming' ? 'Incoming — awaiting connection' : 'Outgoing — awaiting connection' });
  for (const thread of discovery.threads) {
    const sources = thread.sources;
    const peers = thread.expectedPeerUserids ?? [thread.peer];
    const twoWay = sources.some(s => s.direction === 'Outgoing')
      && peers.every(peer => sources.some(s => s.direction === 'Incoming' && s.fulcra_userid === peer));
    if (twoWay) threads.push({ ...thread, sources });
    else for (const source of sources) add(source, thread);
  }
  // Incoming channels already represented in an active multiparty conversation
  // are not separate one-way invitations to each member.
  for (const thread of threads) for (const source of thread.sources) {
    pending.delete(JSON.stringify([source.fulcra_userid, source.id]));
  }
  return { ...discovery, threads, pending: [...pending.values()] };
}

export async function matchInvitations(app) {
  const result = await app.callServerTool({name: 'match_agent_invitations', arguments: {}}, {timeout: 30000});
  const value = result.structuredContent ?? JSON.parse(result.content?.find(c => c.type === 'text')?.text ?? 'null');
  if (result.isError || !Array.isArray(value?.results) || value.status === 'unavailable') throw new Error('Invitation matching unavailable');
  return value.results;
}
