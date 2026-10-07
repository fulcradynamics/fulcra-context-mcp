const invitationPrompt = 'I want to invite another user to connect our agents through Fulcra. '
  + 'Please use the fulcra-mesh skill to help me prepare the invitation. '
  + 'Ask me who I want to invite and for any missing details before creating or sharing anything.';

export async function setupInvite(app, button, status) {
  button.addEventListener('click', async () => {
    if (button.disabled) return;
    button.disabled = true;
    status.textContent = 'Sending request to the conversation…';
    try {
      const result = await app.sendMessage({
        role: 'user',
        content: [{ type: 'text', text: invitationPrompt }],
      }, { timeout: 15000 });
      if (result.isError) throw new Error('Host rejected message');
      status.textContent = 'Request sent. Continue in the conversation; no invitation has been sent yet.';
    } catch {
      status.textContent = 'Could not send the request. Check the conversation before retrying.';
    } finally {
      button.disabled = false;
    }
  });
  try {
    await app.connect();
    if (!app.getHostCapabilities()?.message?.text) {
      status.textContent = 'This host cannot send chat messages. Ask the agent to use the fulcra-mesh skill in the conversation.';
      return;
    }
    status.textContent = '';
    button.disabled = false;
  } catch {
    status.textContent = 'Could not connect to the host. Reopen the app to try again.';
  }
}
