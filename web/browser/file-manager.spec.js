import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { peer } from './harness.js';
const source = await readFile(new URL('../../fulcra_mcp/file_manager_ui.py', import.meta.url), 'utf8');
const html = source.split('FILE_MANAGER_HTML = r"""')[1].split('"""')[0];

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
        reply(r.id, {content:[{type:'text',text:JSON.stringify(r.params.name === 'list_files' ? {folders:[],files:[{name,path:folder}]} : {url:'https://example.com/download'})}]});
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
  await expect.poll(() => page.evaluate(() => window.calls.length)).toBe(2);
  expect(await page.evaluate(() => window.calls)).toEqual([
    {name:'list_files',arguments:{path:browsePath,fulcra_userid:peer}},
    {name:'read_file',arguments:{path,as_link:true,fulcra_userid:peer}},
  ]);
});
