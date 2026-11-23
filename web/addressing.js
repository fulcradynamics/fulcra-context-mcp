import { hostLabel } from './host-label.js';

// Addressing is an agent-name hint, never a verified human identity or access rule.
// Without a choice or one earlier sender name, the host's own name is the assumption.
export function viewingAgent(messages, selected, assumed) {
  if (typeof selected === 'string' && selected.trim()) return selected;
  const names = new Set(messages.filter(m => m.direction === 'Outgoing' && !m.state)
    .map(m => m.record.sender).filter(s => typeof s === 'string' && s.trim()));
  return names.size === 1 ? [...names][0] : assumed;
}

// The sender name to assume: "<the user's saved open-invitation name>'s <host>", the agent name the
// panel's invitations introduce, or else the host's own name, lowercased ("chatgpt", "hermes").
export function hostAgent(app, inviter) {
  const host = app.getHostVersion()?.name?.trim();
  if (inviter) return `${inviter}'s ${hostLabel(host) || 'agent'}`;
  return host?.toLowerCase() || 'agent';
}

export function messageAddressing(record, agent) {
  const recipients = record.recipients;
  if (recipients === undefined || (Array.isArray(recipients) && recipients.includes('all'))) return 'broadcast';
  if (!Array.isArray(recipients) || !recipients.length || !recipients.every(r => typeof r === 'string')) return 'unknown';
  return recipients.includes(agent) ? 'addressed' : 'other';
}
