import { test } from 'node:test';
import assert from 'node:assert/strict';
const { createRefreshScheduler } = await import('./refresh.js').catch(() => ({}));
const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
function clock() {
  let now = 0, id = 0;
  const tasks = new Map();
  return {
    setTimeout(fn, delay) { tasks.set(++id, { fn, at: now + delay }); return id; },
    clearTimeout(id) { tasks.delete(id); },
    async tick(ms) { now += ms; for (const [id, task] of [...tasks]) if (task.at <= now) { tasks.delete(id); task.fn(); } await flush(); },
    now: () => now,
    delays: () => [...tasks.values()].map(t => t.at - now),
  };
}
test('publishes actual deadline only after draining, clears it for retries, pause and disposal', async () => {
  const timer = clock(), states = [];
  let visible = true, settle;
  const scheduler = createRefreshScheduler({ ...timer, isVisible: () => visible,
    onState: state => states.push(state), refresh: () => new Promise(resolve => { settle = resolve; }) });
  scheduler.request();
  assert.deepEqual(states.at(-1), { running: true, paused: false, nextAt: null });
  await timer.tick(5000); settle(false); await flush();
  assert.deepEqual(states.at(-1), { running: false, paused: false, nextAt: 25000 });
  await timer.tick(19000);
  assert.equal(states.at(-1).nextAt, 25000);
  await timer.tick(1000);
  assert.deepEqual(states.at(-1), { running: true, paused: false, nextAt: null });
  visible = false; scheduler.visibilityChanged();
  assert.deepEqual(states.at(-1), { running: true, paused: true, nextAt: null });
  settle(false); await flush();
  assert.deepEqual(states.at(-1), { running: false, paused: true, nextAt: null });
  visible = true; scheduler.visibilityChanged(); settle(false); await flush();
  assert.equal(states.at(-1).nextAt, 105000);
  scheduler.request(); scheduler.request(); settle(false); await flush();
  assert.deepEqual(states.at(-1), { running: true, paused: false, nextAt: null });
  scheduler.dispose(); settle(false); await flush();
  assert.deepEqual(states.at(-1), { running: false, paused: true, nextAt: null });
  assert.deepEqual(timer.delays(), []);
});
test('one visible scheduler: immediate start, coalesced manual, no overlap, bounded backoff, resume and disposal', async () => {
  assert.equal(typeof createRefreshScheduler, 'function');
  const timer = clock(), busy = [];
  let visible = true, calls = 0, settle;
  const scheduler = createRefreshScheduler({
    ...timer, isVisible: () => visible, onBusy: value => busy.push(value),
    refresh: () => { calls++; return new Promise(resolve => { settle = resolve; }); },
  });
  scheduler.request(); await flush();
  assert.equal(calls, 1); assert.deepEqual(busy, [true]);
  scheduler.request(); scheduler.request(); await timer.tick(100000);
  assert.equal(calls, 1);
  settle(true); await flush(); assert.equal(calls, 2);
  settle(true); await flush(); assert.deepEqual(timer.delays(), [10000]);
  await timer.tick(9999); assert.equal(calls, 2);
  await timer.tick(1); assert.equal(calls, 3);
  for (const delay of [20000, 40000, 80000, 80000]) {
    settle(false); await flush(); assert.deepEqual(timer.delays(), [delay]);
    await timer.tick(delay);
  }
  settle(true); await flush(); assert.deepEqual(timer.delays(), [10000]);
  visible = false; scheduler.visibilityChanged(); await timer.tick(100000);
  const hiddenCalls = calls; scheduler.request(); await flush(); assert.equal(calls, hiddenCalls);
  visible = true; scheduler.visibilityChanged(); await flush(); assert.equal(calls, hiddenCalls + 1);
  visible = false; scheduler.visibilityChanged(); scheduler.request(); settle(true); await flush();
  assert.deepEqual(timer.delays(), []);
  visible = true; scheduler.visibilityChanged(); await flush();
  scheduler.dispose(); settle(true); await flush(); await timer.tick(100000); scheduler.request();
  assert.deepEqual(timer.delays(), []); assert.equal(busy.at(-1), false);
});
