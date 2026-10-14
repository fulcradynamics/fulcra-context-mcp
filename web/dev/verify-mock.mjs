import { scenario, own } from './mock-data.js';
import { discoverThreads } from '../connections-discovery.js';
import { threadTitle } from '../contact-identifier.js';

const text = t => ({ content: [{ type: 'text', text: t }] });
const app = {
  callServerTool: async ({ name, arguments: args }) => {
    if (name === 'get_data_catalog') {
      let cat = scenario.catalog;
      if (args.data_type) cat = cat.filter(e => e.id === args.data_type && (e.fulcra_userid || own) === (args.fulcra_userid || own));
      return text('Available data types, grouped by compatible tool: ' + JSON.stringify({ 'data types usable with: get_records': cat }));
    }
    if (name === 'list_shares') return text('Shares: ' + JSON.stringify(scenario.shares));
    if (name === 'get_records') {
      const rows = scenario.rows[`${args.fulcra_userid ?? own}/${args.data_type}`] ?? [];
      return text(`Records for ${args.data_type} from a to b: ${JSON.stringify(rows)}`);
    }
    return text('');
  },
};
const d = await discoverThreads(app);
console.log('contacts:', d.threads.map(t => `${threadTitle(t)} [${t.sources.length} ch]`));
console.log('pending:', d.pending.length, 'legacy:', d.legacy.length, 'warnings:', d.warnings);
