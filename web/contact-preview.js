// Latest records arrive newest first. Protocol acknowledgements are not previews.
export function contactPreview(messages) {
  const message = messages.find(m => ['message', 'reply'].includes(m.record.kind));
  if (!message) return;
  const acknowledged = messages.some(m => m.direction !== message.direction
    && ['ack', 'reply'].includes(m.record.kind) && m.record.in_reply_to === message.record.id);
  return { message, acknowledged };
}

// List order: needs attention, then unread, then most recent; rows without a
// readable message last.
export function compareRows(a, b) {
  const at = r => Number.isFinite(r.lastAt) ? r.lastAt : -Infinity;
  return !!b.attention - !!a.attention || !!b.unread - !!a.unread || at(b) - at(a);
}
