import { getContextLifecycle } from './native-context.js';
import { invitationTemplate } from './invite-template.js';

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
export async function requestInChat(app, status, text, sent) {
  const lifecycle = getContextLifecycle(app, status);
  if (lifecycle.pending) return false;
  lifecycle.pending = true; lifecycle.onChange();
  status.textContent = 'Sending request to the conversation…';
  try {
    await lifecycle.invalidate();
    if (!lifecycle.isClear()) throw new Error('Previous thread context not cleared');
    const result = await app.sendMessage({ role: 'user', content: [{ type: 'text', text }] }, { timeout: 15000 });
    if (result.isError) throw new Error('Host rejected message');
    status.textContent = sent;
    return true;
  } catch {
    status.textContent = 'Could not send the request. Check the conversation before retrying.';
    return false;
  } finally {
    lifecycle.pending = false; lifecycle.onChange();
  }
}

function field(doc, label, name, optional = false) {
  const wrap = doc.createElement('label'); wrap.textContent = label;
  const input = doc.createElement('input'); input.type = 'text'; input.name = name; input.maxLength = name === 'recipient_userid' ? 36 : 80;
  input.required = !optional; wrap.append(input);
  return [wrap, input];
}

// Prepares a single-person invitation without the model, or hands what the user
// typed to the invite skill in chat. Open invitations stay in chat.
export function openInviteDialog(app, doc, status, returnFocus) {
  doc.querySelector('#invite-dialog')?.remove();
  const dialog = doc.createElement('dialog'); dialog.id = 'invite-dialog'; dialog.className = 'app-dialog';
  dialog.setAttribute('aria-labelledby', 'invite-title');
  const title = doc.createElement('h2'); title.id = 'invite-title'; title.textContent = 'Invite someone';
  const form = doc.createElement('div'); form.className = 'dialog-form';
  const [inviterLabel, inviter] = field(doc, 'Your name', 'inviter_name');
  const [recipientLabel, recipient] = field(doc, 'Their name', 'recipient_name');
  const [idLabel, userid] = field(doc, 'Their Fulcra user ID (optional)', 'recipient_userid', true);
  const help = doc.createElement('p'); help.className = 'meta';
  help.textContent = 'Creates a channel for this contact and an invitation to copy and send them. With their ID, the channel is shared with them now. For a group invitation, continue in chat.';
  const error = doc.createElement('p'); error.className = 'meta'; error.setAttribute('role', 'alert');
  const actions = doc.createElement('div'); actions.className = 'dialog-actions';
  const cancel = doc.createElement('button'); cancel.type = 'button'; cancel.textContent = 'Cancel';
  const chat = doc.createElement('button'); chat.type = 'button'; chat.textContent = 'Continue in chat';
  chat.hidden = !app.getHostCapabilities()?.message?.text;
  const create = doc.createElement('button'); create.type = 'button'; create.className = 'primary'; create.textContent = 'Create invitation';
  actions.append(cancel, chat, create);
  form.append(inviterLabel, recipientLabel, idLabel, help, error, actions);
  dialog.append(title, form); doc.body.append(dialog);
  const close = () => { dialog.close(); dialog.remove(); if (returnFocus?.isConnected) returnFocus.focus(); };
  cancel.addEventListener('click', close);
  dialog.addEventListener('cancel', e => { e.preventDefault(); close(); });
  chat.addEventListener('click', async () => {
    const entered = [['my name', inviter.value], ['their name', recipient.value], ['their Fulcra user ID', userid.value]]
      .filter(([, value]) => value.trim()).map(([key, value]) => `${key}: ${value.trim()}`);
    close();
    await requestInChat(app, status, invitationPrompt + (entered.length ? ` Details I already entered: ${entered.join('; ')}.` : ''),
      'Request sent. Continue in the conversation; no invitation has been sent yet.');
  });
  // Sandboxed hosts block form submission; validate and act on click.
  create.addEventListener('click', async () => {
    const missing = [inviter, recipient].find(input => !input.value.trim());
    if (missing) { error.textContent = 'Enter both names.'; missing.focus(); return; }
    create.disabled = true; error.textContent = 'Creating invitation…';
    const args = { inviter_name: inviter.value.trim(), recipient_name: recipient.value.trim(),
      ...(userid.value.trim() ? { recipient_userid: userid.value.trim().toLowerCase() } : {}) };
    try {
      const result = await app.callServerTool({ name: 'create_agent_invitation', arguments: args }, { timeout: 30000 });
      const value = result.structuredContent;
      if (result.isError || value?.status !== 'prepared') throw new Error(result.content?.find(c => c.type === 'text')?.text || 'Invitation not verified.');
      showTemplate(invitationTemplate({ inviterAgent: `${args.inviter_name}'s ${app.getHostVersion()?.name || 'agent'}`,
        ownUserid: value.own_userid, topic: value.topic }), args.recipient_name);
    } catch (e) {
      error.textContent = `Could not create the invitation. ${e.message} Check Pending before retrying.`;
      create.disabled = false;
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

export async function setupInvite(app, buttons, status) {
  for (const button of buttons) button.addEventListener('click', () => {
    if (!button.disabled) openInviteDialog(app, button.ownerDocument, status, button);
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
