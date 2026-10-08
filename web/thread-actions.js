import { setupReplySuggestions } from './reply-suggestions.js';
const options = { timeout: 15000 };

// Thread-only controls; the shared composer still owns the bounded context and
// its lifecycle. Draft state belongs to the peer, pending state to the app.
export function setupThreadActions(app, lifecycle, context, container, isCurrent, draft, peerId) {
  const doc = container.ownerDocument;
  const label = doc.createElement('label'); label.textContent = 'Tell your agent';
  const input = doc.createElement('textarea'); input.rows = 2;
  input.value = draft.value; label.append(input);
  const send = doc.createElement('button'); send.type = 'button'; send.textContent = 'Tell my agent';
  let status = doc.querySelector('#send-status');
  if (!status) {
    status = doc.createElement('p'); status.id = 'send-status'; status.setAttribute('role', 'status');
    doc.querySelector('#context-status').before(status);
  }
  container.append(label, send);
  const supported = Boolean(app.getHostCapabilities()?.message?.text && app.getHostCapabilities()?.updateModelContext?.text);
  if (!supported) status.textContent = 'This host does not support sending a request with separate thread context. Use the native chat.';
  let updateSuggestions = () => {};
  const update = () => {
    send.disabled = !supported || lifecycle.pending || !isCurrent() || !context() || !input.value.trim();
    updateSuggestions();
  };
  updateSuggestions = setupReplySuggestions(app, lifecycle, context, container, isCurrent, input, draft, update);
  input.addEventListener('input', () => { draft.value = input.value; draft.version++; update(); });
  lifecycle.onChange = update;
  send.addEventListener('click', async () => {
    update(); if (send.disabled) return;
    const text = input.value, version = draft.version, token = lifecycle.token();
    // Capture attribution before any await; never read a later peer or draft.
    const origin = `Submitted request #${++lifecycle.requestSequence} for peer ID ${JSON.stringify(peerId())} (not the current draft): `;
    const report = message => { status.textContent = origin + message; };
    const current = () => isCurrent() && lifecycle.current(token);
    lifecycle.pending = true; update();
    let attempted = false;
    report('Attaching displayed context before sending…');
    try {
      if (!await lifecycle.attach(context(), token) || !current()) {
        report('Context changed before sending. No message sent; draft retained.');
        return;
      }
      attempted = true;
      report('Awaiting host confirmation…');
      const result = await app.sendMessage({ role: 'user', content: [{ type: 'text', text }] }, options);
      if (result.isError) throw new Error('Host rejected message');
      report('Request accepted by the host. Check the conversation for the response; no mesh reply was posted by this app.');
      if (isCurrent() && draft.version === version) { draft.value = ''; input.value = ''; draft.version++; }
    } catch {
      report(attempted
        ? 'Could not confirm delivery. Check the conversation before retrying; draft retained.'
        : 'Could not confirm context attachment. No message sent; draft retained.');
    } finally { lifecycle.pending = false; lifecycle.onChange(); }
  });
  update();
  return update;
}
