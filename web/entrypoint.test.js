import { test } from 'node:test';
import assert from 'node:assert/strict';
import { receiveEntrypoint } from './entrypoint.js';

for (const presentation of ['global', 'thread', 'threads']) {
  for (const startup of [undefined, 'resource', 'unknown']) {
    test(`direct startup requires both server markers: ${presentation}/${startup}`, () => {
      const app = { addEventListener() {} };
      const launch = receiveEntrypoint(app, { querySelector: selector => ({
        content: selector.includes('connection-presentation') ? presentation : startup,
      }) });
      assert.equal(launch.directResource, presentation === 'thread' && startup === 'resource');
    });
  }
}

test('initial result is buffered once and late results cannot revive teardown', () => {
  const app = {};
  const launch = receiveEntrypoint(app, { querySelector: () => ({ content: 'thread' }) });
  const first = { structuredContent: { presentation: 'thread', peer_fulcra_userid: 'exact' } };
  app.ontoolresult(first);
  const seen = [];
  launch.consume(result => seen.push(result));
  app.ontoolresult({ isError: true });
  assert.deepEqual(seen, [first]);
  launch.dispose();
  app.ontoolcancelled();
  assert.deepEqual(seen, [first]);
});
