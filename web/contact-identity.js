import { icon, Info, Copy, Check } from './icons.js';

// Display-only labels never replace routing or provenance identifiers.
export function readable(value, fallback = 'Unnamed contact') {
  return typeof value === 'string' && value.trim() && !/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i.test(value) ? value : fallback;
}
export const contactName = thread => readable(thread?.identifier || thread?.accountName, thread?.participants ? 'Group conversation' : 'Unnamed contact');

export function contactIdentity(doc, anchor) {
  const button = doc.createElement('button'); button.type = 'button'; button.className = 'identity-info';
  button.append(icon(Info, 'btn-icon', 16)); button.setAttribute('aria-label', 'Contact information');
  button.setAttribute('aria-expanded', 'false'); button.setAttribute('aria-controls', 'contact-identity');
  const panel = doc.createElement('div'); panel.id = 'contact-identity'; panel.hidden = true;
  panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', 'Fulcra User ID');
  anchor.append(button, panel);
  let generation = 0, pinned = false, restoringFocus = false, closeTimer;
  const resets = [];
  const open = () => {
    clearTimeout(closeTimer);
    panel.hidden = false; button.setAttribute('aria-expanded', 'true');
  };
  const close = (focus = false) => {
    clearTimeout(closeTimer);
    panel.hidden = true; pinned = false; generation++;
    resets.forEach(reset => reset()); button.setAttribute('aria-expanded', 'false');
    if (focus) { restoringFocus = true; button.focus({preventScroll:true}); restoringFocus = false; }
  };
  const leave = () => {
    clearTimeout(closeTimer);
    closeTimer = setTimeout(() => {
      if (!pinned && doc.activeElement !== button && !panel.contains(doc.activeElement)) close();
    }, 180);
  };
  for (const element of [button, panel]) {
    element.addEventListener('pointerenter', e => { if (e.pointerType !== 'touch') open(); });
    element.addEventListener('pointerleave', leave);
  }
  button.addEventListener('focus', () => { if (!restoringFocus) open(); });
  button.addEventListener('click', () => {
    if (pinned && !panel.hidden) { close(); return; }
    pinned = true; open(); panel.querySelector('.identity-id')?.focus({preventScroll:true});
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
      const field = doc.createElement('span'); field.className = 'identity-id'; field.textContent = id; field.tabIndex = 0;
      const copy = doc.createElement('button'); copy.type = 'button'; copy.className = 'identity-copy'; copy.setAttribute('aria-label', 'Copy ID');
      copy.append(icon(Copy, 'btn-icon', 15));
      const status = doc.createElement('p'); status.setAttribute('role', 'status');
      let attempt = 0;
      const showIcon = node => copy.replaceChildren(icon(node, 'btn-icon', 15));
      const selectId = () => {
        const range = doc.createRange(); range.selectNodeContents(field);
        const sel = doc.defaultView.getSelection(); sel.removeAllRanges(); sel.addRange(range); field.focus();
      };
      const reset = () => {
        showIcon(Copy); copy.classList.remove('copy-success'); copy.setAttribute('aria-label', 'Copy ID');
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
          showIcon(Check); copy.classList.add('copy-success'); copy.setAttribute('aria-label', 'Copied'); status.textContent = 'Copied';
        } catch {
          if (!current()) return;
          reset();
          status.textContent = 'Could not copy. Select and copy the ID manually.'; selectId();
        } finally {
          if (current()) copy.disabled = false;
        }
      });
      row.append(field, copy, status); panel.append(row);
    }
  };
}
