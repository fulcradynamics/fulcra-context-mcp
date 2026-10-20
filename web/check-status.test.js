import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readCheckStatus, describeCheckStatus, startPrompt, checkPrompt } from './check-status.js';

const host = statuses => ({
  calls: [],
  async callServerTool({ name, arguments: args }) {
    this.calls.push([name, args]);
    return { structuredContent: statuses[args.configuration_id ?? ''] };
  },
});

test('no schedule offers Start Checking through the setup skill', () => {
  const view = describeCheckStatus({ status: 'not_set_up' });
  assert.equal(view.text, 'Your agent is not automatically checking for messages.');
  assert.equal(view.action, 'Start Checking');
  assert.equal(view.prompt, startPrompt);
  assert.match(startPrompt, /set-up-agent-contacts/);
});

test('a scheduled configuration shows the last check and offers Check Now', () => {
  const view = describeCheckStatus({ status: 'checked', last_checked: '2026-10-19T12:00:00Z' });
  assert.match(view.text, /^Your agent last checked for messages /);
  assert.equal(view.action, 'Check Now');
  assert.equal(view.prompt, checkPrompt);
  assert.match(checkPrompt, /check-messages/);
  assert.equal(describeCheckStatus({ status: 'never_checked' }).action, 'Check Now');
});

test('unknown status shows nothing rather than claiming no schedule', () => {
  assert.equal(describeCheckStatus({ status: 'unavailable' }), null);
});

test('multiple configurations report the most recent check', async () => {
  const app = host({
    '': { status: 'choose_configuration', configurations: ['a', 'b', 'c'] },
    a: { status: 'checked', last_checked: '2026-10-18T12:00:00Z' },
    b: { status: 'checked', last_checked: '2026-10-19T12:00:00Z' },
    c: { status: 'never_checked' },
  });
  assert.equal((await readCheckStatus(app)).last_checked, '2026-10-19T12:00:00Z');
  assert.deepEqual(app.calls.map(([name]) => name), Array(4).fill('fulcra_check_status'));
  const unread = host({ '': { status: 'choose_configuration', configurations: ['a', 'b'] },
    a: { status: 'checked', last_checked: '2026-10-18T12:00:00Z' }, b: { status: 'unavailable' } });
  assert.equal((await readCheckStatus(unread)).status, 'unavailable');
});
