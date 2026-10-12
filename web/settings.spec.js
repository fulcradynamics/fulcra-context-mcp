import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

const html = await readFile(new URL('../fulcra_mcp/ui/mesh-settings.html', import.meta.url), 'utf8').catch(() => '');
const status = { status: 'checked', label: '2026-10-12T15:00:00Z', last_checked: '2026-10-12T15:00:00Z',
  configuration_id: 'a', account_id: 'me', task_id: 'task-a', state_path: '/agent/chatgpt/mesh-checks/a.md' };

async function open(page, { capabilities = { message: { text: {} }, experimental: { 'openai/message': {} } }, platform = 'desktop', outcome = 'accepted', data = status } = {}) {
  await page.setContent('<iframe title="Settings" sandbox="allow-scripts"></iframe>');
  await page.evaluate(({ html, capabilities, platform, outcome, data }) => {
    window.requests = [];
    const frame = document.querySelector('iframe');
    window.addEventListener('message', event => {
      if (event.source !== frame.contentWindow) return;
      const message = event.data;
      window.requests.push(message);
      let result;
      if (message.method === 'ui/initialize') {
        result = { protocolVersion: '2026-01-26', hostInfo: { name: 'test', version: '1' },
          hostCapabilities: capabilities, hostContext: platform ? { platform } : {} };
      } else if (message.method === 'tools/call') {
        result = { content: [], structuredContent: data };
      } else if (message.method === 'ui/message') {
        if (outcome === 'uncertain') return;
        result = outcome === 'rejected' ? { isError: true } : {};
      } else return;
      event.source.postMessage({ jsonrpc: '2.0', id: message.id, result }, '*');
    });
    frame.srcdoc = html;
  }, { html, capabilities, platform, outcome, data });
  return page.frameLocator('iframe');
}

test('read-only status on open; one explicit new-chat handoff with references only', async ({ page }) => {
  const ui = await open(page);
  await expect(ui.getByText('Last mesh check', { exact: true })).toBeVisible();
  await expect(ui.locator('#last-check')).toHaveText(status.label);
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'ui/message'))).toHaveLength(0);
  const button = ui.getByRole('button', { name: 'Reschedule checks in Chat', exact: true });
  await expect(ui.locator('#handoff-help')).toContainText('new conversation');
  await button.click();
  await expect(button).toBeDisabled();
  const requests = await page.evaluate(() => window.requests);
  const messages = requests.filter(r => r.method === 'ui/message');
  expect(messages).toHaveLength(1);
  expect(messages[0].params._meta['openai/message']).toEqual({ target: 'new', send: true });
  expect(messages[0].params.content[0].text).toContain('fulcra-mesh-setup');
  expect(messages[0].params.content[0].text).toContain('task-a');
  expect(messages[0].params.content[0].text).toContain('rather than creating another');
  expect(requests.filter(r => r.method === 'tools/call').map(r => r.params.name)).toEqual(['aicq_check_status']);
  await expect(ui.locator('#handoff-status')).toContainText('not yet changed');
});

for (const options of [
  { platform: 'mobile' },
  { platform: null },
  { capabilities: { message: { text: {} } } },
]) {
  test(`active-chat fallback is disclosed: ${JSON.stringify(options)}`, async ({ page }) => {
    const ui = await open(page, options);
    await expect(ui.locator('#handoff-help')).toContainText('active conversation');
    await ui.locator('#reschedule').click();
    const [message] = await page.evaluate(() => window.requests.filter(r => r.method === 'ui/message'));
    expect(message.params._meta?.['openai/message']?.target || 'active').toBe('active');
  });
}

test('unsupported host exposes a copyable prompt and never sends', async ({ page }) => {
  const ui = await open(page, { capabilities: {} });
  await expect(ui.locator('#reschedule')).toBeDisabled();
  await expect(ui.locator('#prompt')).toBeVisible();
  await expect(ui.locator('#prompt')).toHaveValue(/task-a/);
  expect(await page.evaluate(() => window.requests.filter(r => r.method === 'ui/message'))).toHaveLength(0);
});

for (const outcome of ['rejected', 'uncertain']) {
  test(`${outcome} send stays locked and never automatically retries`, async ({ page }) => {
    const ui = await open(page, { outcome });
    await ui.locator('#reschedule').click();
    await expect(ui.locator('#reschedule')).toBeDisabled();
    await expect(ui.locator('#handoff-status')).toContainText(outcome, { timeout: 20000 });
    await ui.locator('#refresh').click();
    await expect(ui.locator('#last-check')).toHaveText(status.label);
    await expect(ui.locator('#reschedule')).toBeDisabled();
    expect(await page.evaluate(() => window.requests.filter(r => r.method === 'ui/message'))).toHaveLength(1);
  });
}

for (const data of [{ status: 'not_set_up', label: 'Not set up' },
  { status: 'unavailable', label: 'Status unavailable' },
  { status: 'choose_configuration', label: 'Choose a configuration', configurations: ['a', 'b'] }]) {
  test(`status ${data.status} does not imply a schedule`, async ({ page }) => {
    const ui = await open(page, { data });
    await expect(ui.locator('#last-check')).toHaveText(data.label);
    await expect(ui.locator('#reschedule')).toBeDisabled();
    await expect(ui.locator('#fallback')).toBeHidden();
    if (data.configurations) {
      await ui.locator('#configuration').selectOption('b');
      await expect.poll(() => page.evaluate(() => window.requests.filter(r => r.method === 'tools/call').length)).toBe(2);
      const requests = await page.evaluate(() => window.requests.filter(r => r.method === 'tools/call'));
      expect(requests[1].params.arguments).toEqual({ configuration_id: 'b' });
    }
    expect(await page.evaluate(() => window.requests.filter(r => r.method === 'ui/message'))).toHaveLength(0);
  });
}

for (const width of [375, 1120]) {
  test(`settings layout at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 850 });
    const ui = await open(page);
    await page.locator('iframe').evaluate(frame => { frame.style.cssText = 'width:100%;height:800px;border:0'; });
    await page.evaluate(() => { document.body.style.margin = '0'; });
    await expect(ui.locator('#reschedule')).toBeEnabled();
    expect(await ui.locator('body').evaluate(el => el.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: process.env.TMPDIR
      ? `${process.env.TMPDIR}/mesh-settings-${width}.png` : testInfo.outputPath(`mesh-settings-${width}.png`) });
  });
}
