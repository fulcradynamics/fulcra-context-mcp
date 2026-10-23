import { buildThreadContext } from './thread-context.js';
import { setupThreadActions } from './thread-actions.js';

// Mounted once per peer, never on a refresh, preserving focus and disclosure.
export function createThreadComposer(app, container, isCurrent, lifecycle, presentation = 'global', draft, view, changed) {
  const doc = container.ownerDocument;
  const help = presentation === 'thread' ? doc.createElement('p') : doc.querySelector('#thread-help');
  help.textContent = '';
  const details = doc.createElement('details'); details.className = 'context-details';
  const summary = doc.createElement('summary');
  summary.textContent = 'Context attached to chat';
  const preview = doc.createElement('pre'); preview.id = 'thread-context';
  details.append(summary, preview);
  let context, peerId, usable = false;
  container.replaceChildren();
  const currentContext = () => usable ? context : undefined;
  const update = setupThreadActions(app, lifecycle, currentContext, container, isCurrent, draft, () => peerId, view, changed, presentation);
  // Context preview + handoff help live in the single Advanced panel,
  // not inline in the composer. Replace any prior copy on re-mount.
  const advanced = doc.querySelector('#advanced-panel');
  advanced?.querySelector('.context-details')?.remove();
  if (presentation === 'thread') {
    advanced?.querySelector('.thread-help-dyn')?.remove();
    help.className = 'meta thread-help-dyn';
    (advanced ?? container).append(help);
  }
  (advanced ?? container).append(details);
  const updater = (peer, range, result, ready, loaded) => {
    peerId = peer;
    usable = loaded;
    const thread = view().thread;
    result = { ...result, selectedContact: { label: thread?.identifier, account_name: thread?.accountName },
      sources: thread?.sources, participants: thread?.participants };
    // Refresh timestamps alone do not invalidate a snapshot.
    const nextIdentity = JSON.stringify({ peer, range, warnings: result.warnings, assessment: result.assessment,
      selectedContact: result.selectedContact,
      participants: result.participants, viewingAgent: result.viewingAgent,
      sources: result.sources,
      messages: result.messages.map(({ last_success_at, ...message }) => message) });
    context = undefined;
    try {
      const next = buildThreadContext(peer, range, result);
      preview.textContent = next.text;
      if (ready) context = next.text;
      lifecycle.sync(thread?.sources.length && app.getHostCapabilities()?.updateModelContext?.text
        ? next.text : undefined, isCurrent, nextIdentity);
      help.textContent = 'Send posts your exact message directly to your own peer-shared outbox, without an agent turn. The secondary button attaches displayed untrusted context and sends your optional composition to your host chat, not the peer. Drafts remain per peer until you close the app. ' + next.notice;
    } catch {
      preview.textContent = '';
      lifecycle.sync(undefined, isCurrent);
      help.textContent = 'Thread metadata is too large to attach safely. Chat handoff is unavailable for this load.';
    }
    update();
  };
  updater.markRead = update.markRead;
  return updater;
}
