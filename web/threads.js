import { discoverThreads } from './meshes.js';
import { setupMessages } from './messages.js';
import { createRefreshScheduler } from './refresh.js';

export function setupThreads(app, doc) {
  const status = doc.querySelector('#mesh-status');
  const list = doc.querySelector('#meshes');
  const indicator = doc.querySelector('#refresh-status');
  let disposed = false, disposal, lastSuccess, nextRow = 0;
  const rows = new Map();
  const refreshButton = doc.querySelector('#refresh-threads');
  status.textContent = 'Loading threads…';
  const detail = setupMessages(app, doc, () => scheduler.request());
  const scheduler = createRefreshScheduler({
    isVisible: () => doc.visibilityState === 'visible',
    onBusy: busy => { indicator.hidden = !busy; },
    async refresh() {
      try {
        const discovery = await discoverThreads(app);
        if (disposed) return true;
        const peers = new Set(discovery.threads.map(t => t.peer));
        for (const [peer, entry] of rows) if (!peers.has(peer)) { entry.row.remove(); rows.delete(peer); }
        for (const thread of discovery.threads) {
          let entry = rows.get(thread.peer);
          if (!entry) {
            const row = doc.createElement('li');
            const button = doc.createElement('button');
            const account = doc.createElement('p');
            button.type = 'button'; button.id = `thread-${++nextRow}`;
            button.textContent = thread.peer;
            entry = { row, button, account, thread };
            button.addEventListener('click', () => detail.select(entry.thread, button));
            row.append(button, account); list.append(row); rows.set(thread.peer, entry);
          }
          entry.thread = thread;
          entry.account.textContent = thread.accountName ? `Account: ${thread.accountName}` : '';
          entry.account.hidden = !thread.accountName;
        }
        lastSuccess = new Date().toISOString();
        status.textContent = `get_data_catalog/list_shares completed — ${discovery.threads.length} threads returned. ${discovery.warnings.join(' ')} Last success: ${lastSuccess}.`;
        if (doc.visibilityState !== 'visible') return true;
        return await detail.refresh(discovery);
      } catch (error) {
        if (disposed) return false;
        status.textContent = `Could not load threads — discovery failed. Stale last-good threads retained. Last success: ${lastSuccess ?? 'not yet'}.`;
        detail.failed(error);
        return false;
      }
    },
  });
  const manual = () => scheduler.request();
  refreshButton.addEventListener('click', manual);
  const visibility = () => scheduler.visibilityChanged();
  function dispose() {
    if (disposed) return disposal;
    disposed = true;
    scheduler.dispose();
    disposal = detail.dispose();
    refreshButton.removeEventListener('click', manual);
    doc.removeEventListener('visibilitychange', visibility);
    doc.defaultView.removeEventListener('pagehide', dispose);
    return disposal;
  }
  doc.addEventListener('visibilitychange', visibility);
  doc.defaultView.addEventListener('pagehide', dispose);
  app.onteardown = async () => { await dispose(); return {}; };
  scheduler.request();
  return dispose;
}
