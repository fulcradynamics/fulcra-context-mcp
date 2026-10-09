import { build } from 'esbuild';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const root = new URL('./', import.meta.url);
const result = await build({
  absWorkingDir: fileURLToPath(root),
  entryPoints: ['main.js'], bundle: true, write: false,
  format: 'iife', platform: 'browser', target: 'es2022', minify: true,
});
const template = await readFile(new URL('index.html', root), 'utf8');
const styles = await readFile(new URL('styles.css', root), 'utf8');
const font = await readFile(new URL('assets/rubik-latin-wght-normal.woff2', root));
const icon = await readFile(new URL('../fulcra_mcp/static/icon.png', root));
const license = await readFile(new URL('assets/OFL.txt', root), 'utf8');
const script = result.outputFiles[0].text.replaceAll('</script', '<\\/script');
await writeFile(new URL('../fulcra_mcp/ui/mesh.html', root),
  template
    .replace('/* APP_STYLES */', () => `/* Rubik license:\n${license} */\n` + styles.replace('./assets/rubik-latin-wght-normal.woff2', `data:font/woff2;base64,${font.toString('base64')}`))
    .replace('/* BRAND_ICON */', () => `data:image/png;base64,${icon.toString('base64')}`)
    .replace('/* APP_SCRIPT */', () => script));
