import { test, expect } from '@playwright/test';
import { open, peer, other } from './harness.js';
const handoff = ui => ui.getByRole('button', {name:'Discuss in synthetic',exact:true});
async function deselect(page, ui) {
 await ui.locator('#advanced-toggle').click();
 await ui.locator('.incoming-sources summary').click();
 // Earlier selected-contact snapshots are replaced, not erased from host logs.
 await page.evaluate(() => { window.contexts = []; });
 await ui.locator('.incoming-sources input').first().uncheck();
}
async function safeHandoff(page, ui) {
 await handoff(ui).click();
 await expect.poll(() => page.evaluate(() => window.hostMessages.length)).toBeGreaterThan(0);
 const attached = await page.evaluate(() => window.contexts.filter(c => c.content?.length));
 expect(attached.length).toBeGreaterThan(0);
 for (const context of attached) {
  const text = JSON.stringify(context);
  for (const suffix of ['-1','-2','-3']) expect(text).not.toContain(peer + suffix);
  expect(text).toContain(other + '-1');
  const snapshotText = context.content[0].text;
  const snapshot = JSON.parse(snapshotText.slice(snapshotText.indexOf('\n') + 1));
  expect(snapshot.selected_sources.some(source => source.fulcra_userid === peer)).toBe(false);
 }
 const sent = JSON.stringify(await page.evaluate(() => window.hostMessages));
 for (const suffix of ['-1','-2','-3']) expect(sent).not.toContain(peer + suffix);
}

test('unchecked incoming records cannot be attached during delayed discovery', async ({page}) => {
 const ui = await open(page);
 await page.evaluate(() => { window.holdDiscovery = true; });
 await deselect(page, ui);
 // Safety assertion replacing the disclosure probe; no successful refresh first.
 await safeHandoff(page, ui);
 await expect(ui.locator('#messages .message-row')).toHaveCount(3);
 await page.evaluate(() => { window.holdDiscovery=false; window.releaseDiscovery(); });
 await page.clock.runFor(11000);
 await expect(ui.locator('#messages .message-row')).toHaveCount(3);
 await expect(ui.locator('.incoming-sources input').first()).not.toBeChecked();
});

test('deselection clears attached context and retains safe context on discovery failure', async ({page}) => {
 const ui = await open(page);
 await handoff(ui).click();
 await expect.poll(() => page.evaluate(() => window.hostMessages.length)).toBe(1);
 await ui.getByRole('button', {name:'OK',exact:true}).click();
 await ui.locator('#thread-composer textarea:not([readonly])').fill('Retained draft');
 await page.evaluate(() => { window.contexts=[]; window.hostMessages=[]; window.failDiscovery=true; });
 await deselect(page, ui);
 await expect.poll(() => page.evaluate(() => window.contexts.some(c => c.content?.length === 0))).toBe(true);
 await expect(ui.locator('#message-status')).toContainText('Could not load messages');
 await expect(ui.locator('#thread-composer textarea:not([readonly])')).toHaveValue('Retained draft');
 await expect(ui.locator('#messages .message-row')).toHaveCount(3);
 await safeHandoff(page, ui);
 expect(JSON.stringify(await page.evaluate(() => window.contexts))).toContain('Stale');
});

test('old in-flight reads cannot restore unchecked rows or invalidate the composer', async ({page}) => {
 const ui = await open(page);
 await page.evaluate(() => { window.holdReads=true; });
 await page.clock.runFor(11000);
 await expect.poll(() => page.evaluate(() => window.heldReads.length)).toBeGreaterThan(0);
 await page.evaluate(() => { window.holdDiscovery=true; });
 await deselect(page, ui);
 await page.evaluate(() => { window.holdReads=false; window.releaseReads(); });
 // The queued refresh begins only once the old read has finished.
 await expect.poll(() => page.evaluate(() => window.heldDiscovery.length)).toBeGreaterThan(0);
 await expect(ui.locator('#messages .message-row')).toHaveCount(3);
 await expect(ui.locator('.incoming-sources input').first()).not.toBeChecked();
 await safeHandoff(page, ui);
});
