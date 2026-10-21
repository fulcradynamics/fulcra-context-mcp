import { getContextLifecycle } from './native-context.js';
import { invitationTemplate } from './invite-template.js';
import { spinButton, showToast } from './toast.js';
import { hostLabel } from './chat-only.js';
import { icon, Copy } from './icons.js';

export const invitationPrompt = 'I want to invite another user to connect our agents through Fulcra. '
  + 'Please use the invite skill to help me prepare the invitation. '
  + 'First offer a single-person invitation or an open invitation I can share with a group. For a single-person invitation, ask for my name and the name of the person I am inviting. '
  + 'Follow the skill’s private invitation procedure using available generic tools. Without secure code execution, the native Invite someone dialog supports single-person only; new open invitations are unavailable on this host. Reuse verified existing prepared open codes and matching when available. Do not loop back to the dialog for open mode or silently downgrade it. Never invent a random code. Show me a copyable invitation prompt for the other person to give their agent, '
  + 'using my verified Fulcra user ID and persisted code and the connection skill URL. Their agent must share its own channel with me and its FIRST message topic must be exactly handshake followed by one space and the code. Do not ask for the other user\'s ID; if I already gave it, share the prepared outbox with exactly that user after preparing the code. '
  + 'This request authorizes you to prepare a dedicated unshared outbox with the identifier <their name>\'s agent (for example Sura Novi\'s agent) and the original setup session URL when available, without another confirmation. '
  + 'Then ask whether I want to add optional context about what the invite is for, so you can personalize the prompt and draft an outgoing message. '
  + 'For a single-person invitation, this request authorizes the skill’s verified matching procedure to share only that prepared outbox back to the authenticated incoming-share owner after a unique first-message code match and independent grant readback. Keep it unshared until that match; unmatched sharing needs my explicit consent. '
  + 'For an open invitation, ask for my name and a meaningful invitation identifier instead of a recipient name. Follow the skill’s open-invitation procedure; use the topic exactly: open_invitation followed by one space and the code, NOT handshake. The template is never shared; matching creates a separate one-to-one outbox per authenticated responder. Use <sender> via <open invitation identifier> as display-only fallback, never for routing. Do not post messages merely to complete matching; response content remains subject to my preferences.';

// Sends one user request to the chat after clearing any attached thread context.
// opts.button: show a spinner on the triggering button instead of an inline
// "Sending…" line. opts.toast: a (message) => void shown on success instead of
// writing the sent message inline. Errors always report inline on status.
export async function requestInChat(app, status, text, sent, opts = {}) {
  const lifecycle = getContextLifecycle(app, status);
  if (lifecycle.pending) return false;
  lifecycle.pending = true; lifecycle.onChange();
  const restore = opts.button ? spinButton(opts.button) : null;
  if (!opts.button) status.textContent = 'Sending request to the conversation…';
  try {
    await lifecycle.invalidate();
    if (!lifecycle.isClear()) throw new Error('Previous thread context not cleared');
    const result = await app.sendMessage({ role: 'user', content: [{ type: 'text', text }] }, { timeout: 15000 });
    if (result.isError) throw new Error('Host rejected message');
    if (opts.toast) { opts.toast(sent); status.textContent = ''; } else status.textContent = sent;
    return true;
  } catch {
    const host = app.getHostVersion?.()?.name;
    status.textContent = host
      ? `Couldn’t send your request to ${host}. Open ${host} to see what went wrong.`
      : 'Couldn’t send your request. Open the chat to see what went wrong.';
    return false;
  } finally {
    restore?.();
    lifecycle.pending = false; lifecycle.onChange();
  }
}

function field(doc, label, name, { optional = false, placeholder = '', help = '' } = {}) {
  const wrap = doc.createElement('label');
  const text = doc.createElement('span'); text.className = 'field-label'; text.textContent = label;
  const input = doc.createElement('input'); input.type = 'text'; input.name = name; input.maxLength = name === 'recipient_userid' ? 36 : 80;
  input.required = !optional; if (placeholder) input.placeholder = placeholder;
  wrap.append(text, input);
  if (help) { const hint = doc.createElement('span'); hint.className = 'field-help'; hint.textContent = help; wrap.append(hint); }
  return [wrap, input];
}

// Prepares a single-person invitation without the model, or hands what the user
// typed to the invite skill in chat. Open invitations stay in chat.
export function openInviteDialog(app, doc, status, returnFocus, handoff = {}) {
  doc.querySelector('#invite-dialog')?.remove();
  const dialog = doc.createElement('dialog'); dialog.id = 'invite-dialog'; dialog.className = 'app-dialog';
  dialog.setAttribute('aria-labelledby', 'invite-title');
  const head = doc.createElement('div'); head.className = 'dialog-head';
  const title = doc.createElement('h2'); title.id = 'invite-title'; title.textContent = 'Invite someone';
  head.append(title);
  const intro = doc.createElement('p'); intro.className = 'dialog-intro';
  intro.textContent = 'Send an invitation so your agents can message each other. It sets up a private connection just for the two of you.';
  const form = doc.createElement('div'); form.className = 'dialog-form';
  const [inviterLabel, inviter] = field(doc, 'Your name', 'inviter_name', { placeholder: 'e.g. Jordan' });
  const [recipientLabel, recipient] = field(doc, 'Their name', 'recipient_name', { placeholder: 'e.g. Alex' });
  const [idLabel, userid] = field(doc, 'Fulcra User ID (if you know it)', 'recipient_userid',
    { optional: true, placeholder: 'Optional', help: 'If you have it, you’ll connect right away. Otherwise they’ll get an invitation to accept.' });
  const error = doc.createElement('p'); error.className = 'dialog-error'; error.setAttribute('role', 'alert');
  const actions = doc.createElement('div'); actions.className = 'dialog-actions';
  const cancel = doc.createElement('button'); cancel.type = 'button'; cancel.className = 'dialog-ghost'; cancel.textContent = 'Cancel';
  const create = doc.createElement('button'); create.type = 'button'; create.className = 'primary'; create.textContent = 'Create invitation';
  actions.append(cancel, create);
  form.append(inviterLabel, recipientLabel, idLabel, error, actions);
  // Footer note: more invitations are always available by asking the host in chat.
  const host = hostLabel(app.getHostVersion()?.name) || 'chat';
  const alt = doc.createElement('div'); alt.className = 'dialog-alt';
  alt.hidden = !app.getHostCapabilities()?.message?.text;
  const altText = doc.createElement('p'); altText.className = 'dialog-alt-text';
  altText.textContent = `You can always create more invitations later by asking ${host}.`;
  alt.append(altText);
  dialog.append(head, intro, form, alt); doc.body.append(dialog);
  const close = () => { dialog.close(); dialog.remove(); if (returnFocus?.isConnected) returnFocus.focus(); };
  cancel.addEventListener('click', close);
  dialog.addEventListener('cancel', e => { e.preventDefault(); close(); });
  // Sandboxed hosts block form submission; validate and act on click.
  create.addEventListener('click', async () => {
    const missing = [inviter, recipient].find(input => !input.value.trim());
    if (missing) { error.textContent = 'Please enter both names.'; missing.focus(); return; }
    error.textContent = '';
    const restore = spinButton(create);
    const args = { inviter_name: inviter.value.trim(), recipient_name: recipient.value.trim(),
      ...(userid.value.trim() ? { recipient_userid: userid.value.trim().toLowerCase() } : {}) };
    try {
      const result = await app.callServerTool({ name: 'create_agent_invitation', arguments: args }, { timeout: 30000 });
      const value = result.structuredContent;
      if (result.isError || value?.status !== 'prepared') throw new Error(result.content?.find(c => c.type === 'text')?.text || 'Invitation not verified.');
      showTemplate(invitationTemplate({ inviterAgent: `${args.inviter_name}'s ${hostLabel(app.getHostVersion()?.name) || 'agent'}`,
        ownUserid: value.own_userid, topic: value.topic }), args.recipient_name);
    } catch (e) {
      error.textContent = `Couldn’t create the invitation. ${e.message} Check Pending before retrying.`;
    } finally {
      restore();
    }
  });
  function showTemplate(text, name) {
    title.textContent = `Send Invitation to ${name}`;
    const note = doc.createElement('p'); note.className = 'meta';
    note.textContent = `Send this to ${name} to give to their agent. ${name} shows under Pending until their agent responds.`;
    const area = doc.createElement('textarea'); area.readOnly = true; area.rows = 10; area.value = text; area.id = 'invite-template';
    area.setAttribute('aria-label', 'Invitation');
    const copied = doc.createElement('p'); copied.className = 'meta dialog-copied'; copied.setAttribute('role', 'status');
    const done = doc.createElement('div'); done.className = 'dialog-actions';
    const copy = doc.createElement('button'); copy.type = 'button'; copy.className = 'primary'; copy.textContent = 'Copy invitation';
    const finish = doc.createElement('button'); finish.type = 'button'; finish.textContent = 'Done';
    copy.addEventListener('click', () => copyTemplate(doc, area, copied));
    finish.addEventListener('click', close);
    done.append(finish, copy);
    form.replaceWith(note, area, copied, done);
    copy.focus();
  }
  dialog.showModal(); inviter.focus();
  // Pre-fill the user's saved standing-invitation name (creating it if needed).
  standingInvitation(app).then(v => { if (v.inviter_name && !inviter.value) inviter.value = v.inviter_name; }, () => {});
  return dialog;
}

// Clipboard API first; fall back to selecting the textarea and execCommand,
// which works where the sandboxed iframe's async clipboard write is blocked.
async function copyTemplate(doc, area, status) {
  let ok = false;
  try { await doc.defaultView.navigator.clipboard.writeText(area.value); ok = true; } catch { /* try fallback */ }
  if (!ok) { try { area.focus(); area.select(); ok = doc.execCommand('copy'); } catch { ok = false; } }
  status.classList.toggle('copy-success', ok);
  if (ok) status.textContent = 'Copied';
  else { area.focus(); area.select(); status.textContent = 'Could not copy. Select and copy the text manually.'; }
}

async function standingInvitation(app, inviterName) {
  const result = await app.callServerTool({ name: 'standing_agent_invitation',
    arguments: inviterName === undefined ? {} : { inviter_name: inviterName } }, { timeout: 30000 });
  const value = result.structuredContent;
  if (result.isError || value?.status !== 'prepared') throw new Error(result.content?.find(c => c.type === 'text')?.text || 'Invitation not verified.');
  return value;
}

// Creates the standing open invitation if needed (spinner on the button), then
// shows it with an editable name. Done saves the name; Escape discards it.
export async function openStandingInvitation(app, doc, status, button) {
  const restore = spinButton(button);
  let value;
  try { value = await standingInvitation(app); }
  catch { showToast(doc, { title: 'Couldn’t load your open invitation', description: 'Please try again.' }); return; }
  finally { restore(); }
  doc.querySelector('#standing-dialog')?.remove();
  const host = hostLabel(app.getHostVersion()?.name) || 'agent';
  const dialog = doc.createElement('dialog'); dialog.id = 'standing-dialog'; dialog.className = 'app-dialog';
  dialog.setAttribute('aria-labelledby', 'standing-title');
  const title = doc.createElement('h2'); title.id = 'standing-title'; title.textContent = 'Share this with anyone';
  const intro = doc.createElement('p'); intro.className = 'dialog-intro';
  intro.textContent = 'This invitation isn’t for anyone in particular. Share it with anyone you’d like to connect with; each person who responds gets their own private connection with you.';
  const form = doc.createElement('div'); form.className = 'dialog-form';
  const [nameLabel, name] = field(doc, 'Your name in this invitation', 'inviter_name', { optional: true, placeholder: 'Optional' });
  name.value = value.inviter_name ?? '';
  const areaLabel = doc.createElement('label'); areaLabel.className = 'dialog-field-label';
  areaLabel.setAttribute('for', 'standing-template'); areaLabel.textContent = 'Open invitation';
  const area = doc.createElement('textarea'); area.readOnly = true; area.rows = 10; area.id = 'standing-template';
  const render = () => {
    const inviter = name.value.trim();
    area.value = invitationTemplate({ inviterAgent: inviter && `${inviter}'s ${host}`, ownUserid: value.own_userid, topic: value.topic });
  };
  render();
  name.addEventListener('input', render);
  const note = doc.createElement('p'); note.className = 'meta dialog-copied'; note.setAttribute('role', 'status');
  const error = doc.createElement('p'); error.className = 'dialog-error'; error.setAttribute('role', 'alert');
  const actions = doc.createElement('div'); actions.className = 'dialog-actions';
  const done = doc.createElement('button'); done.type = 'button'; done.className = 'dialog-ghost'; done.textContent = 'Done';
  const copy = doc.createElement('button'); copy.type = 'button'; copy.className = 'primary'; copy.textContent = 'Copy invitation';
  copy.prepend(icon(Copy, 'btn-icon'));
  actions.append(done, copy);
  form.append(nameLabel, areaLabel, area, note, error, actions);
  dialog.append(title, intro, form); doc.body.append(dialog);
  const close = () => { dialog.close(); dialog.remove(); if (button.isConnected) button.focus(); };
  dialog.addEventListener('cancel', e => { e.preventDefault(); close(); });
  copy.addEventListener('click', () => copyTemplate(doc, area, note));
  done.addEventListener('click', async () => {
    const inviter = name.value.trim();
    if (inviter === (value.inviter_name ?? '')) { close(); return; }
    const restoreDone = spinButton(done);
    try { await standingInvitation(app, inviter); close(); }
    catch (e) { error.textContent = `Couldn’t save your name. ${e.message}`; }
    finally { restoreDone(); }
  });
  dialog.showModal(); name.focus();
  return dialog;
}

// Invite buttons open the single-person dialog; open-invitation buttons show the standing invitation.
export async function setupInvite(app, buttons, status, handoff = {}, openButtons = []) {
  for (const button of buttons) button.addEventListener('click', () => {
    if (!button.disabled) openInviteDialog(app, button.ownerDocument, status, button, handoff);
  });
  for (const button of openButtons) button.addEventListener('click', () => {
    if (!button.disabled) openStandingInvitation(app, button.ownerDocument, status, button);
  });
  try {
    await app.connect();
    status.textContent = '';
    for (const button of [...buttons, ...openButtons]) button.disabled = false;
    return true;
  } catch {
    status.textContent = 'Could not connect to the host. Reopen the app to try again.';
    return false;
  }
}
