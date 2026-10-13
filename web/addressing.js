// Addressing is an agent-name hint, never a verified human identity or access rule.
export function viewingAgent(messages, selected) {
  if (typeof selected === 'string' && selected.trim()) return selected;
  const names = new Set(messages.filter(m => m.direction === 'Outgoing' && !m.state)
    .map(m => m.record.sender).filter(s => typeof s === 'string' && s.trim()));
  return names.size === 1 ? [...names][0] : 'chatgpt';
}

export function messageAddressing(record, agent) {
  const recipients = record.recipients;
  if (recipients === undefined || (Array.isArray(recipients) && recipients.includes('all'))) return 'broadcast';
  if (!Array.isArray(recipients) || !recipients.length || !recipients.every(r => typeof r === 'string')) return 'unknown';
  return recipients.includes(agent) ? 'addressed' : 'other';
}
