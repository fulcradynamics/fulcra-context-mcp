// Reading selection only: it never establishes membership or changes shares.
import { readable } from './contact-identity.js';
export const sourceKey = source => JSON.stringify([source.fulcra_userid, source.id]);
export const availableSources = thread => thread.availableSources ?? thread.sources;
export function resolveOutbox(thread, id) {
  const outgoing = availableSources(thread).filter(s => s.direction === 'Outgoing')
    .sort((a, b) => (b.sharedAt ?? 0) - (a.sharedAt ?? 0) || a.id.localeCompare(b.id));
  if (id !== undefined) return outgoing.find(s => s.id === id);
  if (outgoing.length > 1 && outgoing.some(s => s.matchedPeers?.length)) return undefined;
  return outgoing[0];
}
export function selectedSources(thread, excluded, outboxId) {
  const available = availableSources(thread), outbox = resolveOutbox(thread, outboxId);
  const outgoing = available.filter(s => s.direction === 'Outgoing');
  const paired = outgoing.some(s => s.matchedPeers?.length);
  let incoming = available.filter(s => s.direction === 'Incoming');
  const sourceWarnings = thread.sourceWarnings ?? thread.warnings;
  const warnings = [...sourceWarnings];
  if (paired && !outbox) {
    incoming = [];
    warnings.push('Choose an outbox in Advanced → Delivery address to read its matched incoming channels.');
  } else if (outbox?.matchedPeers?.length) {
    incoming = incoming.filter(s => outbox.matchedPeers.some(p => p.fulcra_userid === s.fulcra_userid && p.data_type === s.id));
  } else if (excluded === undefined) {
    const ambiguous = incoming.filter(s => incoming.filter(other => other.fulcra_userid === s.fulcra_userid).length > 1);
    if (ambiguous.length) warnings.push('Multiple incoming channels are available. Select which channels to read in Advanced → Available incoming channels.');
    incoming = incoming.filter(s => !ambiguous.includes(s));
  }
  incoming = incoming.filter(s => !excluded?.includes(sourceKey(s)));
  if (excluded?.length) warnings.push('Some available incoming channels were excluded by the viewer.');
  return { ...thread, sourceWarnings, availableSources: available, sources: [
    ...(paired ? (outbox ? [outbox] : []) : outgoing), ...incoming,
  ], warnings: [...new Set(warnings)] };
}
export function incomingSelector(doc, onChange) {
  const details = doc.createElement('details');
  details.className = 'incoming-sources';
  const summary = doc.createElement('summary');
  summary.textContent = 'Available incoming channels';
  const choices = doc.createElement('div');
  details.append(summary, choices);
  let identity;
  return { element: details, update(thread, excluded, outboxId) {
    const sources = availableSources(thread).filter(s => s.direction === 'Incoming');
    details.hidden = !thread.participants && sources.length < 2;
    const selected = selectedSources(thread, excluded, outboxId).sources;
    const outbox = resolveOutbox(thread, outboxId);
    const next = JSON.stringify([sources, selected, outbox]);
    if (next === identity) return;
    identity = next;
    choices.replaceChildren();
    for (const source of sources) {
      const label = doc.createElement('label');
      const checkbox = doc.createElement('input'); checkbox.type = 'checkbox';
      checkbox.checked = selected.some(s => sourceKey(s) === sourceKey(source));
      checkbox.disabled = Boolean(outbox?.matchedPeers?.length && !outbox.matchedPeers.some(p => p.fulcra_userid === source.fulcra_userid && p.data_type === source.id))
        || (!outbox && availableSources(thread).some(s => s.matchedPeers?.length));
      const text = doc.createElement('span');
      text.textContent = `${readable(thread.participants?.find(p => p.id === source.fulcra_userid)?.name, 'Contact')} — ${readable(source.name, 'Incoming channel')} (${sources.indexOf(source) + 1})${source.association === 'matched' ? ' — saved match' : ''}`;
      checkbox.addEventListener('change', () => onChange(sourceKey(source), checkbox.checked));
      label.append(checkbox, text); choices.append(label);
    }
    if (!sources.length) choices.textContent = 'No eligible incoming channels are currently shared with us by these owners.';
  } };
}
