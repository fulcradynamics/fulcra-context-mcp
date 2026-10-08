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

export function createMessageList(list, activity, order, renderRow) {
  const doc = list.ownerDocument, win = doc.defaultView;
  let rows = new Map();
  const latest = () => order.value === 'latest' ? list.firstElementChild : list.lastElementChild;
  const bottom = () => win.innerHeight - parseFloat(win.getComputedStyle(doc.body).paddingBottom);
  function atLatest() {
    const edge = latest()?.getBoundingClientRect();
    return !edge || (order.value === 'latest' ? Math.abs(edge.top) <= 40 : edge.bottom <= bottom() + 40);
  }
  function follow() {
    const edge = latest()?.getBoundingClientRect();
    if (edge) win.scrollBy(0, order.value === 'latest' ? edge.top : edge.bottom - bottom());
    activity.hidden = true;
  }
  activity.addEventListener('click', follow);
  const onScroll = () => { if (atLatest()) activity.hidden = true; };
  win.addEventListener('scroll', onScroll, { passive: true });
  return {
    update(messages, afterRender) {
      const hadRows = rows.size > 0;
      const followEdge = atLatest();
      // Above-list readers keep their viewport, even if a message peeks below
      // the controls. Anchoring that row would scroll the controls away on prepend.
      const aboveList = list.firstElementChild?.getBoundingClientRect().top > 40;
      const anchors = aboveList ? [] : [...list.children].map(el => ({ el, top: el.getBoundingClientRect().top }))
        .filter(({ el, top }) => top < win.innerHeight && el.getBoundingClientRect().bottom > 0);
      const keys = messageKeys(messages), next = new Map();
      const added = keys.some(key => !rows.has(key));
      let cursor = list.firstElementChild;
      messages.forEach((message, index) => {
        const key = keys[index];
        const row = rows.get(key) ?? doc.createElement('li');
        renderRow(row, message);
        next.set(key, row);
        if (row !== cursor) list.insertBefore(row, cursor);
        cursor = row.nextElementSibling;
      });
      for (const [key, row] of rows) if (!next.has(key)) row.remove();
      rows = next;
      // Status and open context preview can also change height above the anchor.
      afterRender();
      if (hadRows && followEdge && added && !doc.activeElement?.matches('input, textarea, summary, select')) follow();
      else {
        const anchor = anchors.find(({ el }) => el.isConnected);
        if (anchor) win.scrollBy(0, anchor.el.getBoundingClientRect().top - anchor.top);
        if (hadRows && added && !followEdge) activity.hidden = false;
      }
    },
    clear() { rows.clear(); list.replaceChildren(); activity.hidden = true; },
    dispose() { activity.removeEventListener('click', follow); win.removeEventListener('scroll', onScroll); },
  };
}
