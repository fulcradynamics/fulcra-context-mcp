// Reading selection only: it never establishes membership or changes shares.
export const sourceKey = source => JSON.stringify([source.fulcra_userid, source.id]);
export function selectedSources(thread, excluded = []) {
  return { ...thread, sources: thread.sources.filter(s => s.direction !== 'Incoming' || !excluded.includes(sourceKey(s))),
    warnings: [...thread.warnings, ...(excluded.length ? ['Some available incoming channels were excluded by the viewer.'] : [])] };
}
export function incomingSelector(doc, onChange) {
  const details = doc.createElement('details');
  details.className = 'incoming-sources';
  const summary = doc.createElement('summary');
  summary.textContent = 'Available incoming channels — association unverified';
  const choices = doc.createElement('div');
  details.append(summary, choices);
  let identity;
  return { element: details, update(thread, excluded = []) {
    details.hidden = !thread.participants;
    const sources = thread.sources.filter(s => s.direction === 'Incoming');
    const next = JSON.stringify([sources, excluded]);
    if (next === identity) return;
    identity = next;
    choices.replaceChildren();
    for (const source of sources) {
      const label = doc.createElement('label');
      const checkbox = doc.createElement('input'); checkbox.type = 'checkbox';
      checkbox.checked = !excluded.includes(sourceKey(source));
      const text = doc.createElement('span');
      text.textContent = `${source.name} — owner ${source.fulcra_userid} / ${source.id}`;
      checkbox.addEventListener('change', () => onChange(sourceKey(source), checkbox.checked));
      label.append(checkbox, text); choices.append(label);
    }
    if (!sources.length) choices.textContent = 'No eligible incoming channels are currently shared with us by these owners.';
  } };
}
