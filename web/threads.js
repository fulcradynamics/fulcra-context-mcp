import { discoverThreads } from './meshes.js';
import { setupMessages } from './messages.js';
import { createRefreshScheduler } from './refresh.js';

export function setupThreads(app, doc, entrypoint = { presentation: 'global' }) {
  const status = doc.querySelector('#mesh-status');
  const list = doc.querySelector('#meshes');

  let disposed = false, disposal, lastSuccess, nextRow = 0;
  const rows = new Map();
  const refreshButton = doc.querySelector('#refresh-threads');
  status.textContent = 'Loading threads…';
  const inlineList = entrypoint.presentation === 'threads';
  const detail = setupMessages(app, doc, () => scheduler.request(), inlineList ? 'thread' : entrypoint.presentation);
  let displayPending = false, displayEpoch = 0, hostContext = app.getHostContext();
  async function choose(entry) {
    if (disposed || displayPending || rows.get(entry.thread.peer) !== entry) return;
    userSelected = true; launchPending = false; launchStatus.textContent = '';
    const epoch = displayEpoch;
    const current = () => !disposed && epoch === displayEpoch && rows.get(entry.thread.peer) === entry;
    if (inlineList && hostContext?.displayMode !== 'fullscreen') {
      if (!hostContext?.availableDisplayModes?.includes('fullscreen')) {
        launchStatus.textContent = 'This host does not advertise fullscreen support. The thread list remains open.';
        return;
      }
      displayPending = true;
      launchStatus.textContent = 'Requesting a fullscreen conversation panel…';
      try {
        const result = await app.requestDisplayMode({ mode: 'fullscreen' }, { timeout: 15000 });
        if (!current()) {
          if (!disposed && epoch === displayEpoch) launchStatus.textContent = 'That peer is no longer available. Choose an accessible thread.';
          return;
        }
        if (result.mode !== 'fullscreen') {
          launchStatus.textContent = `The host kept ${result.mode} mode. No conversation panel was opened.`;
          return;
        }
        // The response is host authority too; a notification need not follow it.
        hostContext = { ...hostContext, displayMode: result.mode };
      } catch {
        if (current()) launchStatus.textContent = 'Could not confirm fullscreen mode change. The thread list remains open. Check the host before retrying.';
        return;
      } finally { displayPending = false; }
    }
    launchStatus.textContent = '';
    if (inlineList) doc.documentElement.classList.remove('compact-threads');
    detail.select(entry.thread, entry.button);
  }
  let requestedPeer, launchPending = false, userSelected = false;
  const launchStatus = doc.createElement('p');
  launchStatus.id = 'entrypoint-status'; launchStatus.setAttribute('role', 'status');
  if (entrypoint.presentation !== 'global') {
    status.before(launchStatus);
    launchStatus.textContent = 'Waiting for the initial conversation result…';
  }
  const scheduler = createRefreshScheduler({
    isVisible: () => doc.visibilityState === 'visible',
    onState: state => detail.refreshState(state),
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
            button.addEventListener('click', () => choose(entry));
            row.append(button, account); list.append(row); rows.set(thread.peer, entry);
          }
          entry.thread = thread;
          entry.account.textContent = thread.accountName ? `Account: ${thread.accountName}` : '';
          entry.account.hidden = !thread.accountName;
        }
        if (launchPending) {
          launchPending = false;
          const matches = discovery.threads.filter(t => t.peer === requestedPeer);
          if (matches.length === 1) {
            launchStatus.textContent = '';
            detail.select(matches[0], rows.get(requestedPeer)?.button);
          } else launchStatus.textContent = 'The exact referenced peer is not available or is ambiguous in accessible threads. Choose a thread below; no other peer was selected.';
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
  const stopHost = entrypoint.observeHost?.(context => {
    hostContext = { ...hostContext, ...context };
    if (!inlineList || disposed || !context.displayMode) return;
    // Initial host context is not a return from a user-selected panel.
    if (context.displayMode !== 'fullscreen' && userSelected) {
      displayEpoch++;
      detail.back();
      launchStatus.textContent = `The host returned to ${context.displayMode} mode. Choose a thread to request a conversation panel.`;
    }
    doc.documentElement.classList.toggle('compact-threads', context.displayMode !== 'fullscreen');
  });
  const manual = () => scheduler.request();
  refreshButton.addEventListener('click', manual);
  const visibility = () => scheduler.visibilityChanged();
  function dispose() {
    if (disposed) return disposal;
    disposed = true;
    stopHost?.();
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
  if (inlineList && entrypoint.directResource) {
    launchStatus.textContent = 'Choose a thread to request a conversation panel.';
    scheduler.request();
  } else if (inlineList) entrypoint.consume(result => {
    if (disposed || userSelected) return;
    launchStatus.textContent = result.isError || result.structuredContent?.presentation !== 'threads'
      ? 'The initial thread list result failed. Refresh threads to retry discovery.'
      : 'Choose a thread to request a conversation panel.';
    scheduler.request();
  });
  else if (entrypoint.presentation === 'thread') entrypoint.consume(result => {
    if (disposed || userSelected) return;
    const data = result.structuredContent;
    if (result.isError || data?.presentation !== 'thread'
      || (data.peer_fulcra_userid != null && (typeof data.peer_fulcra_userid !== 'string' || !data.peer_fulcra_userid.trim()))) {
      launchStatus.textContent = 'The requested conversation could not be opened safely. Choose an accessible thread below.';
    } else {
      requestedPeer = data.peer_fulcra_userid;
      launchPending = requestedPeer != null;
      launchStatus.textContent = launchPending ? 'Finding the exact referenced peer…' : 'Choose an accessible thread.';
    }
    scheduler.request();
  });
  else scheduler.request();
  return dispose;
}
