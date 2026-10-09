import { createThreadComposer } from './thread-composer.js';
import { renderIdentity } from './identity.js';
import { readConversation } from './conversation.js';
import { createMessageList } from './message-list.js';
import { createContextLifecycle } from './native-context.js';
import { reconcilePosts } from './mesh-send.js';
import { icon, ArrowUpRight, ArrowDownLeft, CalendarRange, ArrowLeft, ChevronDown } from './icons.js';
export { parseRecords } from './records.js';

export function setupMessages(app, doc, requestRefresh, presentation = 'global') {
  const panel = doc.querySelector('#mesh-detail');
  const listPanel = doc.querySelector('#mesh-list');
  const title = doc.querySelector('#message-title');
  const status = doc.querySelector('#message-status');
  const loading = doc.querySelector('#message-loading');
  const messages = doc.querySelector('#messages');
  const composer = doc.querySelector('#thread-composer');
  const start = doc.querySelector('#message-start');
  const end = doc.querySelector('#message-end');
  const load = doc.querySelector('#message-load');
  const back = doc.querySelector('#message-back');
  const order = doc.querySelector('#message-order');
  const orderField = doc.querySelector('#message-order-field');
  load.prepend(icon(CalendarRange, 'btn-icon'));
  back.prepend(icon(ArrowLeft, 'btn-icon'));
  const contextLifecycle = createContextLifecycle(app, doc.querySelector('#context-status'), presentation);
  const drafts = new Map();

  let selected, displayed, range, rangeLabel, requested, updateComposer, lastSuccess, ready = false;
  let generation = 0;
  let queryVersion = 0;
  let returnFocus;
  let firstAttempt = true, loadFailed = false, unavailable = false, statusTimer, validation = '';
  let refreshState = { running: false, paused: false, nextAt: null };
  function renderStatus() {
    clearTimeout(statusTimer);
    if (!selected) return;
    let text = '';
    if (validation) text = validation;
    else if (unavailable) text = 'This thread is no longer available.';
    else if (loadFailed) {
      const state = refreshState;
      text = 'Could not load messages. ';
      if (state.paused) text += 'Retries paused while this app is hidden.';
      else if (state.running) text += 'Retrying…';
      else if (state.nextAt !== null) {
        text += `Retrying in ${Math.max(0, Math.ceil((state.nextAt - Date.now()) / 1000))} seconds.`;
        // Display-only tick. The scheduler alone owns retry requests/deadlines.
        statusTimer = setTimeout(renderStatus, 1000);
      } else text += 'Automatic retries are paused.';
    } else if (displayed && !displayed.messages.length) text = 'No messages in this date range.';
    if (status.textContent !== text) messageList.preservePosition(() => { status.textContent = text; });
  }
  const messageList = createMessageList(messages, doc.querySelector('#new-activity'), order,
    (item, { record, source, direction, state }) => {
      let title, date, body;
      if (!item.firstChild) {
        item.className = 'message-row';
        // The direction tile is placed in grid column 1; header/date/body stay
        // direct <li> children so each sits in column 2 and keeps a flat shape.
        const incoming = direction === 'Incoming';
        const tile = doc.createElement('span');
        tile.className = incoming ? 'row-tile incoming' : 'row-tile';
        tile.append(icon(incoming ? ArrowDownLeft : ArrowUpRight, 'row-icon'));
        // The header is a toggle: clicking it collapses/expands the body (below).
        const header = doc.createElement('p');
        header.className = 'message-header message-toggle';
        header.setAttribute('role', 'button');
        header.tabIndex = 0;
        header.setAttribute('aria-expanded', 'true');
        title = doc.createElement('span'); title.className = 'message-title';
        header.append(title, icon(ChevronDown, 'message-chevron'));
        date = doc.createElement('p'); date.className = 'message-date';
        body = doc.createElement('pre');
        // The body is wrapped so collapse can animate via grid-template-rows.
        const bodyWrap = doc.createElement('div'); bodyWrap.className = 'message-body';
        bodyWrap.append(body);
        item.append(tile, header, date, bodyWrap);
      } else {
        title = item.querySelector('.message-title');
        date = item.querySelector('.message-date');
        body = item.querySelector('pre');
      }
      const rawTime = record.recorded_at ?? record.start_time;
      const timestamp = typeof rawTime === 'string' ? new Date(rawTime) : null;
      const name = typeof source.name === 'string' && source.name.trim() ? source.name : 'Catalog name unavailable';
      const text = `${direction} (${name})`;
      if (title.textContent !== text) title.textContent = text;
      let badge = item.querySelector('.send-badge');
      if (state && !badge) { badge = doc.createElement('span'); badge.className = 'send-badge'; title.after(badge); }
      if (badge) { badge.textContent = state === 'sending' ? 'sending…' : state === 'uncertain' ? 'unconfirmed' : 'posted'; badge.hidden = !state; }
      const dateText = timestamp && Number.isFinite(+timestamp)
        ? `${timestamp.toLocaleString()} (your local time)` : 'Timestamp unavailable';
      if (date.textContent !== dateText) date.textContent = dateText;
      const bodyText = messageText(record);
      if (body.textContent !== bodyText) body.textContent = bodyText;
    });
  const setTitle = thread => renderIdentity(title, thread.identifier, thread.peer, 'Thread with ',
    thread.accountName ? ` — Account: ${thread.accountName}` : '');

  function render(result, canSend = true) {
    ready = canSend;
    const draft = drafts.get(selected.peer);
    const confirmed = reconcilePosts(draft, result.messages).at(-1);
    if (confirmed) doc.querySelector('#send-status').textContent = `Peer ${selected.peer}, message ${confirmed.envelope.mid}: Posted to your outbox (verified by polling); not confirmed delivered or read by the peer.`;
    const posts = unavailable ? [] : (draft.posts ?? [])
      .filter(p => selected.sources.some(s => s.id === p.source.id && s.fulcra_userid === p.source.fulcra_userid))
      .map(({ source, record, direction, state }) => ({ source, record, direction, state }));
    result = { ...result, messages: [...result.messages, ...posts] };
    result = { ...result, messages: [...result.messages].sort((a, b) => {
      const at = Date.parse(a.record.recorded_at ?? a.record.start_time);
      const bt = Date.parse(b.record.recorded_at ?? b.record.start_time);
      if (!Number.isFinite(at)) return Number.isFinite(bt) ? 1 : 0;
      if (!Number.isFinite(bt)) return -1;
      return order.value === 'latest' ? bt - at : at - bt;
    }) };
    messageList.update(result.messages, () => {
      setTitle(selected);
      renderStatus();
      updateComposer(selected.peer, range, result, ready, Boolean(lastSuccess || result.messages.length));
    });
  }

  function failed(error, revoked = false) {
    if (!selected) return;
    firstAttempt = false; loading.hidden = true;
    loadFailed = true; unavailable = revoked || unavailable;
    const canSend = !unavailable && Boolean(lastSuccess || displayed?.messages.length);
    const warning = `${unavailable ? '' : 'Stale — '}${error.message} Access and content not verified current. Use Load messages to retry.`;
    displayed = { messages: unavailable ? [] : (displayed?.messages ?? []).map(m => ({ ...m, stale: true })), warnings: [...new Set([...(displayed?.warnings ?? []), warning])] };
    if (unavailable) lastSuccess = undefined;
    render(displayed, canSend);
  }

  async function read(discovery) {
    if (!selected) return true;
    loading.hidden = !firstAttempt;
    const requestGeneration = generation;
    const requestVersion = queryVersion;
    const query = requested;
    const current = () => generation === requestGeneration && queryVersion === requestVersion;
    try {
      const thread = discovery.threads.find(t => t.peer === selected.peer);
      const sourcesRemoved = selected.sources.some(s => !thread?.sources.some(t => t.id === s.id && t.fulcra_userid === s.fulcra_userid));
      if (sourcesRemoved) contextLifecycle.invalidate();
      if (thread) selected = thread;
      // Exclude revoked channels immediately, including when a new range fails.
      if (displayed) {
        const accessible = displayed.messages.filter(m => thread?.sources.some(s => s.id === m.source.id && s.fulcra_userid === m.source.fulcra_userid));
        if (sourcesRemoved || accessible.length !== displayed.messages.length) {
          displayed = { ...displayed, messages: accessible, warnings: [...displayed.warnings, 'Previously displayed sources no longer accessible; removed.'] };
          render(displayed, false);
        }
      }
      const sameRange = JSON.stringify(range) === JSON.stringify(query.range);
      const result = await readConversation(app, selected, query.range, current, { discovery, previous: sameRange ? displayed : undefined, now: new Date().toISOString() });
      if (!current()) return true;
      const success = !result.warnings.some(w => w.startsWith('Could not load messages'));
      if (!success && !sameRange && !result.messages.length && displayed) {
        failed(new Error(`Could not load requested range ${query.label}. Showing previous applied range.`));
        return false;
      }
      if (success) lastSuccess = new Date().toISOString();
      else if (!sameRange) lastSuccess = undefined;
      loadFailed = !success; unavailable = false;
      loading.hidden = true;
      range = query.range; rangeLabel = query.label;
      displayed = result;
      render(result);
      return success;
    } catch (error) {
      if (current()) failed(error, /no longer available/.test(error.message));
      return false;
    } finally {
      if (generation === requestGeneration) { firstAttempt = false; loading.hidden = true; }
    }
  }
  function applyDates() {
    const startDate = new Date(`${start.value}T00:00:00Z`);
    const endDate = new Date(`${end.value}T00:00:00Z`);
    if (!Number.isFinite(+startDate) || !Number.isFinite(+endDate) || startDate > endDate) {
      validation = 'Choose a valid date range (start on or before end).';
      renderStatus();
      return false;
    }
    validation = '';
    renderStatus();
    endDate.setUTCDate(endDate.getUTCDate() + 1);
    const next = { label: `${start.value} through ${end.value} UTC`, range: { start_time: startDate.toISOString(), end_time: endDate.toISOString() } };
    if (JSON.stringify(next) !== JSON.stringify(requested)) {
      requested = next; queryVersion++;
      if (displayed) render(displayed, false);
    }
    return true;
  }
  const onLoad = () => {
    if (start.reportValidity() && end.reportValidity() && applyDates()) requestRefresh();
  };
  const onOrder = () => { if (displayed) render(displayed, ready); };
  const onBack = () => {
    contextLifecycle.invalidate();
    generation++;
    selected = undefined;
    clearTimeout(statusTimer); loading.hidden = true;
    messageList.clear(); composer.replaceChildren();
    panel.hidden = true; listPanel.hidden = false;
    (returnFocus?.isConnected ? returnFocus : doc.querySelector('#refresh-threads'))?.focus();
  };
  // Collapse a message by clicking its header (title/date/tile); the body is
  // left clickable for text selection. Collapse state lives on the reused row.
  function toggleMessage(target) {
    if (target.closest('pre')) return;
    const li = target.closest('.message-row');
    if (!li || !messages.contains(li)) return;
    const collapsed = li.classList.toggle('collapsed');
    li.querySelector('.message-toggle')?.setAttribute('aria-expanded', String(!collapsed));
  }
  const onMessageClick = e => toggleMessage(e.target);
  const onMessageKey = e => {
    if ((e.key !== 'Enter' && e.key !== ' ') || !e.target.closest('.message-toggle')) return;
    e.preventDefault();
    toggleMessage(e.target);
  };
  load.addEventListener('click', onLoad);
  order.addEventListener('change', onOrder);
  back.addEventListener('click', onBack);
  messages.addEventListener('click', onMessageClick);
  messages.addEventListener('keydown', onMessageKey);
  function select(thread, button) {
    contextLifecycle.invalidate();
    generation++;
    const selectionGeneration = generation;
    selected = thread; displayed = undefined; lastSuccess = undefined; range = undefined; rangeLabel = undefined; ready = false;
    firstAttempt = true; loadFailed = false; unavailable = false; validation = '';
    clearTimeout(statusTimer); loading.hidden = false;
    returnFocus = button;
    messageList.clear();
    if (!drafts.has(thread.peer)) drafts.set(thread.peer, { value: '', version: 0 });
    updateComposer = createThreadComposer(app, composer, () => generation === selectionGeneration, contextLifecycle, presentation, drafts.get(thread.peer), orderField,
      () => ({ thread: generation === selectionGeneration ? selected : undefined, result: displayed, ready }),
      () => { if (selected && displayed) render(displayed, ready); });
    setTitle(thread);
    const today = new Date();
    end.value = today.toISOString().slice(0, 10);
    today.setUTCDate(today.getUTCDate() - 1);
    start.value = today.toISOString().slice(0, 10);
    applyDates();
    range = requested.range; rangeLabel = requested.label;
    panel.hidden = false; listPanel.hidden = true; back.focus();
    status.textContent = '';
    requestRefresh();
  }
  return { select, back: onBack, refresh: read, failed,
    refreshState(state) { refreshState = state; renderStatus(); },
    dispose() {
    generation++; selected = undefined;
    clearTimeout(statusTimer); loading.hidden = true;
    messageList.dispose();
    load.removeEventListener('click', onLoad);
    order.removeEventListener('change', onOrder);
    back.removeEventListener('click', onBack);
    messages.removeEventListener('click', onMessageClick);
    messages.removeEventListener('keydown', onMessageKey);
    return contextLifecycle.dispose();
  } };
}

export function messageText(record) {
  if (typeof record.note !== 'string') return 'Unrecognized record: no note.\n' + JSON.stringify(record, null, 2);
  try {
    const message = JSON.parse(record.note);
    if (message?.v === 1 && typeof message.body === 'string') {
      return message.body;
    }
  } catch { /* Non-envelope notes remain readable, not silently discarded. */ }
  return `Unrecognized mesh envelope — raw note:\n${record.note}`;
}
