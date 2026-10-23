// Protocol answers (acks and replies) are the read state; only recent peer
// messages/replies can be acknowledged, so older ones are never unread.
const LOOKBACK = 30 * 86400000;
const time = m => Date.parse(m.record.start_time);

// Unanswered incoming messages/replies, oldest first. `acked` holds IDs whose
// acknowledgement is pending or posted. A rejected attempt stays unread.
export function unreadMessages(messages, acked = new Set(), now = Date.now()) {
  const answered = new Set(messages.filter(m => m.direction === 'Outgoing' && m.record.in_reply_to)
    .map(m => m.record.in_reply_to));
  return messages.filter(m => m.direction === 'Incoming' && ['message', 'reply'].includes(m.record.kind)
    && typeof m.record.id === 'string' && !answered.has(m.record.id)
    && (!acked.has(m.record.id) || acked.get?.(m.record.id)?.state === 'rejected')
    && now - time(m) <= LOOKBACK).sort((a, b) => time(a) - time(b));
}
