import test from 'node:test';
import assert from 'node:assert/strict';
import { parseContactIdentifier } from './contact-identifier.js';
import { channelMetadata } from './channel-metadata.js';
import { parseSetupSession } from './setup-session.js';
import { fieldSpan, writeField } from './description-fields.js';
import { parseStatus } from './contact-status.js';

test('named fields, folded catalog and inert nested marker strings', () => {
  const details = {version: 1, extra: {text: '[mesh_identifier: "Fake"] Contact label: fake', array: [{}]}};
  const text = `Connection details: ${JSON.stringify(details)} Contact label: "Real"`;
  assert.equal(parseContactIdentifier(text), 'Real');
  assert.deepEqual(channelMetadata(text), details);
  assert.equal(parseContactIdentifier('Contact label: "One" [mesh_identifier: "Two"]'), undefined);
  assert.equal(parseContactIdentifier('Contact label: "One"junk'), undefined);
});

test('setup allowlist remains strict with either spelling', () => {
  const url = 'codex://threads/11111111-1111-4111-8111-111111111111';
  assert.equal(parseSetupSession(`Setup conversation: "${url}"`), url);
  assert.equal(parseSetupSession(`Setup conversation: "${url}" [connection_setup_session: "${url}"]`), undefined);
  assert.equal(parseSetupSession('Setup conversation: "https://example.com"'), undefined);
});

for (const [key, label] of Object.entries({mesh_identifier: 'Contact label', agent_connection: 'Connection details',
  contact_status: 'Contact status', connection_setup_session: 'Setup conversation',
  standing_invitation_inviter: 'Invitation sender', converted_from_mesh: 'Converted from mesh'})) {
  test(`lossless dual-read/write and duplicate refusal: ${key}`, () => {
    const value = {nested: ['café "[]" Contact label: fake', {}]};
    const bare = ['standing_invitation_inviter', 'converted_from_mesh'].includes(key);
    const legacy = `${bare ? '' : '['}${key}: ${JSON.stringify(value)}${bare ? '' : ']'}`;
    const named = `${label}: ${JSON.stringify(value)}`;
    for (const field of [legacy, named]) {
      const text = `Notes  unchanged\n${field}\nUnknown: keep`;
      assert.deepEqual(fieldSpan(text, key)[2], value);
      assert.equal(writeField(text, key, value), `Notes  unchanged\n${named}\nUnknown: keep`);
      assert.equal(writeField(text, key, null), 'Notes  unchanged\n\nUnknown: keep');
      assert.deepEqual(fieldSpan(text.replace(/\s+/g, ' '), key)[2], value);
    }
    for (const text of [`${legacy} ${named}`, `${named} ${named}`, `${label}: bad`, `${label}: "x"junk`]) {
      assert.throws(() => writeField(text, key, value));
    }
  });
}

test('status and whitespace-safe label roundtrip', () => {
  const label = 'café  "[mesh_identifier: fake]"\u00a0test';
  assert.equal(parseContactIdentifier(writeField('', 'mesh_identifier', label).replace(/\s+/g, ' ')), label);
  const status = {attention: true, reason: 'Waiting [contact_status: fake]', assessed_at: '2026-10-13T12:00:00Z'};
  const text = writeField('Intro', 'contact_status', status);
  assert.deepEqual(parseStatus(text), status);
  assert.equal(parseStatus(text + ` [contact_status: ${JSON.stringify(status)}]`), null);
});

for (const [prefix, suffix] of [
  ['Notes  unchanged', ''], ['', 'More  notes'], ['Notes  unchanged', 'More  notes'],
  ['[mesh_identifier: "Old"]', '[connection_setup_session: "kept"]'],
  ['Notes\t', '\r\nMore  notes'],
]) {
  test(`legacy metadata replacement preserves both edges: ${JSON.stringify([prefix, suffix])}`, () => {
    const old = {version: 1, invitation: {state: 'prepared', code: '0123456789abcdef0123456789abcdef'}};
    const value = {...old, invitation: {...old.invitation, state: 'completed'}};
    const text = `${prefix}[agent_connection: ${JSON.stringify(old)}]${suffix}`;
    assert.deepEqual(channelMetadata(text), old);
    const updated = writeField(text, 'agent_connection', value);
    const left = prefix && !' \t\r\n'.includes(prefix.at(-1)) ? '\n' : '';
    const right = suffix && !' \t\r\n'.includes(suffix[0]) ? '\n' : '';
    assert.equal(updated, `${prefix}${left}Connection details: ${JSON.stringify(value)}${right}${suffix}`);
    assert.deepEqual(channelMetadata(updated), value);
    assert.deepEqual(channelMetadata(updated.replace(/\s+/g, ' ')), value);
    assert.equal(writeField(updated, 'agent_connection', value), updated);
    assert.equal(writeField(text, 'agent_connection', null), prefix + suffix);
    if (prefix.startsWith('[mesh_identifier:')) {
      assert.equal(parseContactIdentifier(updated), 'Old');
      assert.equal(fieldSpan(updated, 'connection_setup_session')[2], 'kept');
      const renamed = writeField(updated, 'mesh_identifier', 'New');
      assert.equal(parseContactIdentifier(renamed), 'New');
      assert.deepEqual(channelMetadata(renamed), value);
    }
  });
}

for (const [prefix, suffix] of [['Notes', ''], ['', 'More'], ['Notes', 'More'],
  ['[agent_connection: {"version":1}]', '[contact_status: {}]']]) {
  test(`legacy label replacement preserves both edges: ${JSON.stringify([prefix, suffix])}`, () => {
    const text = `${prefix}[mesh_identifier: "Old"]${suffix}`;
    assert.equal(fieldSpan(text, 'mesh_identifier')[2], 'Old');
    const updated = writeField(text, 'mesh_identifier', 'New');
    assert.equal(updated, `${prefix}${prefix ? '\n' : ''}Contact label: "New"${suffix ? '\n' : ''}${suffix}`);
    assert.equal(parseContactIdentifier(updated), 'New');
    if (prefix.startsWith('[agent_connection:')) {
      assert.deepEqual(channelMetadata(updated), {version: 1});
      assert.deepEqual(fieldSpan(updated, 'contact_status')[2], {});
    }
  });
}

test('adjacent legacy fields get parseable named boundaries on edit', () => {
  const text = 'Notes[agent_connection: {"version":1}]More';
  const updated = writeField(text, 'agent_connection', {version: 1});
  assert.equal(updated, 'Notes\nConnection details: {"version":1}\nMore');
  assert.deepEqual(channelMetadata(updated), {version: 1});
});
