import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { discoverThreads } from './connections-discovery.js';
import { channelFixture, shareFixture, incomingFixtures } from './connection-fixtures.js';

const cases = JSON.parse(readFileSync(new URL('../tests/fixtures/connection-discovery.json', import.meta.url)));
for (const fixture of cases) test(`mention discovery parity: ${fixture.name}`, async () => {
  const narrow = { data_types: ['Event/a'], with_user_ids: ['peer'], share_all_data: false };
  const outgoing = [...(fixture.outgoing ?? [narrow])];
  if (fixture.extra) outgoing.push({ ...narrow, ...fixture.extra });
  const calls = [];
  const catalog = fixture.catalog ?? [{id:'Event/a', name:'Connection'}];
  const { threads } = await discoverThreads({ async callServerTool({ name }) {
    calls.push(name);
    return { structuredContent: { result: name === 'get_data_catalog'
      ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({
        [fixture.group ?? 'data types usable with: get_records']: catalog.map(channelFixture),
      })
      : 'Shares: ' + JSON.stringify({ own_fulcra_userid: 'me', outgoing:outgoing.map(shareFixture), incoming: [...(fixture.incoming ?? []), ...incomingFixtures(catalog)] }),
    } };
  } });
  assert.deepEqual(threads.map(t => t.peer), fixture.expected);
  assert.deepEqual(calls, ['get_data_catalog', 'list_shares']);
});
