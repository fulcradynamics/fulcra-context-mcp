import test from 'node:test';
import assert from 'node:assert/strict';
import { createDebugPreview, previewAssessment, previewMessages } from './debug-preview.js';

test('contact previews are instance-local and reset against the latest live assessment', () => {
  const preview = createDebugPreview();
  const live = Object.freeze({ attention: false, reason: 'Live', partial: false });
  preview.set('alice', 'status', 'attention');
  preview.set('alice', 'reason', '<Preview>');
  assert.deepEqual(previewAssessment(live, preview.get('alice')), { attention: true, reason: '<Preview>', partial: false });
  assert.equal(previewAssessment(live, preview.get('bob')), live);
  assert.deepEqual(createDebugPreview().get('alice'), {});
  assert.equal(live.reason, 'Live');
  preview.reset('alice');
  const latest = { ...live, reason: 'Updated by polling' };
  assert.equal(previewAssessment(latest, preview.get('alice')), latest);
});

for (const live of [
  { attention: null, partial: false, reason: null },
  { attention: null, partial: true, reason: null },
  { attention: true, partial: true, reason: 'Live reason' },
]) {
  test(`reason-only preview preserves live attention=${live.attention} and partial=${live.partial}`, () => {
    const assessment = Object.freeze({ ...live, assessed_at: '2026-01-01T00:00:00Z' });
    assert.deepEqual(previewAssessment(assessment, { reason: 'Preview reason' }),
      { ...assessment, reason: 'Preview reason' });
  });
}

for (const [status, attention, partial] of [
  ['attention', true, false], ['clear', false, false], ['partial', false, true],
]) {
  test(`explicit ${status} preview overrides live status`, () => {
    assert.deepEqual(previewAssessment({ attention: null, partial: true }, { status, reason: 'Preview reason' }),
      { attention, partial, reason: 'Preview reason' });
  });
}
test('explicit unknown preview is unassessed', () => {
  assert.deepEqual(previewAssessment({ attention: true, partial: true }, { status: 'unknown' }),
    { attention: null, reason: null });
});

test('message projections cannot mutate live records, and individual fields return to live', () => {
  const message = Object.freeze({ direction: 'Outgoing', record: Object.freeze({ body: 'Live' }), state: 'posted' });
  const live = Object.freeze([message]);
  const preview = createDebugPreview();
  preview.set('alice', 'body', 'Preview');
  preview.set('alice', 'delivery', 'uncertain');
  assert.equal(previewMessages(live, preview.get('alice'))[0].record.body, 'Preview');
  assert.equal(message.record.body, 'Live');
  assert.equal(message.state, 'posted');
  preview.set('alice', 'body', '');
  assert.equal(previewMessages(live, preview.get('alice'))[0].record.body, 'Live');
  assert.equal(previewMessages(live, preview.get('alice'))[0].state, 'uncertain');
  preview.reset('alice');
  assert.equal(previewMessages(live, preview.get('alice')), live);
});
