// Mirrors fulcra_mcp/contact_identifier.py. Display only, never an identity.
import { fieldSpan } from './description-fields.js';
export function parseContactIdentifier(description) {
  try {
    const span = fieldSpan(description, 'mesh_identifier');
    const value = span?.[2];
    if (span && description.startsWith('[mesh_identifier', span[0])) {
      const tail = description.slice(span[1]).replace(/^[ \t\r\n]+|[ \t\r\n]+$/g, '');
      if (tail && !/^(Contact label|Connection details|Contact status|Setup conversation|Invitation sender|Converted from mesh):/.test(tail)) return undefined;
    }
    if (typeof value !== 'string' || !value || [...value].length > 80 || value !== value.trim()
      || /[\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/u.test(value)) return undefined;
    return value;
  } catch { return undefined; }
}

export function threadTitle(thread) {
  if (thread.participants) return `${thread.identifier || 'Multiparty connection'} — `
    + thread.participants.map(p => p.name === p.id ? p.id : `${p.name} (${p.id})`).join(', ');
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
