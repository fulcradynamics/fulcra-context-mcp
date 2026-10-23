import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../fulcra_mcp/file_manager_ui.py', import.meta.url), 'utf8');
const body = source.slice(source.indexOf('async function callTool('), source.indexOf('// --- browsing'));
const parse = result => new Function('request', `${body}; return callTool('list_files', {});`)(async () => result);
const listing = { folders: [], files: [{ name: 'report.txt', path: '/', size: 12 }] };
const text = value => ({ type: 'text', text: value });
const payload = text(`Files at /: ${JSON.stringify(listing)}`);

test('file manager parses the payload without joining supplementary content', async () => {
  assert.deepEqual(await parse({ content: [payload, text('Supplementary host context.')] }), listing);
});

test('file manager accepts structured, wrapped and text-only results', async () => {
  for (const result of [
    { structuredContent: listing, content: [text('Summary')] },
    { structuredContent: { result: payload.text }, content: [text('Summary')] },
    { content: [payload] },
    { content: [{ type: 'resource_link', uri: 'fulcra://files/report.txt', name: 'report.txt' }, payload] },
  ]) assert.deepEqual(await parse(result), listing);
});

test('file manager preserves tool errors and rejects malformed payloads', async () => {
  await assert.rejects(parse({ isError: true, content: [text('Denied'), text('Try again later')] }), /Denied\nTry again later/);
  await assert.rejects(parse({ content: [text('Files at /: {broken}'), text('{}')] }), SyntaxError);
  await assert.rejects(parse({ content: [text('Not shared')] }), /Not shared/);
});
