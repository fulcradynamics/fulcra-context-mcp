import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {build} from 'esbuild';
const template=await readFile(new URL('index.html',import.meta.url),'utf8');
const bundled=await build({entryPoints:[new URL('main.js',import.meta.url).pathname],bundle:true,write:false,format:'iife',platform:'browser',target:'es2022'});
const html=template.replace('/* APP_SCRIPT */',()=>bundled.outputFiles[0].text);
const schema=JSON.parse(await readFile(new URL('../tests/fixtures/connection-schema.json',import.meta.url),'utf8'));
const own='00000000-0000-4000-8000-000000000001', a='00000000-0000-4000-8000-000000000002', b='00000000-0000-4000-8000-000000000003';
async function host(page,{legacyOnly=false,hold=false}={}) {
  await page.clock.install();
  await page.clock.pauseAt(new Date());
  await page.setContent('<iframe sandbox="allow-scripts" style="width:100%;height:900px"></iframe>');
  await page.evaluate(({html,schema,own,a,b,legacyOnly,hold})=>{
    window.calls=[];window.sent=[];window.context={content:[]};window.hold=hold;
    window.entries=[a,b].flatMap(p=>[
      {id:'MomentAnnotation/'+p,name:'Mesh Outbox old',fulcra_userid:p},
      ...(legacyOnly?[]:[{id:'Event/'+p,name:'Connection',fulcra_userid:p,...schema,
        description:'connect-agents-with-anyone channel\nconverted_from_mesh: '+JSON.stringify([{id:'MomentAnnotation/'+p,fulcra_userid:p}])}])]);
    window.incoming=window.entries.map(e=>({sharing_fulcra_userid:e.fulcra_userid,grant_type:'user',data_types:[e.id],datashare_name:'connect-agents-with-anyone: test'}));
    const frame=document.querySelector('iframe');
    const reply=(req,result)=>frame.contentWindow.postMessage({jsonrpc:'2.0',id:req.id,result},'*');
    window.release=()=>{window.hold=false;reply(window.held,{});window.held=null;};
    addEventListener('message',event=>{
      if(event.source!==frame.contentWindow)return;
      const req=event.data;window.calls.push(req);let result;
      if(req.method==='ui/initialize')result={protocolVersion:'2026-01-26',hostInfo:{name:'test',version:'1'},hostCapabilities:{message:{text:{}},updateModelContext:{text:{}}},hostContext:{displayMode:'fullscreen'}};
      else if(req.method==='tools/call'){
        const args=req.params.arguments;
        if(req.params.name==='get_data_catalog')result={content:[{type:'text',text:'Available data types, grouped by compatible tool: '+JSON.stringify({'data types usable with: get_records':window.entries.filter(e=>!args.data_type||e.id===args.data_type&&e.fulcra_userid===args.fulcra_userid)})}]};
        else if(req.params.name==='list_shares')result={content:[{type:'text',text:'Shares: '+JSON.stringify({own_fulcra_userid:own,outgoing:[],incoming:window.incoming})}]};
        else if(req.params.name==='get_records')result={content:[{type:'text',text:'Records for '+args.data_type+' from '+args.start_time+' to '+args.end_time+': []'}]};
        else throw Error('Unexpected tool '+req.params.name);
      }else if(req.method==='ui/update-model-context'){
        window.context=req.params;
        if(window.hold&&req.params.content.length){window.held=req;return;}
        result={};
      }else if(req.method==='ui/message'){window.sent.push({request:req.params,context:window.context});result={};}
      else return;
      reply(req,result);
    });
    frame.srcdoc=html;
  },{html,schema,own,a,b,legacyOnly,hold});
  const ui=page.frameLocator('iframe');
  await expect(ui.getByRole('button',{name:'Convert to Contact',exact:true})).toHaveCount(2);
  return ui;
}
async function open(ui,peer) {
  await ui.getByRole('button',{name:peer,exact:true}).click();
  await expect(ui.locator('#message-status')).toHaveText('No messages in this date range.');
}
const history=ui=>ui.getByRole('button',{name:'chat about old messages',exact:true,includeHidden:true});
test('known revocation cannot reattach history after refresh',async({page})=>{
  const ui=await host(page);await open(ui,a);
  await page.evaluate(a=>{window.entries=window.entries.filter(e=>e.fulcra_userid!==a);window.incoming=window.incoming.filter(s=>s.sharing_fulcra_userid!==a);},a);
  await ui.getByRole('button',{name:'Load messages',exact:true}).click();
  await expect(ui.locator('#message-status')).toContainText('no longer available');
  // A programmatic click also exercises the handler guard when hidden/disabled.
  await history(ui).evaluate(button=>button.click());
  expect(await page.evaluate(()=>window.sent.length)).toBe(0);
  await expect(history(ui)).toBeDisabled();
});
test('history-only revocation invalidates an accepted but unacknowledged attachment',async({page})=>{
  const ui=await host(page,{hold:true});await open(ui,a);await history(ui).click();
  await expect.poll(()=>page.evaluate(()=>!!window.held)).toBe(true);
  await page.evaluate(a=>{
    window.entries=window.entries.filter(e=>e.id!=='MomentAnnotation/'+a);
    window.incoming=window.incoming.filter(s=>s.data_types[0]!=='MomentAnnotation/'+a);
  },a);
  await ui.getByRole('button',{name:'Load messages',exact:true}).click();
  await expect(ui.getByText('Converted from mesh',{exact:true})).toBeHidden();
  await page.evaluate(()=>window.release());
  await expect.poll(()=>page.evaluate(()=>window.context.content.length)).toBe(0);
  expect(await page.evaluate(()=>window.sent.length)).toBe(0);
  await expect(history(ui)).toBeDisabled();
});

test('history lock belongs to originating peer and exact sources, not reused button',async({page})=>{
  const ui=await host(page);await open(ui,a);await history(ui).click();
  await expect.poll(()=>page.evaluate(()=>window.sent.length)).toBe(1);
  await expect.poll(()=>page.evaluate(()=>window.context.content.length)).toBe(0);
  await ui.getByRole('button',{name:'Back to threads',exact:true}).click();await open(ui,b);
  await expect(history(ui)).toBeEnabled();await history(ui).click();
  await expect.poll(()=>page.evaluate(()=>window.sent.length)).toBe(2);
  await ui.getByRole('button',{name:'Back to threads',exact:true}).click();await open(ui,a);
  await expect(history(ui)).toBeDisabled();
});
for(const action of ['conversion','history']) test(`invitation is isolated from pending ${action}`,async({page})=>{
  const ui=await host(page,{legacyOnly:action==='conversion',hold:true});
  if(action==='history'){await open(ui,a);await history(ui).click();}
  else await ui.getByRole('button',{name:'Convert to Contact',exact:true}).first().click();
  await expect.poll(()=>page.evaluate(()=>!!window.held)).toBe(true);
  await ui.locator('#invite').evaluate(button=>button.click());
  expect(await page.evaluate(()=>window.sent.length)).toBe(0);
  await page.evaluate(()=>window.release());
  await expect.poll(()=>page.evaluate(()=>window.sent.length)).toBe(1);
  await expect.poll(()=>page.evaluate(()=>window.context.content.length)).toBe(0);
  await ui.getByRole('button',{name:'Invite someone',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>window.sent.length)).toBe(2);
  expect(await page.evaluate(()=>window.sent[1].context.content)).toEqual([]);
});
