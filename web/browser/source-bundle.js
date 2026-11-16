import { build } from 'esbuild';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

// Exercise source changes without writing or replacing a released UI bundle.
export async function sourceBundle() {
  const root = new URL('../', import.meta.url);
  const result = await build({
    absWorkingDir: fileURLToPath(root), entryPoints: ['main.js'],
    bundle: true, write: false, format: 'iife', platform: 'browser', target: 'es2022',
  });
  const [template, styles, font, icon] = await Promise.all([
    readFile(new URL('index.html', root), 'utf8'),
    readFile(new URL('styles.css', root), 'utf8'),
    readFile(new URL('assets/rubik-latin-wght-normal.woff2', root)),
    readFile(new URL('../fulcra_mcp/static/icon.png', root)),
  ]);
  return template
    .replace('/* APP_STYLES */', () => styles.replace('./assets/rubik-latin-wght-normal.woff2', `data:font/woff2;base64,${font.toString('base64')}`))
    .replace('/* BRAND_ICON */', () => `data:image/png;base64,${icon.toString('base64')}`)
    .replace('/* APP_SCRIPT */', () => result.outputFiles[0].text.replaceAll('</script', '<\\/script'));
}
