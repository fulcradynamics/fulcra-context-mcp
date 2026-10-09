import { buildThreadContext } from './thread-context.js';
import { setupThreadActions } from './thread-actions.js';

// Mounted once per peer, never on a refresh, preserving focus and disclosure.
export function createThreadComposer(app, container, isCurrent, lifecycle, presentation = 'global', draft, orderField, view, changed) {
  const doc = container.ownerDocument;
  const help = presentation === 'thread' ? doc.createElement('p') : doc.querySelector('#thread-help');
  help.textContent = '';
  const details = doc.createElement('details'); details.className = 'context-details';
  const summary = doc.createElement('summary');
  summary.textContent = 'Context attached to chat';
  const preview = doc.createElement('pre'); preview.id = 'thread-context';
  details.append(summary, preview);
  let context, identity, peerId, usable = false;
  container.replaceChildren();
  const currentContext = () => usable ? context : undefined;
  const update = setupThreadActions(app, lifecycle, currentContext, container, isCurrent, draft, () => peerId, orderField, view, changed, presentation);
  if (presentation === 'thread') container.append(help);
  container.append(details);
  return (peer, range, result, ready, loaded) => {
    peerId = peer;
    usable = loaded;
    // Refresh timestamps alone do not invalidate a snapshot. No automatic attach.
    const nextIdentity = JSON.stringify({ peer, range, warnings: result.warnings,
      messages: result.messages.map(({ last_success_at, ...message }) => message) });
    if (!ready || (identity !== undefined && identity !== nextIdentity)) lifecycle.invalidate();
    identity = nextIdentity;
    context = undefined;
    try {
      const next = buildThreadContext(peer, range, result);
      preview.textContent = next.text;
      if (ready) context = next.text;
      help.textContent = 'Send posts your exact message directly to your own peer-shared outbox, without an agent turn. The secondary button attaches displayed untrusted context and sends your optional composition to your host chat, not the peer. Drafts remain per peer until you close the app. ' + next.notice;
    } catch {
      preview.textContent = '';
      lifecycle.invalidate();
      help.textContent = 'Thread metadata is too large to attach safely. Chat handoff is unavailable for this load.';
    }
    update();
  };
}
