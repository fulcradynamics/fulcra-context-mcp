// Latest records arrive newest first. Protocol acknowledgements are not previews.
export function contactPreview(messages) {
  const message = messages.find(m => ['message', 'reply'].includes(m.record.kind));
  if (!message) return;
  const acknowledged = messages.some(m => m.direction !== message.direction
    && ['ack', 'reply'].includes(m.record.kind) && m.record.in_reply_to === message.record.id);
  return { message, acknowledged };
}
