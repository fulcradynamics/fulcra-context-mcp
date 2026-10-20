// Untrusted display data from our own channels only, never live state or authority.
export function parseStatus(description) {
  if (typeof description !== 'string' || description.split('[contact_status:').length !== 2) return null;
  const match = description.split('\n').map(line => line.match(/^\[contact_status: (\{[^\r\n]*\})\]$/)).find(Boolean);
  try {
    const value = JSON.parse(match?.[1]);
    if (!value || Object.keys(value).sort().join(',') !== 'assessed_at,attention,reason'
      || typeof value.attention !== 'boolean' || typeof value.reason !== 'string'
      || !value.reason || [...value.reason].length > 80 || value.reason !== value.reason.trim()
      || /[\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/u.test(value.reason)
      || typeof value.assessed_at !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value.assessed_at)
      || value.assessed_at.startsWith('0000-')
      || new Date(value.assessed_at).toISOString() !== value.assessed_at.replace('Z', '.000Z')) return null;
    return value;
  } catch { return null; }
}

export function aggregateStatus(sources) {
  const own = sources.filter(s => s.direction === 'Outgoing').sort((a,b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  const partial = !own.length || own.some(s => !s.assessment);
  const attention = own.find(s => s.assessment?.attention);
  const chosen = attention ?? (!partial ? own[0] : null);
  return { attention: attention ? true : partial ? null : false, partial,
    reason: chosen?.assessment.reason ?? null,
    // The oldest assessment is the honest lower bound across assessed channels.
    assessed_at: own.map(s => s.assessment?.assessed_at).filter(Boolean).sort()[0] ?? null };
}

export function statusText(status) {
  if (!status || status.attention === null) return status?.assessed_at ? 'Not fully assessed' : 'Not assessed';
  return `Last assessment: ${status.attention ? 'Needs attention' : 'No action identified'} — ${status.reason}`
    + (status.partial ? ' · Some channels not assessed' : '');
}

export function renderStatus(element, status) {
  element.className = 'contact-status' + (status?.attention === true ? ' attention' : '');
  element.textContent = statusText(status);
  element.title = 'Agent’s best-effort last assessment, not live unread or acknowledgement state.'
    + (status?.assessed_at ? ` Oldest assessed channel: ${status.assessed_at}` : '');
}

// Quiet saved assessment; the accessible label distinguishes it from unread.
// Hidden until every own channel has a known assessment (or one needs attention).
export function renderBadge(element, status) {
  const known = status && status.attention !== null && status.reason;
  element.hidden = !known;
  element.replaceChildren();
  if (!known) return;
  element.className = 'status-badge' + (status.attention ? ' attention' : '');
  const kind = element.ownerDocument.createElement('span'); kind.className = 'status-kind';
  kind.textContent = 'Status';
  const reason = element.ownerDocument.createElement('span'); reason.className = 'status-reason';
  reason.textContent = status.reason;
  element.append(kind, reason);
  element.title = statusText(status) + (status.assessed_at ? ` (assessed ${status.assessed_at})` : '');
}
