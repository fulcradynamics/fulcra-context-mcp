import { requestInChat } from './invite.js';
import { showToast } from './toast.js';
import { icon, Sparkles, X } from './icons.js';
import { hostName } from './host-label.js';

const REFRESH_MS = 60000;
// UI-only preference (never an account ID or message): keep the dismissed nudge down.
const DISMISS_KEY = 'fulcra.contacts.onboarding-dismissed';
export const startPrompt = 'Please use the set-up-agent-contacts skill to start automatically checking my Fulcra messages. '
  + 'This is an explicit scheduling request: skip the invitation offer and ask whether I want checks only or checks with replies.';

const call = async (app, args) => {
  const result = await app.callServerTool({ name: 'get_message_check_status', arguments: args }, { timeout: 30000 });
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

const explainer = host => `Set up ${host} to automatically check for new messages and reply on your behalf. `
  + 'New messages still show up here either way — this just lets your agent act on them without you asking.';

const setupAction = (doc, className, onSetup) => {
  const button = doc.createElement('button'); button.type = 'button'; button.className = className;
  button.textContent = 'Set up automatic checking';
  button.addEventListener('click', () => onSetup(button));
  return button;
};

// The prominent, dismissible card shown atop the message view when no schedule exists.
function fillStickyCard(container, host, onSetup, onDismiss) {
  const doc = container.ownerDocument;
  container.replaceChildren();
  const head = doc.createElement('div'); head.className = 'onboarding-head';
  head.append(icon(Sparkles, 'onboarding-icon', 18));
  const title = doc.createElement('p'); title.className = 'onboarding-title'; title.textContent = 'Let your agent keep up for you';
  head.append(title);
  const dismiss = doc.createElement('button'); dismiss.type = 'button'; dismiss.className = 'onboarding-dismiss';
  dismiss.setAttribute('aria-label', 'Dismiss'); dismiss.append(icon(X, 'btn-icon', 16));
  dismiss.addEventListener('click', onDismiss);
  head.append(dismiss);
  const text = doc.createElement('p'); text.className = 'onboarding-text'; text.textContent = explainer(host);
  // Same teal-tint style as the side-panel invite button (not the solid primary).
  container.append(head, text, setupAction(doc, 'onboarding-action', onSetup));
}

// The quiet always-available version in the Advanced panel (no dismiss) so a user
// who dismissed the card can still start setup from the UI.
function fillAdvanced(container, host, onSetup) {
  const doc = container.ownerDocument;
  container.replaceChildren();
  const text = doc.createElement('p'); text.className = 'meta'; text.textContent = explainer(host);
  container.append(text, setupAction(doc, 'onboarding-advanced-action', onSetup));
}

export function setupCheckStatus(app, doc, canMessage, sentMessage = 'Continue in the conversation.',
  notifySent = message => showToast(doc, { title: 'Request sent', description: message })) {
  const sticky = doc.querySelector('#onboarding-thread');
  const advanced = doc.querySelector('#onboarding-advanced');
  const feedback = doc.querySelector('#status');
  const host = hostName(app);
  let sending = false, notSetUp = false, dismissed = false;
  try { dismissed = doc.defaultView.localStorage.getItem(DISMISS_KEY) === '1'; } catch { /* Opaque sandbox origin. */ }
  const onSetup = async button => {
    if (sending) return;
    sending = true;
    await requestInChat(app, feedback, startPrompt, sentMessage, { button, toast: notifySent });
    sending = false;
  };
  // Dismissing the prominent card sends the offer to the Advanced panel instead.
  const onDismiss = () => {
    dismissed = true;
    try { doc.defaultView.localStorage.setItem(DISMISS_KEY, '1'); } catch { /* Session-only fallback. */ }
    render();
  };
  fillStickyCard(sticky, host, onSetup, onDismiss);
  fillAdvanced(advanced, host, onSetup);
  function render() {
    sticky.hidden = !(notSetUp && !dismissed);
    advanced.hidden = !(notSetUp && dismissed);
  }
  async function refresh() {
    if (doc.visibilityState !== 'visible') return;
    let status;
    try { status = await readCheckStatus(app); } catch { status = null; }
    // Only offer setup where the host can carry the request to chat, and only when
    // no schedule exists.
    notSetUp = canMessage && status?.status === 'not_set_up';
    render();
  }
  refresh();
  const timer = setInterval(refresh, REFRESH_MS);
  return { refresh, dispose: () => clearInterval(timer) };
}
