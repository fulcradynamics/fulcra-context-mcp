import test from 'node:test';
import assert from 'node:assert/strict';
import { artifactReferences, fileManagerRequest } from './artifacts.js';
const owner = '00000000-0000-4000-8000-000000000001';
const other = '00000000-0000-4000-8000-000000000002';
test('artifact references retain exact paths, explicit owners and versions', () => {
  const refs = artifactReferences({artifacts:[{path:'/shared/a.txt'}, {path:'/shared/b.txt',owner:other,version:'hash-1'}]}, {fulcra_userid:owner});
  assert.deepEqual(refs, [{path:'/shared/a.txt',owner}, {path:'/shared/b.txt',owner:other,version:'hash-1'}]);
  const request = fileManagerRequest(refs[1]);
  assert.ok(request.includes('open_file_manager'));
  assert.ok(request.includes(JSON.stringify({path:'/shared/b.txt',fulcra_userid:other})));
  assert.ok(request.includes('hash-1'));
  assert.ok(request.includes('current file'));
});

test('empty and malformed references do not become actionable paths', () => {
  assert.deepEqual(artifactReferences({}, {fulcra_userid:owner}), []);
  for (const file of [{path:'https://example.com'}, {path:'/a/../b'}, {path:'/a',owner:'bad'}, {path:'/a',version:3}]) {
    assert.deepEqual(artifactReferences({artifacts:[file]}, {fulcra_userid:owner}), [null]);
  }
});
