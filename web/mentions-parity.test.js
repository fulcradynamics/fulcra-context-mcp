import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { discoverThreads } from './meshes.js';

const cases = JSON.parse(readFileSync(new URL('../tests/fixtures/mesh-discovery.json', import.meta.url)));
for (const fixture of cases) test(`mention discovery parity: ${fixture.name}`, async () => {
  const narrow = { data_types: ['MomentAnnotation/a'], with_user_ids: ['peer'], share_all_data: false };
  const outgoing = [...(fixture.outgoing ?? [narrow])];
  if (fixture.extra) outgoing.push({ ...narrow, ...fixture.extra });
  const calls = [];
  const { threads } = await discoverThreads({ async callServerTool({ name }) {
    calls.push(name);
    return { structuredContent: { result: name === 'get_data_catalog'
      ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({
        [fixture.group ?? 'data types usable with: get_records']: fixture.catalog ?? [{ id: 'MomentAnnotation/a', name: 'Mesh Outbox' }],
      })
      : 'Shares: ' + JSON.stringify({ own_fulcra_userid: 'me', outgoing, incoming: fixture.incoming ?? [] }),
    } };
  } });
  assert.deepEqual(threads.map(t => t.peer), fixture.expected);
  assert.deepEqual(calls, ['get_data_catalog', 'list_shares']);
});
