import { requestInChat } from './invite.js';
import { showToast } from './toast.js';

const REFRESH_MS = 60000;
export const startPrompt = 'Please use the set-up-agent-contacts skill to start automatically checking my Fulcra messages. '
  + 'This is an explicit scheduling request: skip the invitation offer and ask whether I want checks only or checks with replies.';
export const checkPrompt = 'Please use the check-messages skill to check my Fulcra messages now.';

const call = async (app, args) => {
  const result = await app.callServerTool({ name: 'fulcra_check_status', arguments: args }, { timeout: 30000 });
  if (result.isError) throw new Error('Check status unavailable');
  return result.structuredContent;
};

// Latest scheduled check across this account's configurations; null when unknown.
export async function readCheckStatus(app) {
  const status = await call(app, {});
  if (status.status !== 'choose_configuration') return status;
  const all = await Promise.all(status.configurations.map(id => call(app, { configuration_id: id })));
  if (all.some(s => s.status === 'unavailable')) return { status: 'unavailable' };
  const checked = all.filter(s => s.status === 'checked').sort((a, b) => b.last_checked.localeCompare(a.last_checked));
  return checked[0] ?? all[0];
}

export function describeCheckStatus(status) {
  if (status.status === 'not_set_up') return { text: 'Your agent is not automatically checking for messages.', action: 'Start automatic checking', prompt: startPrompt };
  if (status.status === 'never_checked') return { text: 'Your agent has not checked for messages yet.', action: 'Check for new messages', prompt: checkPrompt };
  if (status.status === 'checked') {
    const when = new Date(status.last_checked).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    return { text: `Your agent last checked for messages ${when}.`, action: 'Check for new messages', prompt: checkPrompt };
  }
  return null;
}

export function setupCheckStatus(app, doc, canMessage, sentMessage = 'Continue in the conversation.',
  notifySent = message => showToast(doc, { title: 'Request sent', description: message })) {
  const row = doc.querySelector('#check-status');
  const text = row.querySelector('.check-status-text');
  const button = row.querySelector('button');
  const feedback = doc.querySelector('#status');
  let current = null, sending = false;
  button.addEventListener('click', async () => {
    if (!current || sending) return;
    sending = true;
    await requestInChat(app, feedback, current.prompt, sentMessage, { button, toast: notifySent });
    sending = false;
  });
  async function refresh() {
    if (doc.visibilityState !== 'visible') return;
    // Keep the card open with a loading line through the first fetch so it doesn't
    // collapse (and jolt the side panel) between the connect message clearing and
    // the status arriving. Later refreshes leave the existing line in place.
    if (!text.textContent) text.textContent = 'Checking your agent’s status…';
    try { current = describeCheckStatus(await readCheckStatus(app)); } catch { current = null; }
    // The card collapses on its own (CSS :has) when both the status line and the
    // feedback note are empty, so here we only fill or clear the status line.
    if (!current) { text.textContent = ''; button.hidden = true; return; }
    text.textContent = current.text;
    button.textContent = current.action;
    button.hidden = !canMessage;
  }
  refresh();
  const timer = setInterval(refresh, REFRESH_MS);
  return { refresh, dispose: () => clearInterval(timer) };
}
