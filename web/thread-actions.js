import { setupReplySuggestions } from './reply-suggestions.js';
import { threadTitle } from './mesh-identifier.js';
import { clearPostedDraft, matchesPost, messageId, recipientAgent } from './mesh-send.js';
import { icon, Send } from './icons.js';
const options = { timeout: 15000 };

// Both presentations use the same direct send and separate host-chat handoff.
// Drafts/posts belong to the peer; in-flight host operations belong to the app.
export function setupThreadActions(app, lifecycle, context, container, isCurrent, draft, peerId, orderField, view, changed, presentation) {
  const doc = container.ownerDocument;
  const label = doc.createElement('label'), caption = doc.createElement('span');
  const input = doc.createElement('textarea'); input.rows = 2; input.maxLength = 24000;
  input.value = draft.value; label.append(caption, input);
  const send = doc.createElement('button'); send.type = 'button'; send.className = 'primary composer-primary';
  send.append(icon(Send, 'btn-icon'), doc.createTextNode('Send'));
  const handoff = doc.createElement('button'); handoff.type = 'button';
  handoff.textContent = 'talk with my agent about this thread';
  const address = doc.createElement('details'), addressTitle = doc.createElement('summary');
  addressTitle.textContent = 'Delivery address';
  const outboxLabel = doc.createElement('label'); outboxLabel.textContent = 'Your outbox';
  const outbox = doc.createElement('select'); outboxLabel.append(outbox);
  const agentLabel = doc.createElement('label'); agentLabel.textContent = 'Recipient agent (exact name)';
  const agent = doc.createElement('input'); agent.type = 'text'; agent.maxLength = 200; agentLabel.append(agent);
  const addressHelp = doc.createElement('p');
  addressHelp.textContent = 'Uses an existing outgoing channel only. Confirm the exact recipient agent if no unique address is available from displayed outgoing messages. No sharing is created.';
  address.append(addressTitle, outboxLabel, agentLabel, addressHelp);
  let status = doc.querySelector('#send-status');
  if (!status) {
    status = doc.createElement('p'); status.id = 'send-status'; status.setAttribute('role', 'status');
    doc.querySelector('#context-status').before(status);
  }
  const actions = doc.createElement('div'); actions.className = 'composer-actions';
  actions.append(send, handoff);
  if (orderField) actions.append(orderField);
  container.append(label, actions, address);
  const supported = Boolean(app.getHostCapabilities()?.message?.text && app.getHostCapabilities()?.updateModelContext?.text);
  if (!supported) status.textContent = 'This host does not support sending a request with separate thread context. Direct mesh Send remains available.';
  let updateSuggestions = () => {}, source, sourceIdentity;
  draft.posts ??= []; draft.agents ??= {};
  const update = () => {
    const current = view();
    caption.textContent = `Talk to ${current.thread ? threadTitle(current.thread) : peerId() ?? 'this thread'}`;
    const outgoing = current.thread?.sources.filter(s => s.direction === 'Outgoing') ?? [];
    const identity = JSON.stringify(outgoing);
    if (identity !== sourceIdentity) {
      sourceIdentity = identity;
      outbox.replaceChildren();
      const placeholder = doc.createElement('option'); placeholder.value = ''; placeholder.textContent = outgoing.length ? 'Choose an outbox' : 'No outgoing outbox'; outbox.append(placeholder);
      for (const s of outgoing) { const option = doc.createElement('option'); option.value = s.id; option.textContent = `${s.name} (${s.id})`; outbox.append(option); }
      draft.outbox = outgoing.some(s => s.id === draft.outbox) ? draft.outbox : outgoing.length === 1 ? outgoing[0].id : '';
      outbox.value = draft.outbox;
    }
    source = outgoing.find(s => s.id === outbox.value);
    const inferred = source ? recipientAgent(current.result?.messages ?? [], source, peerId()) : '';
    const agentValue = draft.agents[outbox.value] ?? inferred;
    if (agent.value !== agentValue) agent.value = agentValue;
    if (input.value !== draft.value) input.value = draft.value;
    send.disabled = lifecycle.pending || !isCurrent() || !current.ready || !source || !agent.value.trim() || !input.value.trim()
      || draft.posts.some(p => p.state === 'sending' || p.state === 'uncertain');
    handoff.disabled = !supported || lifecycle.pending || !isCurrent() || !context();
    updateSuggestions();
  };
  if (presentation === 'thread') updateSuggestions = setupReplySuggestions(app, lifecycle, context, container, isCurrent, input, draft, update);
  input.addEventListener('input', () => { draft.value = input.value; draft.version++; update(); });
  agent.addEventListener('input', () => { draft.agents[outbox.value] = agent.value; update(); });
  outbox.addEventListener('change', () => { draft.outbox = outbox.value; update(); });
  lifecycle.onChange = update;
  send.addEventListener('click', async () => {
    update(); if (send.disabled) return;
    const peer = peerId(), mid = messageId();
    const envelope = { v: 1, mid, to: agent.value, to_user: peer, kind: 'directive', pri: 'P2', slug: 'mesh-message', body: input.value };
    const { identifier: _identifier, direction: _direction, ...provenance } = source;
    const post = { source: provenance, direction: 'Outgoing', envelope, state: 'sending', version: draft.version,
      record: { id: mid, recorded_at: new Date().toISOString(), note: JSON.stringify(envelope) } };
    const report = text => { status.textContent = `Peer ${peer}, message ${mid}: ${text}`; };
    draft.posts.push(post); lifecycle.pending = true; changed(); update();
    report('Posting…');
    try {
      const response = await app.callServerTool({ name: 'mesh_send', arguments: {
        peer_userid: peer, outbox: post.source.id, peer_agent: envelope.to, body: envelope.body, mid,
      } }, { timeout: 30000 });
      const result = response.structuredContent ?? JSON.parse(response.content?.find(c => c.type === 'text')?.text ?? '{}');
      if (post.state === 'posted' || (!response.isError && result.status === 'posted' && result.mid === mid
          && result.outbox === post.source.id && result.peer_userid === peer
          && result.record && matchesPost({ ...post, record: result.record }, post))) {
        post.state = 'posted'; if (result.record) post.record = result.record;
        clearPostedDraft(draft, post);
        report('Posted to your outbox; not confirmed delivered or read by the peer.');
      } else if (!response.isError && result.status === 'rejected' && result.mid === mid && result.outbox === post.source.id) {
        draft.posts = draft.posts.filter(p => p !== post);
        report(`Message not posted. ${result.reason ?? ''} Draft retained.`);
      } else throw new Error('Unconfirmed');
    } catch {
      // Polling may prove the exact write even while its response is lost.
      if (post.state === 'posted') report('Posted to your outbox; not confirmed delivered or read by the peer.');
      else {
        post.state = 'uncertain';
        report('Posting unconfirmed. Draft retained; Send is paused for this peer. Check the outbox for this message ID before retrying.');
      }
    } finally { lifecycle.pending = false; changed(); lifecycle.onChange(); }
  });
  handoff.addEventListener('click', async () => {
    update(); if (handoff.disabled) return;
    const text = input.value.trim() ? input.value : 'Let’s talk about this mesh thread.';
    const version = draft.version, token = lifecycle.token();
    const origin = `Submitted request #${++lifecycle.requestSequence} for peer ID ${JSON.stringify(peerId())} (not the current draft): `;
    const report = message => { status.textContent = origin + message; };
    const current = () => isCurrent() && lifecycle.current(token);
    lifecycle.pending = true; update();
    let attempted = false;
    report('Attaching displayed context before sending…');
    try {
      if (!await lifecycle.attach(context(), token) || !current()) {
        report('Context changed before sending. No message sent; draft retained.'); return;
      }
      attempted = true; report('Awaiting host confirmation…');
      const result = await app.sendMessage({ role: 'user', content: [{ type: 'text', text }] }, options);
      if (result.isError) throw new Error('Host rejected message');
      report('Request accepted by the host. Check the conversation for the response; no mesh reply was posted by this handoff.');
      if (draft.version === version) { draft.value = ''; draft.version++; }
    } catch {
      report(attempted ? 'Could not confirm delivery. Check the conversation before retrying; draft retained.'
        : 'Could not confirm context attachment. No message sent; draft retained.');
    } finally { lifecycle.pending = false; lifecycle.onChange(); }
  });
  update();
  return update;
}
