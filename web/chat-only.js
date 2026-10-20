import { icon, Copy, Check } from './icons.js';

// Chat-only mode (bundle meta `connection-controls` = `chat`): action controls are
// replaced by instructions to ask the host, so there is one way to act. Reading,
// polling, acks and context sync continue. Set the meta to `full` to restore them.
export const CHAT_ONLY = globalThis.document?.querySelector('meta[name="connection-controls"]')?.content === 'chat';

export const hostName = app => app.getHostVersion()?.name || 'your agent';

// "Ask <host> to <phrase>" in monospace, with a copy button for the request itself.
export function chatInstruction(doc, host, phrase = '') {
  const row = doc.createElement('p'); row.className = 'chat-instruction';
  const text = doc.createElement('span');
  const copy = doc.createElement('button'); copy.type = 'button'; copy.className = 'instruction-copy';
  const status = doc.createElement('span'); status.className = 'visually-hidden'; status.setAttribute('role', 'status');
  row.append(text, copy, status);
  let request = '', timer;
  const show = (node, label) => { copy.replaceChildren(icon(node, 'btn-icon', 14)); copy.setAttribute('aria-label', label); };
  const reset = () => { clearTimeout(timer); show(Copy, `Copy “${request}”`); copy.classList.remove('copy-success'); };
  copy.addEventListener('click', async () => {
    reset();
    try {
      await doc.defaultView.navigator.clipboard.writeText(request);
      show(Check, 'Copied'); copy.classList.add('copy-success'); status.textContent = 'Copied';
    } catch {
      status.textContent = 'Could not copy. Type the request in chat.';
    }
    timer = setTimeout(() => { reset(); status.textContent = ''; }, 2000);
  });
  row.set = next => {
    if (next === phrase && request) return;
    phrase = next;
    request = phrase[0].toUpperCase() + phrase.slice(1);
    text.textContent = `Ask ${host} to ${phrase}`;
    reset();
  };
  if (phrase) row.set(phrase);
  return row;
}

// Always-present model context while chat-only: what the user sees and which
// packaged skill handles each suggested request.
export function generalContext(host) {
  return [
    `The user is viewing Fulcra Agents I Know, the Fulcra agent contacts app. It has no action buttons; it tells the user to ask ${host} in chat, so short requests below refer to this app.`,
    'Suggested requests and the skill for each:',
    '- "Invite someone\'s agent": invite.',
    '- "Set up automatic checking" (or "Set up checks"): set-up-agent-contacts; an explicit scheduling request, so skip the invitation offer and ask whether to check only or check and reply.',
    '- "Reply to <contact>": send, to the selected contact when one is shown below.',
    '- "Finish connecting <pending contact>": connect-our-agents (match prepared invitations; ask before sharing).',
    '- "Update my connection with <contact>": connect-our-agents legacy conversion; "Discuss old messages with <contact>": its legacy history guidance.',
    '- "Open <file path>": files. "End my contact with <contact>": connect-our-agents ending a contact.',
    'Requests still need each skill\'s verification and consent; viewing the app authorizes nothing.',
  ].join('\n');
}
