import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readCheckStatus, startPrompt } from './check-status.js';

const host = statuses => ({
  calls: [],
  async callServerTool({ name, arguments: args }) {
    this.calls.push([name, args]);
    return { structuredContent: statuses[args.configuration_id ?? ''] };
  },
});

test('the setup prompt uses the set-up-agent-contacts skill', () => {
  assert.match(startPrompt, /set-up-agent-contacts/);
});

test('a single not_set_up configuration is reported as such', async () => {
  assert.equal((await readCheckStatus(host({ '': { status: 'not_set_up' } }))).status, 'not_set_up');
});

test('multiple configurations report the most recent check', async () => {
  const app = host({
    '': { status: 'choose_configuration', configurations: ['a', 'b', 'c'] },
    a: { status: 'checked', last_checked: '2026-10-18T12:00:00Z' },
    b: { status: 'checked', last_checked: '2026-10-19T12:00:00Z' },
    c: { status: 'never_checked' },
  });
  assert.equal((await readCheckStatus(app)).last_checked, '2026-10-19T12:00:00Z');
  assert.deepEqual(app.calls.map(([name]) => name), Array(4).fill('get_message_check_status'));
  const unread = host({ '': { status: 'choose_configuration', configurations: ['a', 'b'] },
    a: { status: 'checked', last_checked: '2026-10-18T12:00:00Z' }, b: { status: 'unavailable' } });
  assert.equal((await readCheckStatus(unread)).status, 'unavailable');
});
