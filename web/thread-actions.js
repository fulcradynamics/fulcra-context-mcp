import { clearPostedDraft, matchesPost, messageId, postRecord } from './connection-send.js';
import { unreadMessages } from './unread.js';
import { availableSources, resolveOutbox, selectedSources, sourceKey } from './incoming-sources.js';
import { icon, Send } from './icons.js';
import { sessionHandoff } from './setup-session.js';
import { showToast, continueMessage, spinButton } from './toast.js';
import { contactName, readable } from './contact-identity.js';
import { hostLabel } from './host-label.js';
const options = { timeout: 15000 };

// Both presentations use the same direct send and separate host-chat handoff.
// Drafts/posts belong to the peer; in-flight host operations belong to the app.
export function setupThreadActions(app, lifecycle, context, container, isCurrent, draft, peerId, view, changed, presentation = 'global') {
  const doc = container.ownerDocument;
  const inlineList = presentation === 'thread';
  const label = doc.createElement('label');
  const input = doc.createElement('textarea'); input.rows = 1; input.maxLength = 4000; input.className = 'composer-input';
  input.value = draft.value; label.append(input);
  // Grow up to four lines (two on narrow screens), then scroll the draft.
  const autosize = () => {
    const edge = doc.querySelector('#messages')?.lastElementChild?.getBoundingClientRect();
    const follow = doc.activeElement === input && edge && Math.abs(edge.bottom - container.getBoundingClientRect().top) <= 40;
    input.style.height = 'auto';
    const s = getComputedStyle(input);
    const border = parseFloat(s.borderTopWidth) + parseFloat(s.borderBottomWidth);
    const lines = parseFloat(s.getPropertyValue('--composer-lines')) || 4;
    const max = (parseFloat(s.lineHeight) || 22) * lines + parseFloat(s.paddingTop) + parseFloat(s.paddingBottom) + border;
    const full = input.scrollHeight + border;
    input.style.overflowY = full > max ? 'auto' : 'hidden';
    input.style.height = `${Math.min(full, max)}px`;
    if (follow) doc.querySelector('#message-area').scrollTop += edge.bottom - container.getBoundingClientRect().top + 12;
  };
  const send = doc.createElement('button'); send.type = 'button'; send.className = 'primary composer-primary send-to-peer';
  send.append(icon(Send, 'btn-icon'), doc.createTextNode('Send'));
  // Reinforces that this input replies to the contact (not ChatGPT's composer).
  const hint = doc.createElement('p'); hint.className = 'composer-hint';
  const handoff = doc.createElement('button'); handoff.type = 'button'; handoff.className = 'btn-secondary';
  handoff.textContent = `Continue in ${hostLabel(app.getHostVersion()?.name) || 'chat'}`;
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
  // Send/handoff outcomes speak through per-message badges and transient toasts —
  // there is no persistent status line under the composer.
  const notify = (title, description) => showToast(doc, { title, description });
  const actions = doc.createElement('div'); actions.className = 'composer-actions';
  actions.append(handoff, send);
  container.append(label, actions, hint);
  // Delivery address (and any setup-session handoff) lives in the Advanced panel.
  const advanced = doc.querySelector('#advanced-panel');
  advanced?.querySelectorAll('.composer-advanced').forEach(el => el.remove());
  (advanced ?? container).append(address);
  const supported = Boolean(app.getHostCapabilities()?.message?.text && app.getHostCapabilities()?.updateModelContext?.text);
  let source, sourceIdentity, selectionVersion = 0, sending = false;
  draft.posts ??= []; draft.acks ??= new Map();
  // Peer-owned attempts survive remounts. Never allocate a second ID for a target,
  // including after a lost response or rejection; polling only reconciles reads.
  const ackAddress = () => ({ audience: view().thread?.expectedPeerUserids, outboxId: source?.id, sender: view().viewingAgent });
  async function ack(targets, { audience, outboxId, sender } = ackAddress()) {
    if (!outboxId || !sender?.trim()) return false;
    const attempts = targets.filter(m => !draft.acks.has(m.record.id)).map(m => {
      const attempt = { state: 'sending', args: { peer_userid: m.source.fulcra_userid, outbox: outboxId, sender, body: 'ack',
        mid: messageId(), kind: 'ack', in_reply_to: m.record.id, ...(audience ? { expected_peer_userids: audience } : {}) } };
      draft.acks.set(m.record.id, attempt);
      return attempt;
    });
    changed();
    for (const attempt of attempts) {
      try {
        const { response, result } = await postRecord(app, attempt.args);
        if (attempt.state === 'posted') continue; // Readback can beat the response.
        attempt.state = !response.isError && result.mid === attempt.args.mid && result.outbox === outboxId
          && ['posted', 'rejected'].includes(result.status) ? result.status : 'uncertain';
      } catch { if (attempt.state !== 'posted') attempt.state = 'uncertain'; }
      changed();
    }
    // Marking-read runs quietly in the background; only surface a failure, and only
    // once, as a transient toast rather than a persistent status line.
    if (isCurrent() && attempts.some(a => a.state === 'rejected' || a.state === 'uncertain'))
      notify('Couldn’t confirm messages read', 'The read state is kept and no duplicate will be sent.');
    return true;
  }
  const update = () => {
    const current = view();
    const name = contactName(current.thread);
    const placeholder = `Message ${name}…`;
    if (input.placeholder !== placeholder) { input.placeholder = placeholder; input.setAttribute('aria-label', placeholder); }
    const host = hostLabel(app.getHostVersion()?.name);
    const selectionWarning = current.thread?.warnings.find(w => /^(Choose an outbox|Multiple incoming channels)/.test(w));
    const hintText = selectionWarning ?? (supported
      ? `Send replies to ${name}; Continue in ${host || 'chat'} to work on it there.`
      : `Send replies to ${name} directly. Continue in chat isn’t available on this host.`);
    if (hint.textContent !== hintText) hint.textContent = hintText;
    const outgoing = (current.thread ? availableSources(current.thread).filter(s => s.direction === 'Outgoing') : [])
      .sort((a, b) => (b.sharedAt ?? 0) - (a.sharedAt ?? 0) || a.id.localeCompare(b.id));
    const identity = JSON.stringify(outgoing);
    if (identity !== sourceIdentity) {
      sourceIdentity = identity;
      outbox.replaceChildren();
      const placeholder = doc.createElement('option'); placeholder.value = ''; placeholder.textContent = outgoing.length ? 'Choose an outbox' : 'No outgoing outbox'; outbox.append(placeholder);
      for (const s of outgoing) {
        const option = doc.createElement('option'); option.value = s.id;
        const duplicate = outgoing.some(other => other.id !== s.id && other.name === s.name);
        option.textContent = `${readable(s.name, 'Outbox')}${duplicate ? ` (${outgoing.indexOf(s) + 1})` : ''}`;
        outbox.append(option);
      }
      draft.outbox = outgoing.some(s => s.id === draft.outbox) ? draft.outbox
        : draft.outbox === undefined && current.thread ? resolveOutbox(current.thread)?.id ?? '' : '';
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
    // Leave the label (and its spinner) alone while a handoff is in flight.
    if (!sending) handoff.textContent = session ? 'Ask in current chat' : `Continue in ${host || 'chat'}`;
    const copy = session && context() ? sessionHandoff(draft.value, context(), session) : '';
    if (transferText.value !== copy) transferText.value = copy;
    outboxId.textContent = source?.name ? source.id : '';
    outboxId.hidden = !source?.name;
    if (input.value !== draft.value) input.value = draft.value;
    autosize();
    send.disabled = lifecycle.pending || !isCurrent() || !current.ready || !source || !current.viewingAgent?.trim() || !input.value.trim()
      || draft.posts.some(p => p.state === 'sending' || p.state === 'uncertain');
    handoff.disabled = sending || !supported || lifecycle.pending || draft.handoffUncertain || !isCurrent() || !context();
  };
  input.addEventListener('input', () => { draft.value = input.value; draft.version++; update(); });
  outbox.addEventListener('change', () => { draft.outbox = outbox.value; draft.excludedSources = undefined; changed('sources'); update(); });
  lifecycle.onChange = update;
  send.addEventListener('click', async () => {
    update(); if (send.disabled) return;
    // Sending answers the newest unread message and acknowledges the rest.
    // Answers name the target's sender; the server finds targets on their channel.
    const audience = view().thread?.expectedPeerUserids;
    const acknowledgementAddress = ackAddress();
    const allowed = selectedSources(view().thread, draft.excludedSources, source.id).sources.map(sourceKey);
    const unread = unreadMessages((view().result?.messages ?? []).filter(m => allowed.includes(sourceKey(m.source))), draft.acks), target = unread.at(-1);
    const peer = target?.source.fulcra_userid ?? audience?.[0] ?? peerId(), mid = messageId(), startedAt = Date.now();
    const envelope = { id: mid, sender: view().viewingAgent, kind: target ? 'reply' : 'message', priority: 'P2',
      topic: target?.record.topic ?? 'chat', body: input.value, ...(target ? { in_reply_to: target.record.id } : {}) };
    // Progress and success show as the message's own badge (sending… → sent).
    const posted = () => { ack(unread.slice(0, -1), acknowledgementAddress); };
    const { identifier: _identifier, setupSession: _setupSession, assessment: _assessment, direction: _direction, ...provenance } = source;
    const post = { source: provenance, direction: 'Outgoing', envelope, state: 'sending', version: draft.version,
      record: { ...envelope, start_time: new Date().toISOString() } };
    draft.value = '';
    draft.posts.push(post); lifecycle.pending = true; changed(); update();
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
        // Rejected: the message leaves the thread and returns to the composer, so a
        // toast (not a bubble) carries the news.
        draft.posts = draft.posts.filter(p => p !== post);
        if (draft.version === post.version) draft.value = envelope.body;
        notify('Couldn’t send', result.reason ? result.reason : 'Your message is back in the box — try again.');
      } else throw new Error('Unconfirmed');
    } catch {
      // Polling may prove the exact write even while its response is lost.
      if (post.state === 'posted') posted();
      else {
        // Allow ingestion/polling to confirm the write before showing uncertainty.
        setTimeout(() => {
          if (post.state !== 'sending') return;
          // The bubble flips to "not confirmed"; a toast warns against resending
          // blind, since the message may actually have gone out.
          post.state = 'uncertain';
          if (draft.version === post.version) draft.value = envelope.body;
          notify('Couldn’t confirm your message', 'Check the conversation before sending it again — it may have gone through.');
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
    const report = (title, description) => {
      if (isCurrent() && lifecycle.current(token) && peerId() === peer && selectionVersion === version
          && source?.id === outboxId && source?.setupSession === url) notify(title, description);
    };
    lifecycle.pending = true; update();
    try {
      const result = await app.openLink({ url }, options);
      if (result.isError) throw new Error('Host rejected link');
      report('Opening the setup session', 'Your message and context don’t carry over — copy the handoff and paste it there.');
    } catch {
      report('Couldn’t open the setup session', 'Open the link yourself and copy the handoff, or ask in the current chat. Your draft is unchanged.');
    } finally { lifecycle.pending = false; lifecycle.onChange(); }
  });
  handoff.addEventListener('click', async () => {
    update(); if (handoff.disabled) return;
    const submitted = input.value;
    const session = source?.setupSession, snapshot = context();
    const text = sessionHandoff(submitted, snapshot, session);
    const version = draft.version, token = lifecycle.token();
    const host = hostLabel(app.getHostVersion()?.name);
    const current = () => isCurrent() && lifecycle.current(token) && source?.setupSession === session;
    const restore = () => { if (draft.version === version) draft.value = submitted; };
    // Progress shows on the button spinner; outcomes speak through toasts.
    draft.value = '';
    sending = true; const stopSpinner = spinButton(handoff);
    lifecycle.pending = true; update();
    let attempted = false;
    try {
      if (!await lifecycle.attach(snapshot, token) || !current()) {
        restore();
        notify('Nothing sent', 'This conversation changed while sending, so nothing went out. Your draft was kept.'); return;
      }
      attempted = true;
      const result = await app.sendMessage({ role: 'user', content: [{ type: 'text', text }] }, options);
      if (result.isError) {
        restore(); notify(host ? `Couldn’t reach ${host}` : 'Couldn’t send', 'Nothing was sent. Your draft was kept — try again.'); return;
      }
      if (current()) notify(host ? `Request sent to ${host}` : 'Request sent', continueMessage(app, inlineList));
      if (draft.version === version) { draft.value = ''; draft.version++; }
    } catch {
      restore();
      if (attempted) draft.handoffUncertain = true;
      notify(attempted ? 'Couldn’t confirm your request' : 'Couldn’t send',
        attempted ? `Check ${host || 'your chat'} to see whether it arrived. Your draft was kept.` : 'Nothing was sent. Your draft was kept — try again.');
    } finally { sending = false; stopSpinner(); lifecycle.pending = false; lifecycle.onChange(); }
  });
  update();
  update.markRead = ack;
  return update;
}
