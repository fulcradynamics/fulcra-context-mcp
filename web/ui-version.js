// The contacts UI version, read from the one place it is declared
// (CONTACTS_UI_VERSION in fulcra_mcp/apps.py), and the bundle built for it.
// Each version is its own file, so building a new version never replaces an
// earlier one: hosts that stored an earlier URI keep reading that file.
import { readFileSync } from 'node:fs';

const declared = readFileSync(new URL('../fulcra_mcp/apps.py', import.meta.url), 'utf8')
  .match(/^CONTACTS_UI_VERSION = (\d+)$/m);
if (!declared) throw new Error('CONTACTS_UI_VERSION = <number> not found in fulcra_mcp/apps.py');

const fileManager = readFileSync(new URL('../fulcra_mcp/file_manager_ui.py', import.meta.url), 'utf8')
  .match(/^FILE_MANAGER_VERSION = (\d+)$/m);
if (!fileManager) throw new Error('FILE_MANAGER_VERSION = <number> not found in fulcra_mcp/file_manager_ui.py');
// The file manager panel has no build step: its versioned file is the source.
export const FILE_MANAGER_URL = new URL(`../fulcra_mcp/ui/file-manager/v${fileManager[1]}.html`, import.meta.url);

export const UI_VERSION = Number(declared[1]);
export const BUNDLE_URL = new URL(`../fulcra_mcp/ui/contacts/v${UI_VERSION}.html`, import.meta.url);
