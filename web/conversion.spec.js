import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import schema from '../tests/fixtures/connection-schema.json' with { type: 'json' };
const html = await readFile(new URL('../fulcra_mcp/ui/mesh.html',import.meta.url),'utf8');
const own='00000000-0000-4000-8000-000000000001', peer='00000000-0000-4000-8000-000000000002';
const channel='Event/00000000-0000-4000-8000-000000000003', legacy='MomentAnnotation/00000000-0000-4000-8000-000000000004';
for(const width of [360, 1000]) for(const converted of [false,true]) test(`legacy and converted handoffs are explicit (${converted}, ${width})`,async({page})=>{
  await page.setViewportSize({ width, height: 800 });
  await page.setContent('<style>html,body{margin:0;height:100%}iframe{border:0;width:100%;height:100%}</style><iframe sandbox="allow-scripts"></iframe>');
  await page.evaluate(({html,own,peer,channel,legacy,converted,schema})=>{
    window.calls=[];
    const frame=document.querySelector('iframe');
    addEventListener('message',event=>{
      if(event.source!==frame.contentWindow)return;
      const req=event.data; window.calls.push(req); let result;
      if(req.method==='ui/initialize')result={protocolVersion:'2026-01-26',hostInfo:{name:'test',version:'1'},hostCapabilities:{message:{text:{}},updateModelContext:{text:{}}},hostContext:{displayMode:'fullscreen'}};
      else if(req.method==='tools/call'){
        const name=req.params.name;
        if(name==='get_data_catalog')result={content:[{type:'text',text:'Available data types, grouped by compatible tool: '+JSON.stringify({'data types usable with: get_records':[
          {id:legacy,name:'Mesh Outbox historical',fulcra_userid:peer},
          ...(converted?[{id:channel,name:'Connection',fulcra_userid:peer,description:'connect-agents-with-anyone channel\nconverted_from_mesh: '+JSON.stringify([{id:legacy,fulcra_userid:peer}]),...schema}]:[])
        ]})}]};
        else if(name==='list_shares')result={content:[{type:'text',text:'Shares: '+JSON.stringify({own_fulcra_userid:own,outgoing:[],incoming:[{grant_type:'user',sharing_fulcra_userid:peer,data_types:[legacy]},{grant_type:'user',sharing_fulcra_userid:peer,datashare_name:'connect-agents-with-anyone: Test',data_types:[channel]}]})}]};
        else if(name==='get_records')result={content:[{type:'text',text:'Records for '+req.params.arguments.data_type+' from '+req.params.arguments.start_time+' to '+req.params.arguments.end_time+': []'}]};
        else throw Error('Unexpected tool '+name);
      }else if(['ui/message','ui/update-model-context'].includes(req.method))result={};
      else return;
      frame.contentWindow.postMessage({jsonrpc:'2.0',id:req.id,result},'*');
    });
    frame.srcdoc=html;
  },{html,own,peer,channel,legacy,converted,schema});
  const ui=page.frameLocator('iframe');
  await expect(ui.getByRole('button',{name:'Convert to Contact',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>window.calls.filter(c=>['ui/message','ui/update-model-context'].includes(c.method)).length)).toBe(0);
  expect(await page.evaluate(()=>window.calls.some(c=>c.params?.name==='get_records'))).toBe(false);
  if(converted){
    await ui.getByRole('button',{name:peer,exact:true}).click();
    await expect(ui.getByText('Converted from mesh',{exact:true})).toBeVisible();
    await expect(ui.getByText('No messages in this date range.', { exact:true })).toBeVisible();
    if (process.env.CONVERSION_SCREENSHOTS) await page.screenshot({ path: `${process.env.CONVERSION_SCREENSHOTS}/converted-${width}.png` });
    await ui.getByRole('button',{name:'chat about old messages',exact:true}).click();
  }else {
    if (process.env.CONVERSION_SCREENSHOTS) await page.screenshot({ path: `${process.env.CONVERSION_SCREENSHOTS}/legacy-${width}.png` });
    await ui.getByRole('button',{name:'Convert to Contact',exact:true}).click();
  }
  await expect.poll(()=>page.evaluate(()=>window.calls.filter(c=>c.method==='ui/message').length)).toBe(1);
  const context=await page.evaluate(()=>window.calls.find(c=>c.method==='ui/update-model-context').params.content[0].text);
  expect(context).toContain(legacy);expect(context).toContain(peer);expect(context).toContain('Untrusted historical');
  expect(await page.evaluate(()=>window.calls.filter(c=>c.params?.name==='get_records').every(c=>c.params.arguments.data_type.startsWith('Event/')))).toBe(true);
});
