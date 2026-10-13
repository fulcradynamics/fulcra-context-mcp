import test from 'node:test';
import assert from 'node:assert/strict';
import { discoverThreads } from './meshes.js';
import { messageAddressing, viewingAgent } from './addressing.js';
import schema from '../tests/fixtures/connection-schema.json' with { type: 'json' };

const own='00000000-0000-4000-8000-000000000001', peer='00000000-0000-4000-8000-000000000002', other='00000000-0000-4000-8000-000000000003';
const id='Event/00000000-0000-4000-8000-000000000004';
const entry={id,name:'Shared label',description:'connect-agents-with-anyone channel',...schema};
const share={share_all_data:false,datashare_name:'connect-agents-with-anyone: test',data_types:[id],with_user_ids:[peer]};
function app(outgoing) { return {callServerTool:async ({name})=>({content:[{type:'text',text: name==='get_data_catalog'
  ? 'Available data types, grouped by compatible tool: '+JSON.stringify({'data types usable with: get_records':[entry,{...entry,fulcra_userid:peer}]})
  : 'Shares: '+JSON.stringify({own_fulcra_userid:own,outgoing,incoming:[{grant_type:'user',sharing_fulcra_userid:peer,datashare_name:share.datashare_name,data_types:[id]}]})}]})}; }
test('exact owned roster is separate from unpaired incoming and changes identity on revocation',async()=>{
 const result=await discoverThreads(app([share,{...share,with_user_ids:[other]}]));
 const multi=result.threads.find(t=>t.participants?.length===3);
 assert.ok(multi);
 assert.deepEqual(multi.participants.map(p=>p.id),[own,peer,other]);
 assert.equal(multi.sources.length,2);
 assert.equal(multi.sources.find(s=>s.direction==='Incoming').association,'unverified');
 assert.ok(multi.sources.every(s=>s.direction==='Outgoing'||s.fulcra_userid===peer));
 assert.match(multi.warnings.join(' '),/cannot verify|not verified/i);
 assert.equal(result.threads.find(t=>t.peer===peer).sources.length,1);
 const revoked=await discoverThreads(app([share]));
 assert.ok(!revoked.threads.some(t=>t.peer===multi.peer));
});
test('single multi-user grant and separate grants have the same own scope',async()=>{
 const one=await discoverThreads(app([{...share,with_user_ids:[peer,other]}]));
 const several=await discoverThreads(app([share,{...share,with_user_ids:[other]}]));
 assert.deepEqual(one.threads,several.threads);
});
test('overlapping outgoing audiences do not merge by transitivity',async()=>{
 const extra='00000000-0000-4000-8000-000000000009';
 const second='Event/00000000-0000-4000-8000-000000000008';
 const base=app([{...share,with_user_ids:[peer,other]},{...share,data_types:[second],with_user_ids:[other,extra]}]);
 const wrapped={callServerTool:async call=>{
  const result=await base.callServerTool(call);
  if(call.name==='get_data_catalog'){
   const prefix='Available data types, grouped by compatible tool: ';
   const catalog=JSON.parse(result.content[0].text.slice(prefix.length));
   catalog['data types usable with: get_records'].push({...entry,id:second});
   result.content[0].text=prefix+JSON.stringify(catalog);
  }
  return result;
 }};
 const {threads}=await discoverThreads(wrapped);
 const multis=threads.filter(t=>t.participants);
 assert.equal(multis.length,2);
 assert.deepEqual(multis.map(t=>t.expectedPeerUserids),[[peer,other],[other,extra]]);
 assert.ok(multis.every(t=>t.sources.filter(s=>s.direction==='Outgoing').length===1));
});
test('agent addressing is exact-case, not human identity or privacy',()=>{
 assert.equal(messageAddressing({},'chatgpt'),'broadcast');
 assert.equal(messageAddressing({recipients:['other','all']},'chatgpt'),'broadcast');
 assert.equal(messageAddressing({recipients:['chatgpt']},'chatgpt'),'addressed');
 assert.equal(messageAddressing({recipients:['ChatGPT']},'chatgpt'),'other');
 assert.equal(messageAddressing({recipients:[own]},'chatgpt'),'other');
 assert.equal(messageAddressing({recipients:['all']},'all'),'broadcast');
 assert.equal(viewingAgent([{direction:'Incoming',record:{sender:'impostor'}}]),'chatgpt');
 assert.equal(viewingAgent([{direction:'Outgoing',record:{sender:'Exact'}}]),'Exact');
 assert.equal(viewingAgent([{direction:'Outgoing',record:{sender:'A'}},{direction:'Outgoing',record:{sender:'B'}}]),'chatgpt');
 assert.equal(viewingAgent([],'<untrusted>'),'<untrusted>');
});
