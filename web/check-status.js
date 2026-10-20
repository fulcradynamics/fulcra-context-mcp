import { requestInChat } from './invite.js';
import { showToast } from './toast.js';
import { icon, Sparkles } from './icons.js';

const REFRESH_MS = 60000;
export const startPrompt = 'Please use the set-up-agent-contacts skill to start automatically checking my Fulcra messages. '
  + 'This is an explicit scheduling request: skip the invitation offer and ask whether I want checks only or checks with replies.';

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

// Builds the onboarding card shown when no automatic-check schedule exists. The
// same content renders in the empty-state welcome panel and as a sticky header in
// the message view; `onSetup` hands the setup request to the chat.
function fillCard(container, host, onSetup) {
  const doc = container.ownerDocument;
  container.replaceChildren();
  const head = doc.createElement('div'); head.className = 'onboarding-head';
  head.append(icon(Sparkles, 'onboarding-icon', 18));
  const title = doc.createElement('p'); title.className = 'onboarding-title'; title.textContent = 'Let your agent keep up for you';
  head.append(title);
  const text = doc.createElement('p'); text.className = 'onboarding-text';
  text.textContent = `Set up ${host} to automatically check for new messages and reply on your behalf. `
    + 'New messages still show up here either way — this just lets your agent act on them without you asking.';
  const button = doc.createElement('button'); button.type = 'button'; button.className = 'primary onboarding-action';
  button.textContent = 'Set up automatic checking';
  button.addEventListener('click', () => onSetup(button));
  container.append(head, text, button);
}

export function setupCheckStatus(app, doc, canMessage, sentMessage = 'Continue in the conversation.',
  notifySent = message => showToast(doc, { title: 'Request sent', description: message })) {
  const cards = [...doc.querySelectorAll('.onboarding-card')];
  const feedback = doc.querySelector('#status');
  const host = app.getHostVersion()?.name || 'your agent';
  let sending = false;
  const onSetup = async button => {
    if (sending) return;
    sending = true;
    await requestInChat(app, feedback, startPrompt, sentMessage, { button, toast: notifySent });
    sending = false;
  };
  // Only offer setup where the host can carry the request to chat.
  for (const card of cards) fillCard(card, host, onSetup);
  async function refresh() {
    if (doc.visibilityState !== 'visible') return;
    let status;
    try { status = await readCheckStatus(app); } catch { status = null; }
    // Show the onboarding card only when no schedule exists; once one is set up,
    // there is nothing to surface here.
    const show = canMessage && status?.status === 'not_set_up';
    for (const card of cards) card.hidden = !show;
  }
  refresh();
  const timer = setInterval(refresh, REFRESH_MS);
  return { refresh, dispose: () => clearInterval(timer) };
}
