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

// Context updates do not send a message or start a model turn (SDK 1.7.5).
export function setupNativeContext(app, lifecycle, context, button, status, isCurrent) {
  let pending = false;
  const update = () => { button.disabled = pending || !isCurrent() || !context() || !app.getHostCapabilities()?.updateModelContext?.text; };
  const guidance = 'Context attached. Now type and send your request in the native ChatGPT composer; you may need to expand the conversation manually. No message or mesh reply was sent.';
  update();
  button.addEventListener('click', async () => {
    update();
    if (button.disabled) return;
    const token = lifecycle.token();
    const current = () => isCurrent() && lifecycle.current(token);
    const text = context();
    pending = true; update();
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
      if (current()) status.textContent = 'Could not confirm context attachment. Retry to attach the current displayed context.';
    } finally {
      pending = false;
      if (isCurrent()) update();
    }
  });
  return update;
}
