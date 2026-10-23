const options = { timeout: 15000 };
const lifecycles = new WeakMap();

export function getContextLifecycle(app, status) {
  if (!lifecycles.has(app)) lifecycles.set(app, createContextLifecycle(app, status));
  return lifecycles.get(app);
}

// One queue for the app, not one per peer: an old attach must settle before its
// empty replacement, and before a new peer can attach.
export function createContextLifecycle(app, status) {
  let tail = Promise.resolve(), epoch = 0, dirty = false, clearing, disposed = false;
  let pending = false, desired, queued, base;
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
        const result = await app.updateModelContext({ content: [] }, options);
        if (result?.isError) throw new Error('Context clear rejected');
        dirty = false;
        report('Thread context cleared. The next chat handoff will attach the current display before sending.');
      } catch {
        report('Could not confirm context was cleared. Previous thread context may remain in ChatGPT; do not rely on it. Retry by attaching the current thread or close the app.');
      } finally { clearing = undefined; if (base) reconcile(); }
    });
    return clearing;
  }
  // The base (general app context) is always published; the selected thread's
  // desired context follows it while current.
  function reconcile() {
    if (disposed || pending) return;
    const thread = desired?.isCurrent() && desired.text ? desired : undefined;
    const text = [base, thread?.text].filter(Boolean).join('\n\n');
    const identity = JSON.stringify([base, thread?.identity]);
    if (!text || (queued?.identity === identity && queued.epoch === epoch)) return;
    const token = epoch;
    queued = { identity, epoch: token };
    lifecycle.attach(text, token, true, Boolean(thread)).catch(() => {
      // Mark delivery dirty, but wait for an ordinary refresh to retry.
      if ((!thread || desired?.isCurrent()) && lifecycle.current(token)) invalidate();
    });
  }
  const lifecycle = {
    get pending() { return pending; },
    set pending(value) {
      pending = value;
      // Explicit actions own the slot until their awaited operation settles.
      if (value) queued = undefined;
      else reconcile();
    },
    handoffLocks: new Set(),
    isClear: () => !dirty,
    onChange: () => {},
    token: () => epoch,
    current: token => !disposed && epoch === token,
    sync(text, isCurrent, identity = text) {
      if (desired?.identity !== identity && !pending) invalidate();
      desired = { text, isCurrent, identity };
      reconcile();
    },
    setBase(text) { base = text; reconcile(); },
    attach(text, token, passive = false, needsThread = true) {
      return enqueue(async () => {
        if (disposed || epoch !== token || (passive && (pending || (needsThread && !desired?.isCurrent())))) return false;
        dirty = true; // Even a timeout is not proof of nondelivery.
        const result = await app.updateModelContext({ content: [{ type: 'text', text }] }, options);
        if (result?.isError) throw new Error('Context attach rejected');
        return !disposed && epoch === token;
      });
    },
    invalidate,
    dispose() { const done = invalidate(); disposed = true; desired = undefined; return done; },
  };
  return lifecycle;
}
