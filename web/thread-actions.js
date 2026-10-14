import { setupReplySuggestions } from './reply-suggestions.js';
import { clearPostedDraft, matchesPost, messageId, postRecord } from './connection-send.js';
import { unreadMessages } from './unread.js';
import { icon, Send } from './icons.js';
import { sessionHandoff } from './setup-session.js';
const options = { timeout: 15000 };

// Both presentations use the same direct send and separate host-chat handoff.
// Drafts/posts belong to the peer; in-flight host operations belong to the app.
export function setupThreadActions(app, lifecycle, context, container, isCurrent, draft, peerId, orderField, view, changed, presentation) {
  const doc = container.ownerDocument;
  const label = doc.createElement('label');
  const input = doc.createElement('textarea'); input.rows = 1; input.maxLength = 4000; input.className = 'composer-input';
  input.value = draft.value; label.append(input);
  // Grow the input line-by-line up to 4 lines; only then does it scroll.
  const autosize = () => {
    input.style.height = 'auto';
    const s = getComputedStyle(input);
    const border = parseFloat(s.borderTopWidth) + parseFloat(s.borderBottomWidth);
    const max = (parseFloat(s.lineHeight) || 22) * 4 + parseFloat(s.paddingTop) + parseFloat(s.paddingBottom) + border;
    const full = input.scrollHeight + border;
    input.style.overflowY = full > max ? 'auto' : 'hidden';
    input.style.height = `${Math.min(full, max)}px`;
  };
  const send = doc.createElement('button'); send.type = 'button'; send.className = 'primary composer-primary send-to-peer';
  send.append(icon(Send, 'btn-icon'), doc.createTextNode('Send'));
  // Reinforces that this input replies to the contact (not ChatGPT's composer).
  const hint = doc.createElement('p'); hint.className = 'composer-hint';
  const handoff = doc.createElement('button'); handoff.type = 'button'; handoff.className = 'btn-secondary';
  handoff.textContent = `Discuss in ${app.getHostVersion()?.name || 'chat'}`;
  const original = doc.createElement('button'); original.type = 'button'; original.hidden = true;
  original.textContent = 'Open original setup session';
  const transfer = doc.createElement('details'); transfer.hidden = true; transfer.className = 'composer-advanced';
  const transferTitle = doc.createElement('summary'); transferTitle.textContent = 'Copy handoff for original session';
  const transferHelp = doc.createElement('p'); transferHelp.className = 'composer-advanced';
  transferHelp.textContent = 'Opening the session does not transfer your message or context. Copy this handoff first, then paste it there. Or ask in the current chat. The host may block opening the link.';
  const transferText = doc.createElement('textarea'); transferText.readOnly = true; transferText.rows = 6;
  transferText.setAttribute('aria-label', 'Handoff for original session');
  transfer.append(transferTitle, transferText);
  const address = doc.createElement('details'); address.className = 'delivery-address composer-advanced';
  const addressTitle = doc.createElement('summary');
  addressTitle.textContent = 'Delivery address';
  const outboxLabel = doc.createElement('label'); outboxLabel.textContent = 'Your outbox';
  const outbox = doc.createElement('select'); outboxLabel.append(outbox);
  const outboxId = doc.createElement('p'); outboxId.className = 'outbox-id identity-secondary';
  const addressHelp = doc.createElement('p');
  addressHelp.textContent = 'Uses an existing outgoing connection channel only. Everyone in this connection can read the message. No sharing is created.';
  address.append(addressTitle, outboxLabel, outboxId, addressHelp);
  let status = doc.querySelector('#send-status');
  if (!status) {
    status = doc.createElement('p'); status.id = 'send-status'; status.setAttribute('role', 'status');
    doc.querySelector('#context-status').before(status);
  }
  const actions = doc.createElement('div'); actions.className = 'composer-actions';
  actions.append(handoff, send);
  if (orderField) actions.append(orderField);
  container.append(label, actions, hint);
  // Delivery address (and any setup-session handoff) lives in the Advanced panel.
  const advanced = doc.querySelector('#advanced-panel');
  advanced?.querySelectorAll('.composer-advanced').forEach(el => el.remove());
  (advanced ?? container).append(address);
  const supported = Boolean(app.getHostCapabilities()?.message?.text && app.getHostCapabilities()?.updateModelContext?.text);
  if (!supported) status.textContent = 'This host does not support sending a request with separate thread context. Direct connection Send remains available.';
  let updateSuggestions = () => {}, source, sourceIdentity, selectionVersion = 0;
  draft.posts ??= []; draft.acks ??= new Set();
  // Acknowledge each target once; a failure returns it to unread for another try.
  async function ack(targets, body) {
    const audience = view().thread?.expectedPeerUserids, outboxId = source?.id, sender = view().viewingAgent;
    if (!outboxId || !sender.trim()) return false;
    targets = targets.filter(m => !draft.acks.has(m.record.id));
    targets.forEach(m => draft.acks.add(m.record.id)); changed();
    let failed = 0;
    for (const m of targets) {
      try {
        const { response, result } = await postRecord(app, { peer_userid: m.source.fulcra_userid, outbox: outboxId, sender, body,
          mid: messageId(), kind: 'ack', in_reply_to: m.record.id, ...(audience ? { expected_peer_userids: audience } : {}) });
        if (response.isError || result.status !== 'posted') throw new Error('Not posted');
      } catch { draft.acks.delete(m.record.id); failed++; }
    }
    if (failed && isCurrent()) status.textContent = `Could not mark ${failed} message${failed === 1 ? '' : 's'} read. Reopen the contact to try again.`;
    changed();
    return true;
  }
  const update = () => {
    const current = view();
    const contactName = current.thread?.identifier || current.thread?.accountName || 'your contact';
    const placeholder = `Message ${contactName}…`;
    if (input.placeholder !== placeholder) { input.placeholder = placeholder; input.setAttribute('aria-label', placeholder); }
    const host = app.getHostVersion()?.name;
    const hintText = `Goes straight to ${contactName} — not your ${host || 'main'} chat.`;
    if (hint.textContent !== hintText) hint.textContent = hintText;
    const outgoing = current.thread?.sources.filter(s => s.direction === 'Outgoing') ?? [];
    const identity = JSON.stringify(outgoing);
    if (identity !== sourceIdentity) {
      sourceIdentity = identity;
      outbox.replaceChildren();
      const placeholder = doc.createElement('option'); placeholder.value = ''; placeholder.textContent = outgoing.length ? 'Choose an outbox' : 'No outgoing outbox'; outbox.append(placeholder);
      for (const s of outgoing) {
        const option = doc.createElement('option'); option.value = s.id;
        const duplicate = outgoing.some(other => other.id !== s.id && other.name === s.name);
        option.textContent = s.name ? `${s.name}${duplicate ? ` (${s.id})` : ''}` : s.id;
        outbox.append(option);
      }
      draft.outbox = outgoing.some(s => s.id === draft.outbox) ? draft.outbox
        : draft.outbox === undefined && outgoing.length === 1 ? outgoing[0].id : '';
      outbox.value = draft.outbox;
    }
    const selected = outgoing.find(s => s.id === outbox.value);
    if (source?.id !== selected?.id || source?.setupSession !== selected?.setupSession) selectionVersion++;
    source = selected;
    const session = source?.setupSession;
    original.hidden = transfer.hidden = transferHelp.hidden = !session;
    if (session && !original.isConnected) handoff.before(original);
    if (!session) original.remove();
    if (session && !transfer.isConnected) address.before(transferHelp, transfer);
    if (!session) { transferHelp.remove(); transfer.remove(); }
    original.disabled = lifecycle.pending || !isCurrent();
    handoff.textContent = session ? 'Ask in current chat' : `Discuss in ${host || 'chat'}`;
    const copy = session && context() ? sessionHandoff(draft.value, context(), session) : '';
    if (transferText.value !== copy) transferText.value = copy;
    outboxId.textContent = source?.name ? source.id : '';
    outboxId.hidden = !source?.name;
    if (input.value !== draft.value) input.value = draft.value;
    autosize();
    send.disabled = lifecycle.pending || !isCurrent() || !current.ready || !source || !current.viewingAgent?.trim() || !input.value.trim()
      || draft.posts.some(p => p.state === 'sending' || p.state === 'uncertain');
    handoff.disabled = !supported || lifecycle.pending || !isCurrent() || !context();
    updateSuggestions();
  };
  if (presentation === 'thread') updateSuggestions = setupReplySuggestions(app, lifecycle, context, container, isCurrent, input, draft, update);
  input.addEventListener('input', () => { draft.value = input.value; draft.version++; update(); });
  outbox.addEventListener('change', () => { draft.outbox = outbox.value; update(); });
  lifecycle.onChange = update;
  send.addEventListener('click', async () => {
    update(); if (send.disabled) return;
    // Sending answers the newest unread message and acknowledges the rest.
    // Answers name the target's sender; the server finds targets on their channel.
    const audience = view().thread?.expectedPeerUserids;
    const unread = unreadMessages(view().result?.messages ?? [], draft.acks), target = unread.at(-1);
    const peer = target?.source.fulcra_userid ?? audience?.[0] ?? peerId(), mid = messageId(), startedAt = Date.now();
    const envelope = { id: mid, sender: view().viewingAgent, kind: target ? 'reply' : 'message', priority: 'P2',
      topic: target?.record.topic ?? 'chat', body: input.value, ...(target ? { in_reply_to: target.record.id } : {}) };
    const posted = () => {
      report('Posted to your outbox; not confirmed delivered or read by the peer.');
      ack(unread.slice(0, -1), 'Read; see my reply.');
    };
    const { identifier: _identifier, setupSession: _setupSession, assessment: _assessment, direction: _direction, ...provenance } = source;
    const post = { source: provenance, direction: 'Outgoing', envelope, state: 'sending', version: draft.version,
      record: { ...envelope, start_time: new Date().toISOString() } };
    const report = text => { status.textContent = `Peer ${peer}, message ${mid}: ${text}`; };
    draft.value = '';
    draft.posts.push(post); lifecycle.pending = true; changed(); update();
    report('Posting…');
    try {
      const { response, result } = await postRecord(app, { peer_userid: peer, outbox: post.source.id,
        sender: envelope.sender, body: envelope.body, mid, ...(target ? { kind: 'reply', in_reply_to: target.record.id } : {}),
        ...(audience ? { expected_peer_userids: audience } : {}) });
      if (post.state === 'posted' || (!response.isError && result.status === 'posted' && result.mid === mid
          && result.outbox === post.source.id && result.peer_userid === peer
          && result.record && matchesPost({ ...post, record: result.record }, post))) {
        post.state = 'posted'; if (result.record) post.record = result.record;
        clearPostedDraft(draft, post);
        posted();
      } else if (!response.isError && result.status === 'rejected' && result.mid === mid && result.outbox === post.source.id) {
        draft.posts = draft.posts.filter(p => p !== post);
        if (draft.version === post.version) draft.value = envelope.body;
        report(`Message not posted. ${result.reason ?? ''} Draft retained.`);
      } else throw new Error('Unconfirmed');
    } catch {
      // Polling may prove the exact write even while its response is lost.
      if (post.state === 'posted') posted();
      else {
        report('Sending… Waiting for confirmation.');
        const waitingStatus = status.textContent;
        // Allow ingestion/polling to confirm the write before showing uncertainty.
        setTimeout(() => {
          if (post.state !== 'sending') return;
          post.state = 'uncertain';
          if (draft.version === post.version) draft.value = envelope.body;
          if (status.textContent === waitingStatus) report('Posting unconfirmed. Draft retained; Send is paused for this peer. Check the outbox for this message ID before retrying.');
          changed(); lifecycle.onChange();
        }, Math.max(0, 60000 - (Date.now() - startedAt)));
      }
    } finally { lifecycle.pending = false; changed(); lifecycle.onChange(); }
  });
  original.addEventListener('click', async () => {
    update(); if (original.disabled || !source?.setupSession) return;
    const url = source.setupSession, outboxId = source.id, peer = peerId();
    const token = lifecycle.token(), version = selectionVersion;
    // Never pair a late navigation result with another display's copyable handoff.
    const report = text => {
      if (isCurrent() && lifecycle.current(token) && peerId() === peer && selectionVersion === version
          && source?.id === outboxId && source?.setupSession === url) status.textContent = text;
    };
    lifecycle.pending = true; update();
    try {
      const result = await app.openLink({ url }, options);
      if (result.isError) throw new Error('Host rejected link');
      report('Host accepted the request to open the original setup session. Your message and context were not transferred; copy the handoff and paste it there.');
    } catch {
      report(`The host could not confirm opening the original setup session. Open ${url} manually and copy the handoff, or ask in the current chat. Your draft is unchanged.`);
    } finally { lifecycle.pending = false; lifecycle.onChange(); }
  });
  handoff.addEventListener('click', async () => {
    update(); if (handoff.disabled) return;
    const submitted = input.value;
    const session = source?.setupSession, snapshot = context();
    const text = sessionHandoff(submitted, snapshot, session);
    const version = draft.version, token = lifecycle.token();
    const origin = `Submitted request #${++lifecycle.requestSequence} for peer ID ${JSON.stringify(peerId())} (not the current draft): `;
    const report = message => { status.textContent = origin + message; };
    const current = () => isCurrent() && lifecycle.current(token) && source?.setupSession === session;
    const restore = () => { if (draft.version === version) draft.value = submitted; };
    draft.value = '';
    lifecycle.pending = true; update();
    let attempted = false;
    report('Attaching displayed context before sending…');
    try {
      if (!await lifecycle.attach(snapshot, token) || !current()) {
        restore();
        report('Context changed before sending. No message sent; draft retained.'); return;
      }
      attempted = true; report('Awaiting host confirmation…');
      const result = await app.sendMessage({ role: 'user', content: [{ type: 'text', text }] }, options);
      if (result.isError) throw new Error('Host rejected message');
      report('Request accepted by the host. Check the conversation for the response; no connection reply was posted by this handoff.');
      if (draft.version === version) { draft.value = ''; draft.version++; }
    } catch {
      restore();
      report(attempted ? 'Could not confirm delivery. Check the conversation before retrying; draft retained.'
        : 'Could not confirm context attachment. No message sent; draft retained.');
    } finally { lifecycle.pending = false; lifecycle.onChange(); }
  });
  update();
  update.markRead = messages => ack(messages, 'Read.');
  return update;
}
