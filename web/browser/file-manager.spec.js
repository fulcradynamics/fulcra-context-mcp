import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { peer } from './harness.js';
const source = await readFile(new URL('../../fulcra_mcp/file_manager_ui.py', import.meta.url), 'utf8');
const html = source.split('FILE_MANAGER_HTML = r"""')[1].split('"""')[0];

test('owned file manager uploads and refreshes a multi-content listing', async ({ page }) => {
  await page.setContent('<iframe sandbox="allow-scripts"></iframe>');
  await page.evaluate(html => {
    const frame = document.querySelector('iframe');
    let uploaded = false;
    const reply = (id, result) => frame.contentWindow.postMessage({jsonrpc:'2.0',id,result}, '*');
    addEventListener('message', ({data:r}) => {
      if (r.method === 'ui/initialize') reply(r.id, {hostCapabilities:{},hostContext:{}});
      if (r.method === 'ui/notifications/initialized') frame.contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-input',params:{arguments:{path:'/'}}}, '*');
      if (r.method !== 'tools/call') return;
      if (r.params.name === 'list_files') reply(r.id, {content:[
        {type:'text',text:'Files at /: ' + JSON.stringify({folders:[],files:uploaded ? [{name:'note.txt',path:'/',size:5}] : []})},
        {type:'text',text:'Supplementary host context.'},
      ]});
      if (r.params.name === 'start_file_upload') reply(r.id, {structuredContent:{upload_id:'test-upload',chunk_size:256 * 1024}});
      if (r.params.name === 'upload_file_chunk') {
        uploaded = r.params.arguments.data === btoa('hello');
        reply(r.id, {structuredContent:{received:5,done:true}});
      }
    });
    frame.srcdoc = html;
  }, html);
  const ui = page.frameLocator('iframe');
  await expect(ui.locator('#listing')).toContainText('This folder is empty.');
  await ui.locator('#picker').setInputFiles({name:'note.txt',mimeType:'text/plain',buffer:Buffer.from('hello')});
  await expect(ui.locator('#uploads')).toContainText('Uploaded');
  await expect(ui.getByRole('button', {name:'Download note.txt',exact:true})).toBeVisible();
  await expect(ui.locator('.error')).toHaveCount(0);
});

for (const [folder, name, directory] of [['/shared', 'report.txt', false], ['/shared', 'README', false], ['/shared/reports.v1', 'reports.v1', true]])
for (const resourceDownload of [false, true]) test(`shared file manager ${name}; directory=${directory}; resource=${resourceDownload}`, async ({ page }) => {
  const path = `${folder}/${name}`;
  const browsePath = directory ? folder : path;
  await page.setContent('<iframe sandbox="allow-scripts"></iframe>');
  await page.evaluate(({html, peer, resourceDownload, folder, name, browsePath}) => {
    const frame = document.querySelector('iframe'); window.calls = []; window.resources = [];
    const reply = (id, result) => frame.contentWindow.postMessage({jsonrpc:'2.0',id,result}, '*');
    addEventListener('message', ({data:r}) => {
      if (r.method === 'ui/initialize') reply(r.id, {hostCapabilities:resourceDownload ? {downloadFile:{},serverResources:{}} : {}, hostContext:{}});
      if (r.method === 'resources/read') {window.resources.push(r.params.uri); reply(r.id,{contents:[{text:'Synthetic file',mimeType:'text/plain'}]});}
      if (r.method === 'ui/download-file') reply(r.id,{});
      if (r.method === 'ui/notifications/initialized') frame.contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-input',params:{arguments:{path:browsePath,fulcra_userid:peer}}}, '*');
      if (r.method === 'tools/call') {
        window.calls.push(r.params);
        reply(r.id, {content:[{type:'text',text:JSON.stringify(r.params.name === 'list_files' ? {folders:[],files:[{name,path:folder}]} : {url:'https://example.com/download'})}, {type:'text',text:'Supplementary host context.'}]});
      }
    }); frame.srcdoc = html;
  }, {html, peer, resourceDownload, folder, name, browsePath});
  const ui = page.frameLocator('iframe');
  await expect(ui.getByRole('button', {name:`Download ${name}`, exact:true})).toBeVisible();
  await expect(ui.locator('#drop')).toBeHidden();
  expect(await page.evaluate(() => window.resources)).toEqual([]);
  expect(await page.evaluate(() => window.calls)).toEqual([{name:'list_files',arguments:{path:browsePath,fulcra_userid:peer}}]);
  await ui.getByRole('button', {name:`Download ${name}`, exact:true}).click();
  if (resourceDownload) {
    await expect(ui.locator('#status')).toHaveText(`Downloaded ${name}.`);
    expect(await page.evaluate(() => window.resources)).toEqual([`fulcra://users/${peer}/files${path}`]);
    expect(await page.evaluate(() => window.calls)).toEqual([{name:'list_files',arguments:{path:browsePath,fulcra_userid:peer}}]);
    return;
  }
  await expect(ui.locator('#status a')).toHaveAttribute('href', 'https://example.com/download');
  await expect.poll(() => page.evaluate(() => window.calls.length)).toBe(2);
  expect(await page.evaluate(() => window.calls)).toEqual([
    {name:'list_files',arguments:{path:browsePath,fulcra_userid:peer}},
    {name:'read_file',arguments:{path,as_link:true,fulcra_userid:peer}},
  ]);
});
