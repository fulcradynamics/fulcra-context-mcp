// Dev server for the local UI harness: rebuilds the real app bundle on every
// change to web/, serves the harness that renders it with mock data, and
// live-reloads the browser. Run with `npm run dev`. Dev-only.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { watch } from 'node:fs';
import { spawn } from 'node:child_process';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';

const PORT = Number(process.env.PORT) || 5050;
// Dev-only: render the app on a dark gray (not its production black :root) so
// non-black-host contrast issues surface here. Hosts supply their own background.
const DEV_BG = '#2a2a2e';
const webDir = fileURLToPath(new URL('../', import.meta.url));
const appHtmlPath = fileURLToPath(new URL('../../fulcra_mcp/ui/contacts.html', import.meta.url));
const hostHtmlPath = fileURLToPath(new URL('./host.html', import.meta.url));
const hostEntry = fileURLToPath(new URL('./host.js', import.meta.url));

const clients = new Set();
const notifyReload = () => { for (const res of clients) res.write('data: reload\n\n'); };

const buildApp = () => new Promise((resolve, reject) => {
  spawn(process.execPath, ['build.mjs'], { cwd: webDir, stdio: 'inherit' })
    .on('exit', code => (code === 0 ? resolve() : reject(new Error('build.mjs failed'))));
});
const buildHost = async () => (await build({
  entryPoints: [hostEntry], bundle: true, write: false, format: 'esm', platform: 'browser', target: 'es2022',
})).outputFiles[0].text;

let hostBundle = '';
let building = false, queued = false;
async function rebuild(reason) {
  if (building) { queued = true; return; }
  building = true;
  try {
    await buildApp();
    hostBundle = await buildHost();
    console.log(`rebuilt (${reason})`);
    notifyReload();
  } catch (e) {
    console.error('rebuild failed:', e.message);
  } finally {
    building = false;
    if (queued) { queued = false; rebuild('coalesced'); }
  }
}

await rebuild('startup');

let timer;
watch(webDir, { recursive: true }, (_event, file) => {
  if (!file || file.includes('node_modules') || /dev[\/\\](serve|verify-mock)\.mjs$/.test(file)) return;
  if (!/\.(js|css|html|png|woff2|json)$/.test(file)) return;
  clearTimeout(timer);
  timer = setTimeout(() => rebuild(file), 150);
});

createServer(async (req, res) => {
  const url = req.url.split('?')[0];
  try {
    if (url === '/events') {
      res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache', connection: 'keep-alive' });
      res.write('retry: 1000\n\n');
      clients.add(res);
      req.on('close', () => clients.delete(res));
      return;
    }
    if (url === '/' || url === '/index.html') {
      res.writeHead(200, { 'content-type': 'text/html' });
      return res.end(await readFile(hostHtmlPath));
    }
    if (url === '/host.js') {
      res.writeHead(200, { 'content-type': 'text/javascript' });
      return res.end(hostBundle);
    }
    if (url === '/contacts.html') {
      const html = (await readFile(appHtmlPath, 'utf8'))
        .replace('</head>', `<style>:root{background:${DEV_BG} !important}</style></head>`);
      res.writeHead(200, { 'content-type': 'text/html' });
      return res.end(html);
    }
    res.writeHead(404);
    res.end('not found');
  } catch (e) {
    res.writeHead(500);
    res.end(String(e));
  }
}).listen(PORT, () => console.log(`\n  Dev harness → http://localhost:${PORT}\n`));
