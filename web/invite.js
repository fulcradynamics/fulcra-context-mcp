import { getContextLifecycle } from './native-context.js';
import { invitationTemplate } from './invite-template.js';
import { spinButton, continueMessage } from './toast.js';

export const invitationPrompt = 'I want to invite another user to connect our agents through Fulcra. '
  + 'Please use the invite skill to help me prepare the invitation. '
  + 'First offer a single-person invitation or an open invitation I can share with a group. For a single-person invitation, ask for my name and the name of the person I am inviting. '
  + 'For that single-person choice, then prepare a dedicated unshared channel and call prepare_agent_invitation(data_type) to durably generate its random code. Show me a copyable invitation prompt for the other person to give their agent, '
  + 'using the returned own_userid and code and the connection skill URL. Their agent must share its own channel with me and its FIRST message topic must be exactly handshake followed by one space and the code. Do not ask for the other user\'s ID; if I already gave it, share the prepared outbox with exactly that user after preparing the code. '
  + 'This request authorizes you to prepare a dedicated unshared outbox with the identifier <their name>\'s agent (for example Lucian\'s agent) and the original setup session URL when available, without another confirmation. '
  + 'Then ask whether I want to add optional context about what the invite is for, so you can personalize the prompt and draft an outgoing message. '
  + 'For a single-person invitation, this request authorizes match_agent_invitations to share only that prepared outbox back to the authenticated incoming-share owner after a unique first-message code match and independent grant readback. Keep it unshared until that match; unmatched sharing needs my explicit consent. '
  + 'For an open invitation, ask for my name and a meaningful invitation identifier instead of a recipient name. Call prepare_agent_invitation(data_type, open_invitation=true); use its returned topic exactly: open_invitation followed by one space and the code, NOT handshake. The template is never shared; matching creates a separate one-to-one outbox per authenticated responder. Use <sender> via <open invitation identifier> as display-only fallback, never for routing. Do not post messages merely to complete matching; response content remains subject to my preferences.';

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
    status.textContent = 'Could not send the request. Check the conversation before retrying.';
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
  const [idLabel, userid] = field(doc, 'Their Fulcra user ID', 'recipient_userid',
    { optional: true, placeholder: 'Optional', help: 'If you have it, you’ll connect right away. Otherwise they’ll get an invitation to accept.' });
  const error = doc.createElement('p'); error.className = 'dialog-error'; error.setAttribute('role', 'alert');
  const actions = doc.createElement('div'); actions.className = 'dialog-actions';
  const cancel = doc.createElement('button'); cancel.type = 'button'; cancel.className = 'dialog-ghost'; cancel.textContent = 'Cancel';
  const create = doc.createElement('button'); create.type = 'button'; create.className = 'primary'; create.textContent = 'Create invitation';
  actions.append(cancel, create);
  form.append(inviterLabel, recipientLabel, idLabel, error, actions);
  // A separate path: hand the invite off to the agent in chat (e.g. for groups).
  const host = app.getHostVersion()?.name || 'chat';
  const alt = doc.createElement('div'); alt.className = 'dialog-alt';
  alt.hidden = !app.getHostCapabilities()?.message?.text;
  const altText = doc.createElement('p'); altText.className = 'dialog-alt-text';
  altText.textContent = `Inviting a group, or want help? Continue in ${host} and your agent will set it up.`;
  const chat = doc.createElement('button'); chat.type = 'button'; chat.className = 'dialog-alt-action'; chat.textContent = `Continue in ${host}`;
  alt.append(altText, chat);
  dialog.append(head, intro, form, alt); doc.body.append(dialog);
  const close = () => { dialog.close(); dialog.remove(); if (returnFocus?.isConnected) returnFocus.focus(); };
  cancel.addEventListener('click', close);
  dialog.addEventListener('cancel', e => { e.preventDefault(); close(); });
  chat.addEventListener('click', async () => {
    const entered = [['my name', inviter.value], ['their name', recipient.value], ['their Fulcra user ID', userid.value]]
      .filter(([, value]) => value.trim()).map(([key, value]) => `${key}: ${value.trim()}`);
    // Keep the dialog open with a spinner on the button during send; then close.
    await requestInChat(app, status, invitationPrompt + (entered.length ? ` Details I already entered: ${entered.join('; ')}.` : ''),
      `${continueMessage(app, handoff.inlineList)} No invitation has been sent yet.`,
      { button: chat, toast: handoff.notifySent });
    close();
  });
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
      showTemplate(invitationTemplate({ inviterAgent: `${args.inviter_name}'s ${app.getHostVersion()?.name || 'agent'}`,
        ownUserid: value.own_userid, topic: value.topic }), args.recipient_name);
    } catch (e) {
      error.textContent = `Couldn’t create the invitation. ${e.message} Check Pending before retrying.`;
    } finally {
      restore();
    }
  });
  function showTemplate(text, name) {
    title.textContent = `Invitation for ${name}`;
    const note = doc.createElement('p'); note.className = 'meta';
    note.textContent = `Send this to ${name} to give to their agent. ${name} shows under Pending until their agent responds.`;
    const area = doc.createElement('textarea'); area.readOnly = true; area.rows = 10; area.value = text; area.id = 'invite-template';
    area.setAttribute('aria-label', 'Invitation');
    const copied = doc.createElement('p'); copied.className = 'meta'; copied.setAttribute('role', 'status');
    const done = doc.createElement('div'); done.className = 'dialog-actions';
    const copy = doc.createElement('button'); copy.type = 'button'; copy.className = 'primary'; copy.textContent = 'Copy invitation';
    const finish = doc.createElement('button'); finish.type = 'button'; finish.textContent = 'Done';
    copy.addEventListener('click', async () => {
      try { await doc.defaultView.navigator.clipboard.writeText(text); copied.textContent = 'Copied'; }
      catch { area.focus(); area.select(); copied.textContent = 'Could not copy. Select and copy the text manually.'; }
    });
    finish.addEventListener('click', close);
    done.append(finish, copy);
    form.replaceWith(note, area, copied, done);
    copy.focus();
  }
  dialog.showModal(); inviter.focus();
  return dialog;
}

export async function setupInvite(app, buttons, status, handoff = {}) {
  for (const button of buttons) button.addEventListener('click', () => {
    if (!button.disabled) openInviteDialog(app, button.ownerDocument, status, button, handoff);
  });
  try {
    await app.connect();
    status.textContent = '';
    for (const button of buttons) button.disabled = false;
    return true;
  } catch {
    status.textContent = 'Could not connect to the host. Reopen the app to try again.';
    return false;
  }
}
