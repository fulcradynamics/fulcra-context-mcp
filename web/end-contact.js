// Ends a single-peer contact like the connection skill: the server deletes our
// narrow grants and verifies none remain; broader shares are untouched.
export async function endContact(app, thread, archive) {
  const outgoing = thread.sources.filter(s => s.direction === 'Outgoing');
  let archived = 0;
  let broaderAccessRemains = false;
  for (const source of outgoing) {
    const result = await app.callServerTool({ name: 'end_agent_contact',
      arguments: { data_type: source.id, peer_userid: thread.peer, archive } }, { timeout: 30000 });
    const value = result.structuredContent;
    if (result.isError || !value?.ended) throw new Error(value?.reason || 'Ending not verified.');
    if (archive && !value.archived) throw new Error(`Narrow contact grants removed; broader shares are unchanged, but archiving was not verified. ${value.reason ?? ''}`.trim());
    archived += value.archived ? 1 : 0;
    broaderAccessRemains ||= value.broader_access_remains === true;
  }
  return { archived, ...(broaderAccessRemains ? { broaderAccessRemains } : {}) };
}

// Resolves { archive } on confirmation, or null when cancelled.
export function confirmEndContact(doc, name, returnFocus) {
  doc.querySelector('#end-contact-dialog')?.remove();
  const dialog = doc.createElement('dialog'); dialog.id = 'end-contact-dialog';
  dialog.setAttribute('aria-labelledby', 'end-contact-title');
  const title = doc.createElement('h2'); title.id = 'end-contact-title'; title.textContent = `End contact with ${name}?`;
  const text = doc.createElement('p');
  text.textContent = `Remove the narrow grants for this contact. Broader shares remain unchanged and may still allow access to your messages. They may already have read earlier ones. What they share with you is not changed.`;
  const label = doc.createElement('label');
  const archive = doc.createElement('input'); archive.type = 'checkbox'; archive.id = 'end-contact-archive';
  label.append(archive, ' Also archive your messages (kept and restorable)');
  const actions = doc.createElement('div'); actions.className = 'dialog-actions';
  const cancel = doc.createElement('button'); cancel.type = 'button'; cancel.textContent = 'Cancel';
  const confirm = doc.createElement('button'); confirm.type = 'button'; confirm.className = 'danger'; confirm.textContent = 'End contact';
  actions.append(cancel, confirm);
  dialog.append(title, text, label, actions); doc.body.append(dialog);
  return new Promise(resolve => {
    const close = value => { dialog.close(); dialog.remove(); if (returnFocus?.isConnected) returnFocus.focus(); resolve(value); };
    cancel.addEventListener('click', () => close(null));
    confirm.addEventListener('click', () => close({ archive: archive.checked }));
    dialog.addEventListener('cancel', e => { e.preventDefault(); close(null); });
    dialog.showModal(); cancel.focus();
  });
}
