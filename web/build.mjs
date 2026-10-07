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
const script = result.outputFiles[0].text.replaceAll('</script', '<\\/script');
await writeFile(new URL('../fulcra_mcp/ui/hello.html', root),
  template.replace('/* APP_SCRIPT */', () => script));
