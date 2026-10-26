// Optional recorded decisions; live grants and schema still govern access.
export function channelMetadata(description) {
  if (typeof description !== 'string' || description.split('[agent_connection: ').length !== 2) return {};
  try {
    const start = description.indexOf('[agent_connection: ') + '[agent_connection: '.length;
    let value;
    // Try closing brackets until the complete JSON object ends, not a nested
    // peers array or a bracket inside an unrelated label.
    for (let end = description.indexOf(']', start); end !== -1; end = description.indexOf(']', end + 1)) {
      try { value = JSON.parse(description.slice(start, end)); break; } catch { /* nested bracket */ }
    }
    const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
    if (value?.version !== 1 || (value.peers !== undefined && (!Array.isArray(value.peers)
      || !value.peers.every(p => new RegExp('^' + uuid + '$').test(p?.fulcra_userid)
        && new RegExp('^Event/' + uuid + '$').test(p?.data_type))))) return {};
    return value;
  } catch { return {}; }
}

export const isInvitationTemplate = entry => entry.name === 'connect-our-agents-standing-invitation'
  || channelMetadata(entry.description).invitation?.prefix === 'open_invitation';
