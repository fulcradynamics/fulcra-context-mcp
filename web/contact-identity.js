// Display-only labels never replace routing or provenance identifiers.
export function readable(value, fallback = 'Unnamed contact') {
  return typeof value === 'string' && value.trim() && !/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i.test(value) ? value : fallback;
}
export const contactName = thread => readable(thread?.identifier || thread?.accountName, thread?.participants ? 'Group conversation' : 'Unnamed contact');

export function contactIdentity(doc, anchor) {
  const button = doc.createElement('button'); button.type = 'button'; button.className = 'identity-info';
  button.textContent = 'ⓘ'; button.setAttribute('aria-label', 'Contact information');
  button.setAttribute('aria-expanded', 'false'); button.setAttribute('aria-controls', 'contact-identity');
  const panel = doc.createElement('div'); panel.id = 'contact-identity'; panel.hidden = true;
  panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', 'Fulcra User ID');
  anchor.append(button, panel);
  let generation = 0;
  const resets = [];
  const close = (focus = false) => { panel.hidden = true; generation++; resets.forEach(reset => reset()); button.setAttribute('aria-expanded', 'false'); if (focus) button.focus(); };
  button.addEventListener('click', () => {
    if (!panel.hidden) { close(); return; }
    panel.hidden = false; button.setAttribute('aria-expanded', 'true'); panel.querySelector('input')?.focus();
  });
  doc.addEventListener('keydown', e => { if (e.key === 'Escape' && !panel.hidden) { e.preventDefault(); close(true); } });
  doc.addEventListener('pointerdown', e => { if (!panel.hidden && !panel.contains(e.target) && !button.contains(e.target)) close(); });
  doc.addEventListener('focusin', e => { if (!panel.hidden && !panel.contains(e.target) && e.target !== button) close(); });
  return thread => {
    const ids = thread.participants?.map(p => p.id) ?? [thread.peer];
    if (panel.dataset.identity === JSON.stringify(ids)) return;
    close(); resets.length = 0; panel.dataset.identity = JSON.stringify(ids); panel.replaceChildren();
    const title = doc.createElement('strong'); title.textContent = 'Fulcra User ID'; panel.append(title);
    for (const id of ids.filter(Boolean)) {
      const row = doc.createElement('div');
      const field = doc.createElement('input'); field.readOnly = true; field.value = id; field.setAttribute('aria-label', 'Fulcra User ID');
      const copy = doc.createElement('button'); copy.type = 'button'; copy.textContent = '⧉'; copy.setAttribute('aria-label', 'Copy ID');
      const status = doc.createElement('p'); status.setAttribute('role', 'status');
      let attempt = 0;
      const reset = () => {
        copy.textContent = '⧉'; copy.classList.remove('copy-success'); copy.setAttribute('aria-label', 'Copy ID');
        copy.disabled = false; status.textContent = '';
      };
      resets.push(reset);
      copy.addEventListener('click', async () => {
        const epoch = generation, currentAttempt = ++attempt;
        reset(); copy.disabled = true;
        const current = () => epoch === generation && currentAttempt === attempt;
        try {
          await doc.defaultView.navigator.clipboard.writeText(id);
          if (!current()) return;
          copy.textContent = '✓'; copy.classList.add('copy-success'); copy.setAttribute('aria-label', 'Copied'); status.textContent = 'Copied';
        } catch {
          if (!current()) return;
          reset();
          status.textContent = 'Could not copy. Select and copy the ID manually.'; field.focus(); field.select();
        } finally {
          if (current()) copy.disabled = false;
        }
      });
      row.append(field, copy, status); panel.append(row);
    }
  };
}
