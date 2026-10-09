// Display metadata only; callers keep exact IDs for routing and stable keys.
export function renderIdentity(element, name, id, prefix = '', suffix = '') {
  if (!element.firstChild) {
    const doc = element.ownerDocument;
    const primary = doc.createElement('span');
    const secondary = doc.createElement('span'); secondary.className = 'identity-secondary';
    element.append(primary, secondary, doc.createTextNode(''));
  }
  const [primary, secondary, trailing] = element.childNodes;
  const text = prefix + (name || id);
  if (primary.textContent !== text) primary.textContent = text;
  const detail = name ? ` (${id})` : '';
  if (secondary.textContent !== detail) secondary.textContent = detail;
  secondary.hidden = !name;
  if (trailing.textContent !== suffix) trailing.textContent = suffix;
}
