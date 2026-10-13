import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: '.', testMatch: '*.spec.js', workers: 2, timeout: 20000,
  outputDir: '../test-results', reporter: 'list',
  use: { headless: true, screenshot: 'off', trace: 'off', video: 'off' },
});
