// Source-qualified identity; fallback preserves id-less records and duplicates.
export function messageKeys(messages) {
  const seen = new Map();
  return messages.map(({ source, record }) => {
    const base = JSON.stringify([source.fulcra_userid, source.id, record.id ?? record]);
    const occurrence = seen.get(base) ?? 0;
    seen.set(base, occurrence + 1);
    return `${base}/${occurrence}`;
  });
}

// Chat order is always oldest first; only the message pane owns its scrolling.
export function createMessageList(list, renderRow) {
  const doc = list.ownerDocument, win = doc.defaultView;
  const scroller = doc.querySelector('#message-area');
  let rows = new Map(), following = true;
  const top = () => scroller.getBoundingClientRect().top;
  const bottom = () => scroller.getBoundingClientRect().bottom - 12;
  const scrollBy = delta => { scroller.scrollTop += delta; };
  // The composer is the scroller's last child; "latest" means it's visible near the
  // bottom. Scrolled up into history it drops below the fold.
  function atLatest() {
    const last = scroller.lastElementChild;
    if (!last) return true;
    const resizeDelta = Math.max(0, paneHeight - scroller.clientHeight);
    return last.getBoundingClientRect().bottom <= scroller.getBoundingClientRect().bottom + 40 + resizeDelta;
  }
  // Default resting position leaves 1/8 of the viewport below the input; the pane
  // keeps extra bottom room (padding) so the user can still scroll it further up.
  function follow() {
    const last = scroller.lastElementChild;
    if (!last) { scroller.scrollTop = scroller.scrollHeight; return; }
    const target = scroller.getBoundingClientRect().bottom - win.innerHeight / 8;
    scrollBy(last.getBoundingClientRect().bottom - target);
  }
  let paneHeight = scroller.clientHeight;
  const onScroll = () => {
    // A resize may dispatch scroll before ResizeObserver. Preserve the old
    // latest-edge intent until the new pane geometry has been applied.
    if (scroller.clientHeight === paneHeight) following = atLatest();
  };
  scroller.addEventListener('scroll', onScroll);
  const resize = new win.ResizeObserver(() => {
    paneHeight = scroller.clientHeight;
    if (following) follow();
  });
  resize.observe(scroller);
  function anchors() {
    // Readers above the list retain the history/advanced controls, not a row.
    if (list.firstElementChild?.getBoundingClientRect().top > top() + 40) return [];
    return [...list.children].map(el => ({ el, top: el.getBoundingClientRect().top }))
      .filter(({ el, top: rowTop }) => rowTop < bottom() && el.getBoundingClientRect().bottom > top());
  }
  function restore(saved) {
    const anchor = saved.find(({ el }) => el.isConnected);
    if (anchor) scrollBy(anchor.el.getBoundingClientRect().top - anchor.top);
  }
  return {
    reveal(element) {
      // Explicit navigation takes precedence before scroll/resize delivery.
      following = false;
      scrollBy(element.getBoundingClientRect().top - top());
    },
    preservePosition(change) {
      const saved = anchors();
      change();
      restore(saved);
    },
    update(messages, afterRender) {
      const hadRows = rows.size > 0, followEdge = atLatest(), saved = anchors();
      const keys = messageKeys(messages), next = new Map();
      const added = keys.some(key => !rows.has(key));
      const selection = win.getSelection();
      const savedSelection = selection && list.contains(selection.anchorNode) && list.contains(selection.focusNode)
        ? { anchor: selection.anchorNode, anchorOffset: selection.anchorOffset, focus: selection.focusNode, focusOffset: selection.focusOffset } : null;
      let cursor = list.firstElementChild;
      messages.forEach((message, index) => {
        const key = keys[index];
        const row = rows.get(key) ?? doc.createElement('li');
        renderRow(row, message);
        next.set(key, row);
        if (row !== cursor) list.insertBefore(row, cursor);
        cursor = row.nextElementSibling;
        if (!rows.has(key) && !win.matchMedia('(prefers-reduced-motion: reduce)').matches) {
          // Animate content, not the measured row: reader anchors stay stable.
          for (const child of row.children) child.animate([
            { opacity: 0, transform: 'translateY(4px)' },
            { opacity: 1, transform: 'translateY(0)' },
          ], { duration: 180, easing: 'ease-out' });
        }
      });
      for (const [key, row] of rows) if (!next.has(key)) row.remove();
      rows = next;
      if (savedSelection?.anchor.isConnected && savedSelection.focus.isConnected) {
        const { anchor, anchorOffset, focus, focusOffset } = savedSelection;
        selection.setBaseAndExtent(anchor, anchorOffset, focus, focusOffset);
      }
      afterRender();
      if (!hadRows && messages.length) follow();
      else if (hadRows && followEdge && added && !doc.activeElement?.matches('input, textarea, summary, select')) follow();
      else restore(saved);
      following = atLatest();
    },
    clear() { rows.clear(); list.replaceChildren(); following = true; },
    dispose() { resize.disconnect(); scroller.removeEventListener('scroll', onScroll); },
  };
}
