import { buildThreadContext, setupTellAgent } from './tell-agent.js';

// Mounted once per peer, never on a refresh. Pending-send state lives here.
export function createThreadComposer(app, container, isCurrent) {
  const doc = container.ownerDocument;
  const label = doc.createElement('label');
  label.textContent = 'Instructions for my agent';
  const input = doc.createElement('textarea');
  input.rows = 3;
  label.append(input);
  const button = doc.createElement('button');
  button.type = 'button'; button.textContent = 'Tell my agent';
  const help = doc.createElement('p');
  const details = doc.createElement('details');
  const summary = doc.createElement('summary');
  summary.textContent = 'Context sent with your instruction';
  const preview = doc.createElement('pre'); preview.id = 'thread-context';
  details.append(summary, preview);
  const feedback = doc.createElement('p'); feedback.id = 'agent-status';
  feedback.setAttribute('role', 'status'); feedback.setAttribute('aria-live', 'polite');
  let context;
  const update = setupTellAgent(app, () => context, input, button, feedback, isCurrent);
  container.replaceChildren(label, button, help, details, feedback);
  return (peer, range, result, ready) => {
    context = undefined;
    try {
      const next = buildThreadContext(peer, range, result);
      preview.textContent = next.text;
      if (ready) context = next.text;
      help.textContent = 'Sends your instruction (up to 4,000 characters) and the latest displayed context. Does not post a mesh reply or acknowledge messages. Refresh preserves drafts; leaving the thread clears them. If a send was pending, check the conversation before retrying. ' + next.notice;
    } catch {
      preview.textContent = '';
      help.textContent = 'Thread metadata is too large to send safely. Tell my agent is unavailable for this load.';
    }
    update();
  };
}
