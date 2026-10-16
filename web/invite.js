import { getContextLifecycle } from './native-context.js';

const invitationPrompt = 'I want to invite another user to connect our agents through Fulcra. '
  + 'Please use the invite skill to help me prepare the invitation. '
  + 'First prepare a dedicated unshared channel and call prepare_agent_invitation(data_type) to durably generate its random code. Show me a copyable invitation prompt for the other person to give their agent, '
  + 'using the returned own_userid and code and the connection skill URL. Their agent must share its own channel with me and its FIRST message topic must be exactly handshake followed by one space and the code. Do not ask for the other user\'s ID. '
  + 'This request authorizes you to prepare a dedicated unshared outbox with a context-supported identifier and the original setup session URL when available, without another confirmation. '
  + 'Then ask whether I want to add optional context about who or what the invite is for, so you can personalize the prompt and draft an outgoing message. '
  + 'This invitation request authorizes match_agent_invitations to share only that prepared outbox back to the authenticated incoming-share owner after a unique first-message code match and independent grant readback. Keep it unshared until that match; unmatched sharing needs my explicit consent. Do not post messages merely to complete matching; response content remains subject to my preferences.';

export async function setupInvite(app, buttons, status) {
  const setDisabled = disabled => { for (const button of buttons) button.disabled = disabled; };
  for (const button of buttons) button.addEventListener('click', async () => {
    const lifecycle = getContextLifecycle(app, status);
    if (button.disabled || lifecycle.pending) return;
    lifecycle.pending = true; lifecycle.onChange();
    setDisabled(true);
    status.textContent = 'Sending request to the conversation…';
    try {
      await lifecycle.invalidate();
      if (!lifecycle.isClear()) throw new Error('Previous thread context not cleared');
      const result = await app.sendMessage({
        role: 'user',
        content: [{ type: 'text', text: invitationPrompt }],
      }, { timeout: 15000 });
      if (result.isError) throw new Error('Host rejected message');
      status.textContent = 'Request sent. Continue in the conversation; no invitation has been sent yet.';
    } catch {
      status.textContent = 'Could not send the request. Check the conversation before retrying.';
    } finally {
      lifecycle.pending = false; lifecycle.onChange();
      setDisabled(false);
    }
  });
  try {
    await app.connect();
    if (!app.getHostCapabilities()?.message?.text) {
      status.textContent = 'This host cannot send chat messages. Ask the agent to use the invite skill in the conversation.';
      return true;
    }
    status.textContent = '';
    setDisabled(false);
    return true;
  } catch {
    status.textContent = 'Could not connect to the host. Reopen the app to try again.';
    return false;
  }
}
