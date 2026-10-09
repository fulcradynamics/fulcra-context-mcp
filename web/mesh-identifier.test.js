import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseMeshIdentifier } from './mesh-identifier.js';
import { readFileSync } from 'node:fs';

const boundaries = JSON.parse(readFileSync(new URL('../tests/fixtures/mesh-identifier-whitespace.json', import.meta.url)));
for (const { suffix, valid } of boundaries) {
  test(`explicit suffix whitespace ${JSON.stringify(suffix)}`, () => {
    for (const tail of [suffix, ` \t${suffix}\r\n`]) {
      assert.equal(parseMeshIdentifier(`[mesh_identifier: "Trip"]${tail}`), valid ? 'Trip' : undefined);
    }
  });
}

test('JSON marker parser handles quotes, brackets, escapes, Unicode and nested token text', () => {
  for (const label of ['Trip  ["Paris"] \\ café', '[mesh_identifier: "nested"]', '🦊'.repeat(80), 'a'.repeat(80)]) {
    const quoted = JSON.stringify(label).replaceAll(' ', '\\u0020');
    assert.equal(parseMeshIdentifier(`Prose\n  intact. [mesh_identifier: ${quoted}]`), label);
  }
});

test('malformed, multiple, non-suffix, control and untrimmed labels fall back', () => {
  for (const label of ['', ' ', ' x', 'x ', 'x\ny', 'x\ty', 'x\x00y', 'x\x7fy', 'x\u200ey', 'x\u2028y', 'x'.repeat(81)]) {
    assert.equal(parseMeshIdentifier(`[mesh_identifier: ${JSON.stringify(label)}]`), undefined);
  }
  for (const description of [undefined, {}, 'prose', '[mesh_identifier: bad]', '[mesh_identifier: 12]', '[mesh_identifier: "a"] trailing', '[mesh_identifier: "a"] [mesh_identifier: "b"]', '[mesh_identifier "bad"]', '[mesh_identifier: "unterminated]']) {
    assert.equal(parseMeshIdentifier(description), undefined);
  }
});
