const fields = ['id', 'sender', 'kind', 'body', 'recipients', 'topic', 'priority', 'in_reply_to', 'artifacts'];
const sameSource = (a, b) => a.id === b.id && a.fulcra_userid === b.fulcra_userid;
export function recipientAgent(messages, source, peer) {
  const names = new Set(messages.filter(m => m.direction === 'Outgoing' && sameSource(m.source, source))
    .map(m => m.record.sender).filter(s => typeof s === 'string' && s.trim()));
  return names.size === 1 ? [...names][0] : 'chatgpt';
}
export function matchesPost(message, post) {
  return message.direction === 'Outgoing' && sameSource(message.source, post.source)
    && fields.every(k => JSON.stringify(message.record[k]) === JSON.stringify(post.envelope[k]));
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
export function messageId() {
  // getRandomValues works in sandboxed app frames without a secure origin.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = [...bytes].map(b => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
