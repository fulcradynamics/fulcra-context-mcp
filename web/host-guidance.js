// Store only a UI preference: never account IDs, drafts, or message contents.
const key = 'fulcra.contacts.hide-host-guidance';
let suppressed = false;
export function showHostGuidance(doc, host, returnFocus) {
  try { suppressed ||= doc.defaultView.localStorage.getItem(key) === '1'; } catch { /* Opaque sandbox origin. */ }
  if (suppressed) return;
  doc.querySelector('#host-guidance')?.remove();
  const dialog = doc.createElement('dialog'); dialog.id = 'host-guidance'; dialog.setAttribute('aria-label', 'Continue in host chat');
  const text = doc.createElement('p');
  text.textContent = `Your request was sent to ${host || 'your host'}. Expand its input to see the conversation and check for a response.`;
  const ok = doc.createElement('button'); ok.type = 'button'; ok.textContent = 'OK';
  const never = doc.createElement('button'); never.type = 'button'; never.textContent = "Don't show again";
  const close = () => { dialog.close(); dialog.remove(); if (returnFocus.isConnected) returnFocus.focus(); };
  ok.addEventListener('click', close);
  never.addEventListener('click', () => { suppressed = true; try { doc.defaultView.localStorage.setItem(key, '1'); } catch { /* Lifetime fallback above. */ } close(); });
  dialog.addEventListener('cancel', e => { e.preventDefault(); close(); });
  dialog.append(text, ok, never); doc.body.append(dialog); dialog.showModal(); ok.focus();
}
