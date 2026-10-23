// App-instance display state. Never pass these values to conversation actions.
export function createDebugPreview() {
  const contacts = new Map(), listeners = new Set();
  return {
    get: peer => contacts.get(peer) ?? {},
    set(peer, field, value) {
      const next = { ...this.get(peer) };
      if (value === '') delete next[field]; else next[field] = value;
      if (Object.keys(next).length) contacts.set(peer, next); else contacts.delete(peer);
      for (const listener of listeners) listener(peer);
    },
    reset(peer) { contacts.delete(peer); for (const listener of listeners) listener(peer); },
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
  };
}

export function previewAssessment(live, overrides) {
  if (!overrides.status && !overrides.reason) return live;
  if (!overrides.status) return { ...live, reason: overrides.reason };
  if (overrides.status === 'unknown') return { attention: null, reason: null };
  return { ...live, attention: overrides.status === 'attention',
    partial: overrides.status === 'partial', reason: overrides.reason || live?.reason || 'Preview status' };
}

const fields = [
  ['unread', 'Unread state', [['unread', 'Unread'], ['read', 'Read']]],
  ['status', 'Contact status', [['attention', 'Needs attention'], ['clear', 'No action identified'], ['unknown', 'Not assessed'], ['partial', 'Partially assessed']]],
  ['reason', 'Status reason'],
  ['relationship', 'Relationship', [['connected', 'Connected'], ['pending', 'Pending']]],
  ['preview', 'List preview', [['loading', 'Loading'], ['empty', 'Empty'], ['error', 'Unavailable']]],
  ['previewText', 'Preview text'],
  ['time', 'Preview time'],
  ['topic', 'Topic'],
  ['messages', 'Messages', [['incoming', 'Sample incoming'], ['outgoing', 'Sample outgoing'], ['empty', 'Empty'], ['loading', 'Loading'], ['error', 'Read failed']]],
  ['body', 'Message body'],
  ['delivery', 'Message delivery', [['sending', 'Sending'], ['posted', 'Posted'], ['uncertain', 'Unconfirmed']]],
  ['ack', 'Acknowledgement', [['sending', 'Marking read'], ['posted', 'Marked read'], ['rejected', 'Rejected'], ['uncertain', 'Unconfirmed']]],
];

export function previewMessages(live, overrides) {
  if (['empty', 'loading'].includes(overrides.messages)) return [];
  if (['incoming', 'outgoing'].includes(overrides.messages)) return [{
    source: { id: 'debug-preview', fulcra_userid: 'debug-preview' },
    direction: overrides.messages === 'incoming' ? 'Incoming' : 'Outgoing',
    record: { id: 'debug-preview', sender: 'Preview agent', kind: 'message', body: overrides.body || 'Preview message',
      start_time: '2026-01-01T12:00:00Z' },
    state: overrides.messages === 'outgoing' ? overrides.delivery : undefined,
  }];
  if (!overrides.body && !overrides.delivery) return live;
  return live.map(message => ({ ...message,
    record: overrides.body ? { ...message.record, body: overrides.body } : message.record,
    state: message.direction === 'Outgoing' ? overrides.delivery || message.state : message.state,
  }));
}

export const acknowledgementPreview = {
  sending: 'Marking message read…', posted: 'Message marked read.',
  rejected: 'Could not mark message read. Reopen the contact to try again.',
  uncertain: 'Acknowledgement unconfirmed. Check live state before retrying.',
};

export function setupDebugControls(doc, preview, selectedPeer) {
  if (doc.querySelector('meta[name="connection-debug"]')?.content !== 'true') return () => {};
  const section = doc.createElement('details'); section.id = 'debug-preview';
  const summary = doc.createElement('summary'); summary.textContent = 'Debug';
  const help = doc.createElement('p'); help.className = 'meta';
  help.textContent = 'Display only, for this contact and app instance. Actions and agent context always use live data.';
  const grid = doc.createElement('div'); grid.className = 'debug-fields';
  const controls = new Map();
  for (const [key, text, options] of fields) {
    const label = doc.createElement('label'); label.textContent = text;
    const input = doc.createElement(options ? 'select' : 'input');
    input.setAttribute('aria-label', text);
    if (options) for (const [value, name] of [['', 'Live'], ...options]) {
      const option = doc.createElement('option'); option.value = value; option.textContent = name; input.append(option);
    }
    else { input.type = 'text'; input.maxLength = 160; input.placeholder = 'Live'; }
    input.addEventListener(options ? 'change' : 'input', () => {
      if (selectedPeer()) preview.set(selectedPeer(), key, input.value);
    });
    controls.set(key, input); label.append(input); grid.append(label);
  }
  const reset = doc.createElement('button'); reset.type = 'button'; reset.textContent = 'Reset to live';
  reset.addEventListener('click', () => preview.reset(selectedPeer()));
  section.append(summary, help, grid, reset);
  doc.querySelector('#advanced-panel').append(section);
  const banner = doc.createElement('p'); banner.id = 'debug-preview-active'; banner.className = 'meta'; banner.hidden = true;
  banner.setAttribute('role', 'status');
  banner.textContent = 'Debug preview active — display only. Actions use live data.';
  doc.querySelector('#advanced-panel').after(banner);
  return () => {
    const overrides = preview.get(selectedPeer());
    banner.hidden = !Object.keys(overrides).length;
    reset.disabled = banner.hidden;
    for (const [key, input] of controls) if (doc.activeElement !== input) input.value = overrides[key] ?? '';
  };
}
