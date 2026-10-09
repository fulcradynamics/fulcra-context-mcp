// Mirrors fulcra_mcp/mesh_identifier.py. Display only, never an identity.
// Suffix whitespace is exactly JSON whitespace, not JS trim()/Unicode \s.
const NON_SUFFIX_WHITESPACE = /[^ \t\r\n]/u;
export function parseMeshIdentifier(description) {
  if (typeof description !== 'string') return undefined;
  const token = '[mesh_identifier', prefix = `${token}: `;
  const start = description.indexOf(token);
  if (start < 0 || !description.startsWith(prefix, start)) return undefined;
  const valueStart = start + prefix.length;
  if (description[valueStart] !== '"') return undefined;
  let end = valueStart + 1;
  for (; end < description.length; end++) {
    if (description[end] === '\\') { end++; continue; }
    if (description[end] === '"') break;
  }
  if (description[end + 1] !== ']' || NON_SUFFIX_WHITESPACE.test(description.slice(end + 2))) return undefined;
  try {
    const value = JSON.parse(description.slice(valueStart, end + 1));
    if (!value || [...value].length > 80 || value !== value.trim()
      || /[\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/u.test(value)) return undefined;
    return value;
  } catch { return undefined; }
}

export function threadTitle(thread) {
  return thread.identifier ? `${thread.identifier} (${thread.peer})` : thread.peer;
}

export function threadIdentifier(sources) {
  // Prefer a valid own/outgoing label. Among equal directions use exact type
  // ID lexical order (not locale, catalog order, account name, or label).
  const candidates = sources.filter(s => s.identifier).sort((a, b) =>
    (a.direction === 'Outgoing' ? 0 : 1) - (b.direction === 'Outgoing' ? 0 : 1)
    || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  return candidates[0]?.identifier;
}
