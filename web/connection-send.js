export function matchesPost(message, post) {
  return message.record.id === post.envelope.id;
}
export function clearPostedDraft(draft, post) {
  if (draft.version === post.version) { draft.value = ''; draft.version++; }
}
export function reconcilePosts(draft, messages) {
  const confirmed = [];
  draft.posts = (draft.posts ?? []).filter(post => {
    if (!messages.some(m => matchesPost(m, post))) return true;
    if (post.state !== 'posted') confirmed.push(post);
    post.state = 'posted';
    clearPostedDraft(draft, post);
    return false;
  });
  return confirmed;
}
export async function postRecord(app, args) {
  const response = await app.callServerTool({ name: 'agent_connection_send', arguments: args }, { timeout: 30000 });
  const result = response.structuredContent ?? JSON.parse(response.content?.find(c => c.type === 'text')?.text ?? '{}');
  return { response, result };
}
export function messageId() {
  // getRandomValues works in sandboxed app frames without a secure origin.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = [...bytes].map(b => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
