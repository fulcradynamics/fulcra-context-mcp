import { createThreadComposer } from './thread-composer.js';
import { readConversation } from './conversation.js';
import { createMessageList } from './message-list.js';
export { parseRecords } from './records.js';

export function setupMessages(app, doc, requestRefresh) {
  const panel = doc.querySelector('#mesh-detail');
  const listPanel = doc.querySelector('#mesh-list');
  const title = doc.querySelector('#message-title');
  const status = doc.querySelector('#message-status');
  const messages = doc.querySelector('#messages');
  const composer = doc.querySelector('#thread-composer');
  const start = doc.querySelector('#message-start');
  const end = doc.querySelector('#message-end');
  const load = doc.querySelector('#message-load');
  const back = doc.querySelector('#message-back');
  const order = doc.querySelector('#message-order');
  let selected, displayed, range, rangeLabel, requested, updateComposer, lastSuccess, ready = false;
  let generation = 0;
  let queryVersion = 0;
  let returnFocus;
  const messageList = createMessageList(messages, doc.querySelector('#new-activity'), order,
    (item, { record, source, direction, stale, last_success_at }) => {
      if (!item.firstChild) item.append(doc.createElement('p'), doc.createElement('pre'));
      const rawTime = record.recorded_at ?? record.start_time;
      const timestamp = typeof rawTime === 'string' ? new Date(rawTime) : null;
      const text = `${direction} — ${source.fulcra_userid} / ${source.id} — ` + (timestamp && Number.isFinite(+timestamp)
        ? `${timestamp.toLocaleString()} (your local time)` : 'Timestamp unavailable')
        + (stale ? ` — Stale; access not verified. Last success: ${last_success_at ?? 'unknown'}` : '');
      if (item.firstChild.textContent !== text) item.firstChild.textContent = text;
      const body = messageText(record);
      if (item.lastChild.textContent !== body) item.lastChild.textContent = body;
    });
  const setTitle = thread => { title.textContent = `Thread with ${thread.peer}${thread.accountName ? ` — Account: ${thread.accountName}` : ''}`; };

  function render(result, canSend = true) {
    ready = canSend;
    result = { ...result, messages: [...result.messages].sort((a, b) => {
      const at = Date.parse(a.record.recorded_at ?? a.record.start_time);
      const bt = Date.parse(b.record.recorded_at ?? b.record.start_time);
      if (!Number.isFinite(at)) return Number.isFinite(bt) ? 1 : 0;
      if (!Number.isFinite(bt)) return -1;
      return order.value === 'latest' ? bt - at : at - bt;
    }) };
    messageList.update(result.messages, () => {
      setTitle(selected);
      status.textContent = result.warnings.length
        ? `${result.messages.length} messages shown. ${result.warnings.join(' ')}`
        : `${result.messages.length} messages returned for this range${result.messages.length === 0 ? '. No messages in this range.' : '.'}`;
      status.textContent += ` Range: ${rangeLabel}. Last success: ${lastSuccess ?? 'not yet'}.`;
      updateComposer(selected.peer, range, result, ready);
    });
  }

  function failed(error, unavailable = false) {
    if (!selected) return;
    const canSend = !unavailable && Boolean(lastSuccess || displayed?.messages.length);
    const warning = `${unavailable ? '' : 'Stale — '}${error.message} Access and content not verified current. Use Load messages to retry.`;
    displayed = { messages: unavailable ? [] : (displayed?.messages ?? []).map(m => ({ ...m, stale: true })), warnings: [...new Set([...(displayed?.warnings ?? []), warning])] };
    if (unavailable) lastSuccess = undefined;
    render(displayed, canSend);
  }

  async function read(discovery) {
    if (!selected) return true;
    const requestGeneration = generation;
    const requestVersion = queryVersion;
    const query = requested;
    const current = () => generation === requestGeneration && queryVersion === requestVersion;
    try {
      const thread = discovery.threads.find(t => t.peer === selected.peer);
      if (thread) selected = thread;
      // Exclude revoked channels immediately, including when a new range fails.
      if (displayed) {
        const accessible = displayed.messages.filter(m => thread?.sources.some(s => s.id === m.source.id && s.fulcra_userid === m.source.fulcra_userid));
        if (accessible.length !== displayed.messages.length) {
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
      range = query.range; rangeLabel = query.label;
      displayed = result;
      render(result);
      return success;
    } catch (error) {
      if (current()) failed(error, /no longer available/.test(error.message));
      return false;
    }
  }
  function applyDates() {
    const startDate = new Date(`${start.value}T00:00:00Z`);
    const endDate = new Date(`${end.value}T00:00:00Z`);
    if (!Number.isFinite(+startDate) || !Number.isFinite(+endDate) || startDate > endDate) {
      status.textContent = 'Choose a valid date range (start on or before end).';
      return false;
    }
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
    generation++;
    selected = undefined;
    messageList.clear(); composer.replaceChildren();
    panel.hidden = true; listPanel.hidden = false;
    (returnFocus?.isConnected ? returnFocus : doc.querySelector('#refresh-threads'))?.focus();
  };
  load.addEventListener('click', onLoad);
  order.addEventListener('change', onOrder);
  back.addEventListener('click', onBack);
  function select(thread, button) {
    generation++;
    const selectionGeneration = generation;
    selected = thread; displayed = undefined; lastSuccess = undefined; range = undefined; rangeLabel = undefined;
    returnFocus = button;
    messageList.clear();
    updateComposer = createThreadComposer(app, composer, () => generation === selectionGeneration);
    setTitle(thread);
    const today = new Date();
    end.value = today.toISOString().slice(0, 10);
    today.setUTCDate(today.getUTCDate() - 1);
    start.value = today.toISOString().slice(0, 10);
    applyDates();
    range = requested.range; rangeLabel = requested.label;
    panel.hidden = false; listPanel.hidden = true; back.focus();
    status.textContent = 'Loading messages…';
    requestRefresh();
  }
  return { select, refresh: read, failed, dispose() {
    generation++; selected = undefined;
    messageList.dispose();
    load.removeEventListener('click', onLoad);
    order.removeEventListener('change', onOrder);
    back.removeEventListener('click', onBack);
  } };
}

export function messageText(record) {
  if (typeof record.note !== 'string') return 'Unrecognized record: no note.\n' + JSON.stringify(record, null, 2);
  try {
    const message = JSON.parse(record.note);
    if (message?.v === 1 && typeof message.body === 'string') {
      const metadata = ['kind', 'to', 'to_user', 'slug', 'mid']
        .filter(key => typeof message[key] === 'string')
        .map(key => `${key}: ${message[key]}`).join(' · ');
      return `${metadata}\n\n${message.body}`;
    }
  } catch { /* Non-envelope notes remain readable, not silently discarded. */ }
  return `Unrecognized mesh envelope — raw note:\n${record.note}`;
}
