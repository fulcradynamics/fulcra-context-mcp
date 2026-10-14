import { expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
const bundle = await readFile(new URL('../../fulcra_mcp/ui/contacts.html', import.meta.url), 'utf8');
const schema = JSON.parse(await readFile(new URL('../../tests/fixtures/connection-schema.json', import.meta.url), 'utf8'));
export const own='00000000-0000-4000-8000-000000000001', peer='00000000-0000-4000-8000-000000000002', other='00000000-0000-4000-8000-000000000003';
export const out='Event/00000000-0000-4000-8000-000000000004', incoming='Event/00000000-0000-4000-8000-000000000005';
export async function open(page, width=900, { listOnly = false, holdReads = false, acceptAck = false, ownRecords = [] } = {}) {
 await page.setViewportSize({width,height:1100});
 await page.clock.install({time:new Date('2026-10-13T12:00:00Z')});
 await page.clock.pauseAt(new Date('2026-10-13T12:00:01Z'));
 await page.setContent('<iframe style="border:0;width:100%;height:1800px" sandbox="allow-scripts"></iframe>');
 await page.evaluate(({bundle,schema,own,peer,other,out,incoming,holdReads,acceptAck,ownRecords})=>{
  window.holdReads = holdReads;
  window.ownRecords = ownRecords;
  const frame=document.querySelector('iframe');
  window.calls=[]; window.contexts=[]; window.hostMessages=[]; window.audience=[peer,other];
  window.heldDiscovery=[]; window.heldReads=[];
  const reply=(id,result)=>frame.contentWindow.postMessage({jsonrpc:'2.0',id,result},'*');
  window.releaseDiscovery=()=>window.heldDiscovery.splice(0).forEach(fn=>fn());
  window.releaseReads=()=>window.heldReads.splice(0).forEach(fn=>fn());
  addEventListener('message',({data:r,source})=>{
   if(source!==frame.contentWindow)return;
   if(r.method==='ui/initialize')reply(r.id,{protocolVersion:'2026-01-26',hostInfo:{name:'synthetic',version:'1'},hostContext:{displayMode:'fullscreen'},hostCapabilities:{message:{text:{}},updateModelContext:{text:{}}}});
   if(r.method==='ui/notifications/initialized')frame.contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-result',params:{structuredContent:{presentation:'global'}}},'*');
   if(r.method==='ui/update-model-context'){window.contexts.push(r.params);reply(r.id,{});}
   if(r.method==='ui/message'){window.hostMessages.push(r.params);reply(r.id,{});}
   if(r.method!=='tools/call')return;
   window.calls.push(r.params); const {name,arguments:a}=r.params;
   const discovery=['get_data_catalog','list_shares'].includes(name);
   if(discovery && window.failDiscovery){reply(r.id,{isError:true,content:[{type:'text',text:'Synthetic discovery failure'}]});return;}
   if(name==='agent_connection_send'){
    if(acceptAck && a.kind === 'ack') {
     window.ownRecords.push({id:a.mid,kind:a.kind,body:a.body,sender:a.sender,in_reply_to:a.in_reply_to,start_time:'2026-10-13T12:00:00Z'});
     reply(r.id,{structuredContent:{status:'posted',mid:a.mid,outbox:a.outbox}});
    } else reply(r.id,{structuredContent:{status:'rejected',mid:a.mid,outbox:a.outbox,reason:'Synthetic audience rejection'}});
    return;
   }
   let text;
   if(name==='get_data_catalog')text='Available data types, grouped by compatible tool: '+JSON.stringify({'data types usable with: get_records':[
    ...[out,...(window.second ? [out.slice(0,-1)+'8'] : [])].map(id=>({id,name:'Planning',description:'connect-agents-with-anyone channel\n[mesh_identifier: "Weekend"]',...schema})),
    ...[peer,other].map(fulcra_userid=>({id:incoming,name:'<img src=x onerror=alert(1)>',fulcra_userid,description:'connect-agents-with-anyone channel',...schema}))]});
   if(name==='list_shares')text='Shares: '+JSON.stringify({own_fulcra_userid:own,outgoing:[...(!window.excludeOut ? [out] : []),...(window.second ? [out.slice(0,-1)+'8'] : [])].map(id=>({share_all_data:false,data_types:[id],with_user_ids:window.audience,datashare_name:'connect-agents-with-anyone: synthetic'})),incoming:[peer,other].map((id,i)=>({sharing_fulcra_userid:id,sharing_fulcra_user_name:i?'Chris':'Alex',grant_type:'user',data_types:[incoming],datashare_name:'connect-agents-with-anyone: synthetic'}))});
   if(name==='get_records') {
    if(window.failReads) { reply(r.id,{isError:true,content:[{type:'text',text:'Synthetic read failure'}]}); return; }
    const records = a.fulcra_userid?[
    {id:a.fulcra_userid+'-1',start_time:'2026-10-13T11:00:00Z',sender:'SharedName',kind:'message',body:'Addressed message',recipients:['chatgpt']},
    {id:a.fulcra_userid+'-2',start_time:'2026-10-13T11:01:00Z',sender:'SharedName',kind:'message',body:'Other agent message',recipients:['ChatGPT','<script>bad</script>']},
    {id:a.fulcra_userid+'-3',start_time:'2026-10-13T11:02:00Z',sender:'SharedName',kind:'message',body:'Broadcast message',recipients:['all']}
    ]:window.ownRecords;
    text=`Records for ${a.data_type} from start to end: `+JSON.stringify(a.latest ? records.slice(-1) : records);
   }
   const respond=()=>reply(r.id,{content:[{type:'text',text}]});
   if(discovery && window.holdDiscovery)window.heldDiscovery.push(respond);
   else if(name==='get_records' && (window.holdReads === true
     || window.holdReads === (a.fulcra_userid ? 'incoming' : 'outgoing')
     || (window.holdReads === 'history' && !a.latest))) window.heldReads.push(respond);
   else respond();
  }); frame.srcdoc=bundle;
 },{bundle,schema,own,peer,other,out,incoming,holdReads,acceptAck,ownRecords});
 const ui=page.frameLocator('iframe');
 if (listOnly) { await expect(ui.locator('.thread-button').filter({hasText:'Weekend'})).toBeVisible(); return ui; }
 await ui.locator('.thread-button').filter({hasText:'Weekend'}).click();
 await expect(ui.locator('#messages .message-row')).toHaveCount(6);
 return ui;
}
