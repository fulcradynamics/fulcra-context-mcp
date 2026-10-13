import schema from '../tests/fixtures/connection-schema.json' with { type: 'json' };

// Synthetic Event fixtures for presentation tests; authorization tests supply
// their own explicit catalog and grants (connections.test.js).
export function channelFixture(entry) {
  return { ...entry, description: 'connect-agents-with-anyone channel\n' + (entry.description ?? ''),
    ...structuredClone(schema) };
}
export function shareFixture(share) {
  return { datashare_name:'connect-agents-with-anyone: synthetic', ...share };
}
export function incomingFixtures(catalog, own='me') {
  return catalog.filter(e => e.fulcra_userid && e.fulcra_userid !== own).map(e => ({
    datashare_name:'connect-agents-with-anyone: synthetic', grant_type:'user',
    sharing_fulcra_userid:e.fulcra_userid, data_types:[e.id],
  }));
}
