// Lossless field spans; mirrors description_fields.py. Values are untrusted data.
const fields = {
  mesh_identifier: 'Contact label', agent_connection: 'Connection details',
  contact_status: 'Contact status', connection_setup_session: 'Setup conversation',
  standing_invitation_inviter: 'Invitation sender', converted_from_mesh: 'Converted from mesh',
};
const whitespace = c => c !== undefined && ' \t\r\n'.includes(c);

function decode(text, start) {
  let quoted = false, depth = 0;
  for (let i = start; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '\\') { i++; continue; }
      if (c === '"') { quoted = false; if (!depth) return [JSON.parse(text.slice(start, i + 1)), i + 1]; }
    } else if (c === '"') quoted = true;
    else if (c === '{' || c === '[') depth++;
    else if (c === '}' || c === ']') {
      if (--depth === 0) return [JSON.parse(text.slice(start, i + 1)), i + 1];
    } else if (!depth && (whitespace(c) || i === text.length - 1)) {
      const end = whitespace(c) ? i : i + 1;
      return [JSON.parse(text.slice(start, end)), end];
    }
  }
  throw new Error('Malformed JSON');
}

export function fieldSpan(text, key) {
  if (text == null) text = '';
  if (typeof text !== 'string') throw new Error('Description must be text');
  const found = [];
  for (let i = 0; i < text.length;) {
    let match;
    for (const [candidate, label] of Object.entries(fields)) {
      const bare = ['standing_invitation_inviter', 'converted_from_mesh'].includes(candidate);
      const legacy = (bare ? '' : '[') + candidate;
      if (text.startsWith(legacy, i) && (!bare || !i || whitespace(text[i - 1]))) {
        match = [candidate, legacy, !bare]; break;
      }
      if (text.startsWith(label + ':', i) && (!i || whitespace(text[i - 1]))) {
        match = [candidate, label, false]; break;
      }
    }
    if (match) {
      const [candidate, token, bracket] = match;
      try {
        let pos = i + token.length;
        if (text[pos++] !== ':' || !whitespace(text[pos])) throw new Error('Missing delimiter');
        while (whitespace(text[pos])) pos++;
        const [value, valueEnd] = decode(text, pos);
        let end = valueEnd;
        if (bracket && text[end++] !== ']') throw new Error('Missing bracket');
        if (!bracket && end < text.length && !whitespace(text[end])) throw new Error('Missing boundary');
        if (candidate === key) found.push([i, end, value]);
        i = end;
      } catch (error) {
        if (candidate === key) throw error;
        i += token.length;
      }
      continue;
    }
    if ('"{['.includes(text[i])) {
      try { [, i] = decode(text, i); continue; } catch { /* ordinary prose */ }
    }
    i++;
  }
  if (found.length > 1) throw new Error('Duplicate field');
  return found[0];
}

export function writeField(text, key, value) {
  text ??= '';
  const span = fieldSpan(text, key);
  let replacement = value == null ? '' : fields[key] + ': ' + JSON.stringify(value).replace(/ {2,}|[^\S ]/gu,
    run => [...run].map(c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0')).join(''));
  if (span && replacement) {
    if (span[0] && !whitespace(text[span[0] - 1])) replacement = '\n' + replacement;
    if (span[1] < text.length && !whitespace(text[span[1]])) replacement += '\n';
  }
  return span ? text.slice(0, span[0]) + replacement + text.slice(span[1])
    : text + (text && replacement ? '\n' : '') + replacement;
}
