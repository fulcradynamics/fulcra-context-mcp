import { test as base, expect } from '@playwright/test';
import schema from '../tests/fixtures/connection-schema.json' with { type: 'json' };

// Shared synthetic backend for presentation regressions. Data payloads in these
// tests are concise: expand them into Event channels, their direct incoming
// grants, and Event messages before returning them on the MCP wire. Protocol
// authorization/conversion tests use explicit fixtures, not this adapter.
export const test = base.extend({
  page: async ({ page }, use) => {
    await page.evaluate(schema => {
      let entries = [];
      window.connectionResult = result => {
        const prefix = 'Available data types, grouped by compatible tool: ';
        for (const part of Array.isArray(result.content) ? result.content : []) {
          if (part.type !== 'text') continue;
          if (part.text.startsWith(prefix)) {
            const catalog = JSON.parse(part.text.slice(prefix.length));
            entries = Object.values(catalog).flat();
            for (const entry of entries) {
              if (!entry.id.startsWith('Event/')) continue;
              entry.description = 'connect-agents-with-anyone channel\n' + (entry.description ?? '');
              Object.assign(entry, structuredClone(schema));
            }
            part.text = prefix + JSON.stringify(catalog);
          } else if (part.text.startsWith('Shares: ')) {
            const shares = JSON.parse(part.text.slice(8));
            shares.outgoing = shares.outgoing.map(s => ({datashare_name:'connect-agents-with-anyone: synthetic',...s}));
            shares.incoming.push(...(window.entries ?? entries).filter(e => e.fulcra_userid && e.fulcra_userid !== shares.own_fulcra_userid).map(e => ({
              sharing_fulcra_userid:e.fulcra_userid,grant_type:'user',data_types:[e.id],datashare_name:'connect-agents-with-anyone: synthetic',
            })));
            part.text = 'Shares: ' + JSON.stringify(shares);
          } else if (part.text.startsWith('Records for ')) {
            const at = part.text.indexOf(': [');
            if (at < 0) continue;
            const rows = JSON.parse(part.text.slice(at + 2));
            part.text = part.text.slice(0, at + 2) + JSON.stringify(rows.map(({note, ...r}) => {
              if (note === undefined) return r;
              let body = note;
              try { const old = JSON.parse(note); if (old?.v === 1 && typeof old.body === 'string') body = old.body; } catch {}
              return {...r,sender:'Incoming',kind:'message',body};
            }));
          }
        }
        return result;
      };
    }, schema);
    await use(page);
  },
});
export { expect };
