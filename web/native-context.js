import { INSTRUCTION_LIMIT } from './tell-agent.js';

const options = { timeout: 15000 };

// One queue for the app, not one per peer: an old attach must settle before its
// empty replacement, and before a new peer can attach. No poll reattaches data.
export function createContextLifecycle(app, status) {
  let tail = Promise.resolve(), epoch = 0, dirty = false, clearing, disposed = false;
  const report = text => { if (!disposed) status.textContent = text; };
  const enqueue = task => {
    const result = tail.then(task);
    tail = result.catch(() => {});
    return result;
  };
  function invalidate() {
    epoch++;
    if (clearing) return clearing;
    if (!dirty) return tail;
    report('Clearing attached thread context…');
    clearing = enqueue(async () => {
      try {
        // SDK content is an array; empty content replaces the previous context.
        await app.updateModelContext({ content: [] }, options);
        dirty = false;
        report('Thread context cleared. Use this thread in ChatGPT again to attach the current display.');
      } catch {
        report('Could not confirm context was cleared. Previous thread context may remain in ChatGPT; do not rely on it. Retry by attaching the current thread or close the app.');
      } finally { clearing = undefined; }
    });
    return clearing;
  }
  return {
    token: () => epoch,
    current: token => !disposed && epoch === token,
    attach(text, token) {
      return enqueue(async () => {
        if (disposed || epoch !== token) return false;
        dirty = true; // Even a timeout is not proof of nondelivery.
        await app.updateModelContext({ content: [{ type: 'text', text }] }, options);
        return !disposed && epoch === token;
      });
    },
    invalidate,
    dispose() { const done = invalidate(); disposed = true; return done; },
  };
}

// Only an explicit click attaches context and then relays a separate request.
export function setupNativeContext(app, lifecycle, context, button, status, isCurrent, input, sendState, feedback) {
  const update = () => {
    const capabilities = app.getHostCapabilities();
    button.disabled = sendState.pending || !isCurrent() || !context() || input.value.length > INSTRUCTION_LIMIT
      || !capabilities?.updateModelContext?.text || !capabilities?.message?.text;
  };
  input.addEventListener('input', update);
  const guidance = 'Request sent. Continue in the conversation; no mesh reply was posted by this button. You may need to expand the conversation manually.';
  update();
  button.addEventListener('click', async () => {
    update();
    if (button.disabled) return;
    const token = lifecycle.token();
    const current = () => isCurrent() && lifecycle.current(token);
    const text = context();
    const draft = input.value;
    sendState.pending = true; sendState.onChange();
    let attached = false;
    feedback.textContent = '';
    status.textContent = 'Attaching displayed thread context…';
    try {
      if (!await lifecycle.attach(text, token) || !current()) return;
      attached = true;
      status.textContent = 'Context attached.';
      feedback.textContent = 'Sending request…';
      const request = draft.trim() ? `App-relayed request from the instruction field. Please go ahead and carry out the request below, including sending or posting when requested. If it asks only for a draft, do not send it.\n\n${draft}`
        : 'I have attached a Fulcra Mesh thread for context. Please help me with this thread; I will provide my request in this conversation.';
      const result = await app.sendMessage({ role: 'user', content: [{ type: 'text', text: request }] }, options);
      if (result.isError) throw new Error('Host rejected request');
      // A changed poll does not undo acceptance, but never clear a newer draft.
      if (!isCurrent()) return;
      if (input.value === draft) input.value = '';
      // Acceptance belongs to the message, not the attached snapshot's epoch.
      feedback.textContent = guidance;
      if (!current()) return;
      if (app.getHostContext()?.availableDisplayModes?.includes('pip')) {
        try {
          const result = await app.requestDisplayMode({ mode: 'pip' }, options);
          if (current()) feedback.textContent = guidance + (result.mode === 'pip' ? ' Host reports picture-in-picture mode.' : ` Host kept ${result.mode} mode; PiP was not applied.`);
        } catch {
          if (current()) feedback.textContent = guidance + ' Could not change display mode.';
        }
      } else feedback.textContent = guidance + ' This host does not advertise PiP support.';
    } catch {
      if (attached && isCurrent()) {
        // Cleanup must never overwrite the outcome or lose its privacy warning.
        feedback.textContent = 'Context attached, but request send unconfirmed. Check the conversation before retrying; your draft is preserved. The attachment may have been cleared if the display changed.';
      } else if (current()) {
        status.textContent = 'Could not confirm context attachment. No request sent; your draft is preserved. Retry to attach the current displayed context.';
      }
    } finally {
      sendState.pending = false;
      sendState.onChange();
    }
  });
  return update;
}
