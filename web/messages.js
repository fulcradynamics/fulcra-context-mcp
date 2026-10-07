import { buildThreadContext, setupTellAgent } from './tell-agent.js';
import { readConversation } from './conversation.js';
export { parseRecords } from './records.js';

export function setupMessages(app, doc) {
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
  let selected;
  let generation = 0;

  async function read() {
    const requestGeneration = ++generation;
    messages.replaceChildren();
    composer.replaceChildren();
    const startDate = new Date(`${start.value}T00:00:00Z`);
    const endDate = new Date(`${end.value}T00:00:00Z`);
    if (!Number.isFinite(+startDate) || !Number.isFinite(+endDate) || startDate > endDate) {
      status.textContent = 'Choose a valid date range (start on or before end).';
      return;
    }
    endDate.setUTCDate(endDate.getUTCDate() + 1);
    const rangeLabel = `${start.value} through ${end.value} UTC`;
    const range = { start_time: startDate.toISOString(), end_time: endDate.toISOString() };
    status.textContent = `Loading messages — calling get_records after refreshing get_data_catalog/list_shares… ${rangeLabel}`;
    load.disabled = true;
    try {
      const result = await readConversation(app, selected, range, () => generation === requestGeneration);
      if (generation !== requestGeneration) return;
      for (const { record, source, direction } of result.messages) {
        const item = doc.createElement('li');
        const time = doc.createElement('p');
        const rawTime = record.recorded_at ?? record.start_time;
        const timestamp = typeof rawTime === 'string' ? new Date(rawTime) : null;
        time.textContent = `${direction} — ${source.fulcra_userid} / ${source.id} — ` + (timestamp && Number.isFinite(+timestamp)
          ? `${timestamp.toLocaleString()} (your local time)` : 'Timestamp unavailable');
        const body = doc.createElement('pre');
        body.textContent = messageText(record);
        item.append(time, body);
        messages.append(item);
      }
      status.textContent = result.warnings.length
        ? `${result.messages.length} messages shown. ${result.warnings.join(' ')}`
        : `${result.messages.length} messages returned for this range${result.messages.length === 0 ? '. No messages in this range.' : '.'}`;
      status.textContent += ` Range: ${rangeLabel}.`;
      try {
        const context = buildThreadContext(selected.peer, range, result);
        const label = doc.createElement('label');
        label.textContent = 'Instructions for my agent';
        const input = doc.createElement('textarea');
        input.rows = 3;
        label.append(input);
        const button = doc.createElement('button');
        button.type = 'button';
        button.textContent = 'Tell my agent';
        const help = doc.createElement('p');
        help.textContent = 'Sends your instruction (up to 4,000 characters) and only the displayed thread context to your agent. Does not post a mesh reply or acknowledge messages. Drafts are cleared when you leave or reload; if a send was pending, check the conversation before retrying. ' + context.notice;
        const details = doc.createElement('details');
        const summary = doc.createElement('summary');
        summary.textContent = 'Context sent with your instruction';
        const preview = doc.createElement('pre');
        preview.id = 'thread-context';
        preview.textContent = context.text;
        details.append(summary, preview);
        const feedback = doc.createElement('p');
        feedback.id = 'agent-status';
        feedback.setAttribute('role', 'status');
        feedback.setAttribute('aria-live', 'polite');
        setupTellAgent(app, context.text, input, button, feedback, () => generation === requestGeneration);
        composer.append(label, button, help, details, feedback);
      } catch {
        composer.textContent = 'Thread metadata is too large to send safely. Tell my agent is unavailable for this load.';
      }
    } catch (error) {
      if (generation !== requestGeneration) return;
      messages.replaceChildren();
      composer.replaceChildren();
      status.textContent = `Could not load messages. ${error.message} Range: ${rangeLabel}. Use Load messages to retry.`;
    } finally {
      if (generation === requestGeneration) load.disabled = false;
    }
  }
  load.addEventListener('click', () => {
    if (!load.disabled && start.reportValidity() && end.reportValidity()) void read();
  });
  back.addEventListener('click', () => {
    generation++;
    selected = undefined;
    messages.replaceChildren();
    composer.replaceChildren();
    panel.hidden = true;
    listPanel.hidden = false;
    listPanel.querySelector('button')?.focus();
  });
  return thread => {
    selected = thread;
    title.textContent = `Thread with ${thread.peer}`;
    const today = new Date();
    end.value = today.toISOString().slice(0, 10);
    today.setUTCDate(today.getUTCDate() - 29);
    start.value = today.toISOString().slice(0, 10);
    panel.hidden = false;
    listPanel.hidden = true;
    back.focus();
    void read();
  };
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
