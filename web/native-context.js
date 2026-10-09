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
        report('Thread context cleared. The next chat handoff will attach the current display before sending.');
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
