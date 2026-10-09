import { test } from 'node:test';
import assert from 'node:assert/strict';
import { receiveEntrypoint } from './entrypoint.js';

for (const presentation of ['global', 'thread', 'threads']) {
  for (const startup of [undefined, 'resource', 'unknown']) {
    test(`direct startup requires both server markers: ${presentation}/${startup}`, () => {
      const app = { addEventListener() {} };
      const launch = receiveEntrypoint(app, { querySelector: selector => ({
        content: selector.includes('mesh-presentation') ? presentation : startup,
      }) });
      assert.equal(launch.directResource, presentation === 'threads' && startup === 'resource');
    });
  }
}

test('host handler is installed before connect and partial changes are buffered', () => {
  const listeners = new Map();
  const app = { addEventListener: (name, fn) => listeners.set(name, fn),
    removeEventListener: name => listeners.delete(name),
    getHostContext: () => ({ displayMode: 'inline', availableDisplayModes: ['inline', 'fullscreen'] }) };
  const launch = receiveEntrypoint(app, { querySelector: () => ({ content: 'threads' }) });
  assert.equal(typeof listeners.get('hostcontextchanged'), 'function');
  listeners.get('hostcontextchanged')({ displayMode: 'fullscreen' });
  const seen = [];
  const stop = launch.observeHost(context => seen.push(context));
  assert.deepEqual(seen, [{ displayMode: 'fullscreen', availableDisplayModes: ['inline', 'fullscreen'] }]);
  listeners.get('hostcontextchanged')({ theme: 'dark' });
  assert.deepEqual(seen[1], { theme: 'dark' });
  stop();
  assert.equal(listeners.size, 0);
});
