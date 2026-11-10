// Optional recorded decisions; live grants and schema still govern access.
import { fieldSpan } from './description-fields.js';
export function channelMetadata(description) {
  try {
    const value = fieldSpan(description, 'agent_connection')?.[2];
    const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
    if (value?.version !== 1 || (value.peers !== undefined && (!Array.isArray(value.peers)
      || !value.peers.every(p => new RegExp('^' + uuid + '$').test(p?.fulcra_userid)
        && new RegExp('^Event/' + uuid + '$').test(p?.data_type))))) return {};
    return value;
  } catch { return {}; }
}

export const isInvitationTemplate = entry => entry.name === 'connect-our-agents-standing-invitation'
  || channelMetadata(entry.description).invitation?.prefix === 'open_invitation';
