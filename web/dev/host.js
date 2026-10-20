// Browser-side mock MCP host for the dev harness. Embeds the real built app
// (contacts.html) in a sandboxed iframe and answers its SDK postMessage calls
// with mock data, so the global entry point can be iterated on without a tunnel,
// ChatGPT, or a live account. Dev-only; never shipped in the built app.
import { scenario, own } from './mock-data.js';

// Preview empty states using the same app/SDK bridge, not a replacement mock UI.
const state = new URLSearchParams(location.search).get('state');
if (state === 'no-history') scenario.rows = {};
if (state === 'no-contacts') {
  scenario.catalog = []; scenario.rows = {};
  scenario.shares = { own_fulcra_userid: own, incoming: [], outgoing: [] };
}
const checkStatus = state === 'no-schedule' ? { status: 'not_set_up', label: 'Not set up' }
  : { status: 'checked', last_checked: new Date(Date.now() - 20 * 60000).toISOString() };

const CATALOG_PREFIX = 'Available data types, grouped by compatible tool: ';
const text = t => ({ content: [{ type: 'text', text: t }] });

// Mirrors the production tool responses the app parses (catalog / shares /
// records); writes update only this page's in-memory fixture, never an account.
function toolResult(name, args = {}) {
  if (scenario.fail?.includes(name)) return { isError: true };
  if (name === 'match_agent_invitations') return { structuredContent: { results: [] } };
  if (name === 'fulcra_check_status') return { structuredContent: checkStatus };
  if (name === 'get_data_catalog') {
    let catalog = scenario.catalog;
    if (args.data_type) catalog = catalog.filter(e => e.id === args.data_type && (e.fulcra_userid || own) === (args.fulcra_userid || own));
    return text(CATALOG_PREFIX + JSON.stringify({ 'data types usable with: get_records': catalog }));
  }
  if (name === 'list_shares') return text('Shares: ' + JSON.stringify(scenario.shares));
  if (name === 'get_records') {
    const rows = scenario.rows[`${args.fulcra_userid ?? own}/${args.data_type}`] ?? [];
    return text(`Records for ${args.data_type} from a to b: ${JSON.stringify(rows)}`);
  }
  if (name === 'agent_connection_send') {
    const rows = scenario.rows[`${own}/${args.outbox}`];
    if (!rows) return { isError: true, ...text('Unknown mock outbox') };
    let record = rows.find(row => row.id === args.mid);
    if (!record) {
      record = { id: args.mid, sender: args.sender, body: args.body, kind: args.kind ?? 'message',
        start_time: new Date().toISOString(),
        ...(args.in_reply_to ? { in_reply_to: args.in_reply_to } : {}) };
      rows.push(record);
    }
    return { structuredContent: { status: 'posted', mid: args.mid, outbox: args.outbox,
      peer_userid: args.peer_userid, peer_acknowledged: false, record } };
  }
  return { isError: true, ...text(`Unsupported mock tool: ${name}`) };
}

const frame = document.querySelector('#app');
const reply = (id, result) => frame.contentWindow.postMessage({ jsonrpc: '2.0', id, result }, '*');

addEventListener('message', ({ data: r, source }) => {
  if (source !== frame.contentWindow || !r || r.jsonrpc !== '2.0') return;
  if (r.method === 'ui/initialize') {
    reply(r.id, {
      protocolVersion: '2026-01-26',
      hostInfo: { name: 'ChatGPT', version: '1' }, // simulate the real host name
      hostCapabilities: { message: { text: {} }, updateModelContext: { text: {} }, sampling: {} },
      // bottom inset matches the simulated composer bar in host.html so footer
      // clearance can be eyeballed the way ChatGPT would report it.
      hostContext: { displayMode: 'fullscreen', availableDisplayModes: ['fullscreen', 'pip'],
        safeAreaInsets: { top: 0, right: 0, bottom: 56, left: 0 } },
    });
  } else if (r.method === 'tools/call') {
    const name = r.params?.name, args = r.params?.arguments ?? {};
    const result = toolResult(name, args);
    // Slow the whole-account discovery calls so the loading spinner is visible on
    // initial load and when "Refresh contacts" is clicked; keep reads snappy.
    const slow = name === 'list_shares' || (name === 'get_data_catalog' && !args.data_type);
    if (slow) setTimeout(() => reply(r.id, result), 2000);
    else reply(r.id, result);
  } else if (r.method === 'ui/request-display-mode') {
    reply(r.id, { mode: r.params?.mode ?? 'fullscreen' });
  } else if (r.method === 'ui/create-sampling-message') {
    reply(r.id, { role: 'assistant', stopReason: 'endTurn',
      content: { type: 'text', text: JSON.stringify(['Sounds good — let’s do it.', 'Thanks, I’ll follow up tomorrow.']) } });
  } else if (r.method === 'ui/message' || r.method === 'ui/update-model-context') {
    reply(r.id, {});
  } else if (r.id !== undefined && typeof r.method === 'string' && r.method.startsWith('ui/')) {
    reply(r.id, {}); // Acknowledge any other request so the SDK never hangs.
  }
  // Notifications (no id) need no response.
});

// Load the real built app bundle into the sandboxed iframe.
fetch('contacts.html').then(res => res.text()).then(html => { frame.srcdoc = html; });
