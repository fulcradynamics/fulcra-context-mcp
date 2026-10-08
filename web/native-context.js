const options = { timeout: 15000 };

// One queue for the app, not one per peer: an old attach must settle before its
// empty replacement, and before a new peer can attach. No poll reattaches data.
export function createContextLifecycle(app, status, presentation = 'global') {
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
        report(presentation === 'thread'
          ? 'Thread context cleared. Your next Tell my agent request will attach the current display before sending.'
          : 'Thread context cleared. Click Continue conversation in chat again to attach the current display.');
      } catch {
        report('Could not confirm context was cleared. Previous thread context may remain in ChatGPT; do not rely on it. Retry by attaching the current thread or close the app.');
      } finally { clearing = undefined; }
    });
    return clearing;
  }
  return {
    pending: false,
    requestSequence: 0,
    samplingPending: false,
    onChange: () => {},
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

// Only an explicit click attaches context. The user writes in native chat;
// this path never sends a message or requests a model turn.
export function setupNativeContext(app, lifecycle, context, button, status, isCurrent) {
  const supported = Boolean(app.getHostCapabilities()?.updateModelContext?.text);
  const update = () => {
    button.disabled = lifecycle.pending || !isCurrent() || !context() || !supported;
  };
  lifecycle.onChange = update;
  if (!supported) status.textContent = 'This host cannot attach thread context. Continue in the native chat without an attachment.';
  const guidance = 'Context attached. Type and send your request in the native chat. No message or mesh reply was sent. You may need to expand the conversation manually.';
  update();
  button.addEventListener('click', async () => {
    update();
    if (button.disabled) return;
    const token = lifecycle.token();
    const current = () => isCurrent() && lifecycle.current(token);
    const text = context();
    lifecycle.pending = true;
    update();
    status.textContent = 'Attaching displayed thread context…';
    try {
      if (!await lifecycle.attach(text, token) || !current()) return;
      status.textContent = guidance;
      if (app.getHostContext()?.availableDisplayModes?.includes('pip')) {
        try {
          const result = await app.requestDisplayMode({ mode: 'pip' }, options);
          if (current()) status.textContent = guidance + (result.mode === 'pip' ? ' Host reports picture-in-picture mode.' : ` Host kept ${result.mode} mode; PiP was not applied.`);
        } catch {
          if (current()) status.textContent = guidance + ' Could not change display mode.';
        }
      } else status.textContent = guidance + ' This host does not advertise PiP support.';
    } catch {
      if (current()) status.textContent = 'Could not confirm context attachment. No message sent. Retry to attach the current displayed context.';
    } finally {
      lifecycle.pending = false;
      lifecycle.onChange();
    }
  });
  return update;
}
