import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {discoverThreads} from './connections-discovery.js';
const schema=JSON.parse(readFileSync(new URL('../tests/fixtures/connection-schema.json',import.meta.url)));
const own='00000000-0000-4000-8000-000000000001', peer='00000000-0000-4000-8000-000000000002', other='00000000-0000-4000-8000-000000000005';
const id='Event/00000000-0000-4000-8000-000000000003', old='MomentAnnotation/00000000-0000-4000-8000-000000000004';
const legacy={id:old,name:'Mesh Outbox old'};
const entry={id,name:'Connection',fulcra_userid:peer,description:'connect-agents-with-anyone channel',...schema};
test('catalog omitted names do not break connection discovery', async()=>{
  const candidate={...entry}; delete candidate.name;
  const result=await discover([{id:'StepCount'},candidate],[],[incoming(peer,id)]);
  assert.deepEqual(result.threads.map(t=>t.peer),[peer]);
  assert.equal(result.threads[0].sources[0].name,id);
});
const incoming=(owner,type)=>({sharing_fulcra_userid:owner,grant_type:'user',datashare_name:'connect-agents-with-anyone: test',file_paths:[],file_history_paths:[],data_types:[type]});
const outgoing=(selector,p=peer)=>({share_all_data:false,file_paths:[],file_history_paths:[],data_types:[selector],with_user_ids:[p],datashare_name:'connect-agents-with-anyone: test'});
function discover(entries, out=[], inc=[]) {
  return discoverThreads({callServerTool:async({name})=>({content:[{type:'text',text:name==='get_data_catalog'
    ?'Available data types, grouped by compatible tool: '+JSON.stringify({'data types usable with: get_records':entries})
    :'Shares: '+JSON.stringify({own_fulcra_userid:own,outgoing:out,incoming:inc})}]})});
}
for(const selector of [old,'MomentAnnotation','MomentAnnotation/*','*']) test(`legacy outgoing selector must be exact: ${selector}`,async()=>{
  assert.equal((await discover([legacy],[outgoing(selector)])).legacy.length,selector===old?1:0);
});
test('all covering legacy grants remain checked',async()=>{
  assert.equal((await discover([legacy],[outgoing(old),outgoing('*')])).legacy.length,0);
});
for(const mode of ['absent','wrong-owner','wrong-peer','group','valid']) test(`conversion claims require exact legacy relationship: ${mode}`,async()=>{
  const refs=[{id:old,fulcra_userid:own}];
  const channel={...entry,description:entry.description+'\nconverted_from_mesh: '+JSON.stringify(refs)};
  const entries=[channel,...(mode==='absent'?[]:[{...legacy,...(mode==='wrong-owner'?{fulcra_userid:other}:{})}])];
  const grant=outgoing(old,mode==='wrong-peer'?other:peer);
  if(mode==='group') grant.with_group_ids=['group'];
  const result=await discover(entries,[grant],[incoming(peer,id)]);
  assert.deepEqual(result.threads[0].convertedFrom,mode==='valid'?refs:[]);
  assert.deepEqual(result.threads[0].sources[0].convertedFrom??[],mode==='valid'?refs:[]);
});
for(const mode of ['types','required','kind','body_limit','sender_limit','recipients','valid']) test(`semantic connection schema: ${mode}`,async()=>{
  const candidate=structuredClone(entry);
  if(mode==='types') {candidate.fields={sender:'number',kind:'boolean',body:'object'};delete candidate.required_fields;}
  if(mode==='required') delete candidate.required_fields;
  if(mode==='kind') candidate.fields.kind.enum=['message','heartbeat'];
  if(mode==='body_limit') candidate.fields.body.maxLength=9999;
  if(mode==='sender_limit') candidate.fields.sender.minLength=0;
  if(mode==='recipients') candidate.fields.recipients.maxItems=99;
  assert.equal((await discover([candidate],[],[incoming(peer,id)])).threads.length,mode==='valid'?1:0);
});
