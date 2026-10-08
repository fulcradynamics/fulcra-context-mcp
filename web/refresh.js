// One completion-based timer for discovery and selected-thread reads. A refresh
// must drain its entire batch before settling (including on partial failure).
export function createRefreshScheduler({ refresh, isVisible, onBusy = () => {},
  setTimeout = globalThis.setTimeout, clearTimeout = globalThis.clearTimeout }) {
  let timer, running = false, queued = false, disposed = false, failures = 0;
  const cancel = () => { clearTimeout(timer); timer = undefined; };
  async function request() {
    cancel();
    if (disposed || !isVisible()) return;
    if (running) { queued = true; return; }
    running = true;
    onBusy(true);
    let success = false;
    try { success = await refresh(); } catch { /* Retry after the drained batch. */ }
    finally {
      running = false;
      onBusy(false);
      failures = success ? 0 : Math.min(failures + 1, 3);
      if (!disposed && isVisible()) {
        if (queued) { queued = false; void request(); }
        else timer = setTimeout(request, 10000 * 2 ** failures);
      } else queued = false;
    }
  }
  return {
    request,
    visibilityChanged() { cancel(); if (isVisible()) void request(); else queued = false; },
    dispose() { disposed = true; queued = false; cancel(); },
  };
}
