// Mock data for the local dev harness (web/dev/host.html). Not shipped in the
// built app. Reuses the real fixture helpers so discovery accepts the payloads
// exactly as the production host would.
import { channelFixture, shareFixture } from '../connection-fixtures.js';

export const own = 'me';

const iso = (daysAgo, hour = 12) => {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  d.setHours(hour, 0, 0, 0);
  return d.toISOString();
};

let seq = 0;
const message = (sender, body, at, kind = 'message', topic) => ({ id: `rec-${++seq}`, recorded_at: at, sender, kind, body, ...(topic ? { topic } : {}) });

// One Agent Contact: an owned outgoing channel shared to the peer, plus the
// peer's incoming channel shared to us, each carrying some messages.
function contact({ peerId, name, outId, inId, sender = name, topic, outgoing = [], incoming = [] }) {
  const outbox = channelFixture({ id: `Event/${outId}`, name: `${name} (outbox)`, description: `[mesh_identifier: "${name}"]` });
  const inbox = channelFixture({ id: `Event/${inId}`, name: `${name} (inbox)`, fulcra_userid: peerId, description: `[mesh_identifier: "${name}"]` });
  return {
    catalog: [outbox, inbox],
    outgoing: [shareFixture({ data_types: [outbox.id], with_user_ids: [peerId], share_all_data: false })],
    incoming: [{
      datashare_name: 'connect-agents-with-anyone: synthetic', grant_type: 'user',
      sharing_fulcra_userid: peerId, sharing_fulcra_user_name: name, data_types: [inbox.id],
    }],
    rows: {
      [`${own}/${outbox.id}`]: outgoing.map(m => message('You', m.body, m.at, m.kind, m.topic ?? topic)),
      [`${peerId}/${inbox.id}`]: incoming.map(m => message(sender, m.body, m.at, m.kind, m.topic ?? topic)),
    },
  };
}

const contacts = [
  // Contact whose agent sends under a different name (person "Gregory Klein",
  // agent "Schreber") — the header avatar vs message-sender case.
  contact({
    peerId: '00000000-0000-0000-0000-000000000001', name: 'Gregory Klein', sender: 'Schreber', topic: 'Q3 numbers', outId: 'g-out', inId: 'g-in',
    outgoing: [{ body: 'Can your agent confirm the Q3 numbers before Friday?', at: iso(2, 10) }],
    incoming: [
      { body: 'On it — pulling the figures now.', at: iso(2, 11), kind: 'reply' },
      { body: 'Confirmed: revenue is up 12% QoQ. Want me to draft a one-paragraph summary?', at: iso(1, 15), kind: 'reply' },
    ],
  }),
  contact({
    peerId: '11111111-1111-1111-1111-111111111111', name: 'Alice', topic: 'Saturday hike', outId: 'a-out', inId: 'a-in',
    outgoing: [
      { body: 'Hey Alice — can your agent pull the latest trail conditions for Saturday?', at: iso(3, 9) },
      { body: 'Great, thanks! I’ll plan for an early start then.', at: iso(1, 8) },
    ],
    incoming: [
      { body: 'Checking now. Conditions look clear through the weekend, light wind Saturday morning.', at: iso(3, 10), kind: 'reply' },
      { body: 'One note: the north approach is still muddy after Thursday’s rain, but the south approach is dry.\n\nI’d recommend the south approach and a 7am start to beat the crowd — want me to put it on your calendar?', at: iso(2, 16), kind: 'reply' },
    ],
  }),
  contact({
    peerId: '22222222-2222-2222-2222-222222222222', name: 'Bob', outId: 'b-out', inId: 'b-in',
    outgoing: [{ body: 'Bob, did your agent get the shared budget file?', at: iso(5, 11) }],
    // Most recent activity of anyone — sorts to the top of the list even though
    // Bob's peer id is not first alphabetically, demonstrating recency ordering.
    incoming: [{ body: 'Yes, received. Reviewing the Q3 numbers and I’ll send notes tomorrow.', at: iso(0, 9), kind: 'reply' }],
  }),
  contact({
    peerId: '33333333-3333-3333-3333-333333333333', name: 'Carol', outId: 'c-out', inId: 'c-in',
    outgoing: [],
    incoming: [{ body: 'Ack — noted, no action needed on my side.', at: iso(10, 9), kind: 'ack' }],
  }),
];

// A pending outbox: an owned connection channel with no covering outgoing share
// yet, so it shows under "Pending" rather than as a contact.
const pending = channelFixture({ id: 'Event/pending-1', name: 'Dana (outbox)', description: '[mesh_identifier: "Dana"]' });

// A legacy mesh outbox (pre-"connect-agents-with-anyone"): a shared
// MomentAnnotation named "... mesh outbox", which shows under "Legacy
// connections" as a conversion candidate rather than as a Contact.
const legacyOutbox = { id: 'MomentAnnotation/legacy-erin', name: 'Erin mesh outbox', description: '[mesh_identifier: "Erin"]' };
const legacyPeer = '44444444-4444-4444-4444-444444444444';

export const scenario = {
  catalog: [...contacts.flatMap(c => c.catalog), pending, legacyOutbox],
  shares: {
    own_fulcra_userid: own,
    outgoing: [...contacts.flatMap(c => c.outgoing),
      shareFixture({ data_types: [legacyOutbox.id], with_user_ids: [legacyPeer], share_all_data: false })],
    incoming: contacts.flatMap(c => c.incoming),
  },
  rows: Object.assign({}, ...contacts.map(c => c.rows)),
};
