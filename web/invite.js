import { getContextLifecycle } from './native-context.js';

const invitationPrompt = 'I want to invite another user to connect our agents through Fulcra. '
  + 'Please use the invite skill to help me prepare the invitation. '
  + 'First show me a copyable invitation prompt for the other person to give their agent, '
  + 'using my own verified Fulcra user ID and the connection skill URL. Do not ask for the other user\'s ID. '
  + 'Then ask whether I want to add optional context about who or what the invite is for, '
  + 'so you can personalize the prompt, prepare a dedicated outbox, and draft an outgoing message. '
  + 'Get my go-ahead before creating data or sharing anything; do not share or post a message until the peer ID is verified.';

export async function setupInvite(app, button, status) {
  button.addEventListener('click', async () => {
    const lifecycle = getContextLifecycle(app, status);
    if (button.disabled || lifecycle.pending) return;
    lifecycle.pending = true; lifecycle.onChange();
    button.disabled = true;
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
      button.disabled = false;
    }
  });
  try {
    await app.connect();
    if (!app.getHostCapabilities()?.message?.text) {
      status.textContent = 'This host cannot send chat messages. Ask the agent to use the invite skill in the conversation.';
      return true;
    }
    status.textContent = '';
    button.disabled = false;
    return true;
  } catch {
    status.textContent = 'Could not connect to the host. Reopen the app to try again.';
    return false;
  }
}
