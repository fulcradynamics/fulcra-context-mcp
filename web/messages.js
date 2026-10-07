import { setupTellAgent } from './tell-agent.js';

export function setupMessages(app, doc) {
  const panel = doc.querySelector('#mesh-detail');
  const listPanel = doc.querySelector('#mesh-list');
  const title = doc.querySelector('#message-title');
  const status = doc.querySelector('#message-status');
  const messages = doc.querySelector('#messages');
  const start = doc.querySelector('#message-start');
  const end = doc.querySelector('#message-end');
  const load = doc.querySelector('#message-load');
  const back = doc.querySelector('#message-back');
  let selected;
  let generation = 0;

  async function read() {
    const requestGeneration = ++generation;
    messages.replaceChildren();
    const startDate = new Date(`${start.value}T00:00:00Z`);
    const endDate = new Date(`${end.value}T00:00:00Z`);
    if (!Number.isFinite(+startDate) || !Number.isFinite(+endDate) || startDate > endDate) {
      status.textContent = 'Choose a valid date range (start on or before end).';
      return;
    }
    endDate.setUTCDate(endDate.getUTCDate() + 1);
    const rangeLabel = `${start.value} through ${end.value} UTC`;
    const args = { data_type: selected.id, start_time: startDate.toISOString(), end_time: endDate.toISOString() };
    if (selected.fulcra_userid) args.fulcra_userid = selected.fulcra_userid;
    status.textContent = `Loading messages — calling get_records… ${rangeLabel}`;
    load.disabled = true;
    try {
      const result = await app.callServerTool({ name: 'get_records', arguments: args }, { timeout: 30000 });
      if (generation !== requestGeneration) return;
      const { records, truncated } = parseRecords(result, args.data_type);
      for (const record of records) {
        const item = doc.createElement('li');
        const time = doc.createElement('p');
        const rawTime = record.recorded_at ?? record.start_time;
        const timestamp = typeof rawTime === 'string' ? new Date(rawTime) : null;
        time.textContent = timestamp && Number.isFinite(+timestamp)
          ? `${timestamp.toLocaleString()} (your local time)` : 'Timestamp unavailable';
        const body = doc.createElement('pre');
        body.textContent = messageText(record);
        const label = doc.createElement('label');
        label.textContent = 'Instructions for my agent';
        const input = doc.createElement('textarea');
        input.rows = 3;
        label.append(input);
        const button = doc.createElement('button');
        button.type = 'button';
        button.textContent = 'Tell My Agent';
        const help = doc.createElement('p');
        help.textContent = 'Sends your instruction and this message to your agent in the conversation. Does not directly post a mesh reply. Drafts are cleared when you leave or reload this view.';
        const feedback = doc.createElement('p');
        feedback.setAttribute('role', 'status');
        feedback.setAttribute('aria-live', 'polite');
        setupTellAgent(app, selected, record, input, button, feedback);
        item.append(time, body, label, button, help, feedback);
        messages.append(item);
      }
      status.textContent = truncated
        ? `${records.length} records shown. Partial result — narrow the date range to see the rest.`
        : `${records.length} messages returned for this range${records.length === 0 ? '. No messages in this range.' : '.'}`;
      status.textContent += ` Range: ${rangeLabel}.`;
    } catch {
      if (generation !== requestGeneration) return;
      messages.replaceChildren();
      status.textContent = `Could not load messages (get_records failed or returned an invalid result). Range: ${rangeLabel}. Use Load messages to retry.`;
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
    panel.hidden = true;
    listPanel.hidden = false;
    listPanel.querySelector('button')?.focus();
  });
  return mesh => {
    selected = mesh;
    title.textContent = `${mesh.name} — ${mesh.fulcra_userid ? `Owner: ${mesh.fulcra_userid}` : 'Your outbox'}`;
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

export function parseRecords(result, dataType) {
  if (result.isError) throw new Error('Tool failed');
  const text = result.structuredContent?.result ?? result.content?.find(p => p.type === 'text')?.text;
  if (typeof text !== 'string' || !text.startsWith(`Records for ${dataType} from `)) throw new Error('Unexpected response');
  const separator = text.indexOf(': [');
  if (separator < 0) throw new Error('Missing records');
  const records = JSON.parse(text.slice(separator + 2));
  if (!Array.isArray(records) || !records.every(r => r && typeof r === 'object' && !Array.isArray(r))) throw new Error('Invalid records');
  return { records, truncated: text.slice(0, separator).includes('(showing the first ') };
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
