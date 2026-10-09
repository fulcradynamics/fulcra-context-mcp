// One completion-based timer for discovery and selected-thread reads. A refresh
// must drain its entire batch before settling (including on partial failure).
export function createRefreshScheduler({ refresh, isVisible, onBusy = () => {},
  onState = () => {}, now = Date.now,
  setTimeout = globalThis.setTimeout, clearTimeout = globalThis.clearTimeout }) {
  let timer, nextAt = null, running = false, queued = false, disposed = false, failures = 0;
  const publish = () => onState({ running, paused: disposed || !isVisible(), nextAt });
  const cancel = () => { clearTimeout(timer); timer = undefined; nextAt = null; };
  async function request() {
    cancel();
    if (disposed || !isVisible()) { publish(); return; }
    if (running) { queued = true; publish(); return; }
    running = true;
    onBusy(true);
    publish();
    let success = false;
    try { success = await refresh(); } catch { /* Retry after the drained batch. */ }
    finally {
      running = false;
      onBusy(false);
      failures = success ? 0 : Math.min(failures + 1, 3);
      if (!disposed && isVisible()) {
        if (queued) { queued = false; void request(); }
        else {
          const delay = 10000 * 2 ** failures;
          nextAt = now() + delay;
          timer = setTimeout(request, delay);
        }
      } else queued = false;
      publish();
    }
  }
  return {
    request,
    visibilityChanged() {
      cancel();
      if (isVisible()) void request();
      else { queued = false; publish(); }
    },
    dispose() { disposed = true; queued = false; cancel(); publish(); },
  };
}
