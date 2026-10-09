import { buildThreadContext } from './thread-context.js';
import { setupNativeContext } from './native-context.js';
import { setupThreadActions } from './thread-actions.js';
import { icon, MessageSquare } from './icons.js';

// Mounted once per peer, never on a refresh, preserving focus and disclosure.
export function createThreadComposer(app, container, isCurrent, lifecycle, presentation = 'global', draft, orderField) {
  const doc = container.ownerDocument;
  const button = doc.createElement('button');
  button.type = 'button'; button.className = 'primary composer-primary';
  const help = presentation === 'thread' ? doc.createElement('p') : doc.querySelector('#thread-help');
  help.textContent = '';
  const details = doc.createElement('details');
  const summary = doc.createElement('summary');
  summary.textContent = 'Context attached to chat';
  const preview = doc.createElement('pre'); preview.id = 'thread-context';
  details.append(summary, preview);
  let context, identity, peerId, usable = false;
  container.replaceChildren();
  const currentContext = () => usable ? context : undefined;
  const update = presentation === 'thread'
    ? setupThreadActions(app, lifecycle, currentContext, container, isCurrent, draft, () => peerId, orderField)
    : setupNativeContext(app, lifecycle, currentContext, button, doc.querySelector('#context-status'), isCurrent);
  if (presentation !== 'thread') {
    button.append(icon(MessageSquare, 'btn-icon'), doc.createTextNode('Continue conversation in chat'));
    const actions = doc.createElement('div'); actions.className = 'composer-actions';
    actions.append(button);
    if (orderField) actions.append(orderField);
    container.append(actions);
  }
  if (presentation === 'thread') container.append(help);
  container.append(details);
  return (peer, range, result, ready, loaded) => {
    peerId = peer;
    usable = loaded;
    // Refresh timestamps alone do not invalidate a snapshot; changed displayed
    // records, warnings, order or applied range do. Never reattach automatically.
    const nextIdentity = JSON.stringify({ peer, range, warnings: result.warnings,
      messages: result.messages.map(({ last_success_at, ...message }) => message) });
    if (!ready || (identity !== undefined && identity !== nextIdentity)) lifecycle.invalidate();
    identity = nextIdentity;
    context = undefined;
    try {
      const next = buildThreadContext(peer, range, result);
      preview.textContent = next.text;
      if (ready) context = next.text;
      help.textContent = (presentation === 'thread'
        ? 'Tell my agent sends exactly your nonblank text to this chat after attaching the displayed context separately. It does not post to a peer or acknowledge messages. Drafts remain per peer until you close the app. '
        : 'Attaches only the displayed thread context. Type and send your request in the native chat; you may need to expand the conversation manually. This button does not send a message, start an agent turn, post a mesh reply or acknowledge messages. Changed context clears the attachment; click again to reattach. ') + next.notice;
    } catch {
      preview.textContent = '';
      lifecycle.invalidate();
      help.textContent = 'Thread metadata is too large to attach safely. Thread actions are unavailable for this load.';
    }
    update();
  };
}
