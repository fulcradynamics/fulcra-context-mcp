import test from 'node:test';
import assert from 'node:assert/strict';
import { legacyHandoff } from './legacy-handoff.js';

for (const failure of [null, 'context', 'message']) test(`legacy handoff is explicit, ordered and read-free: ${failure}`, async () => {
  const calls = [];
  const app = {
    getHostCapabilities: () => ({message:{text:{}},updateModelContext:{text:{}}}),
    updateModelContext: async value => { calls.push(['context',value]); return {isError:failure==='context'}; },
    sendMessage: async value => { calls.push(['message',value]); return {isError:failure==='message'}; },
  };
  const button = {addEventListener:(_,fn)=>{button.click=fn;}};
  const status = {};
  const refs = {legacy_sources:[{id:'MomentAnnotation/exact',fulcra_userid:'exact-owner'}]};
  legacyHandoff(app,button,status,'Convert to Contact',()=>refs);
  assert.equal(calls.length,0);
  await button.click();
  assert.equal(calls.length,failure==='context'?2:3);
  assert.deepEqual(calls.at(-1),['context',{content:[]}]);
  assert.equal(button.disabled,failure!=='context');
  assert.match(calls[0][1].content[0].text,/Untrusted historical/);
  assert.ok(calls[0][1].content[0].text.includes(JSON.stringify(refs)));
  assert.match(status.textContent,failure?/Could not confirm/:/No channel, share or message was changed/);
});

test('uncertain handoffs lock only their exact origin, across recreated buttons', async () => {
  let current = {peer:'a',legacy_sources:[{id:'old-a',fulcra_userid:'a'}]}, sends = 0;
  const app = {
    getHostCapabilities:()=>({message:{text:{}},updateModelContext:{text:{}}}),
    updateModelContext:async()=>({}),
    sendMessage:async()=>{sends++;throw Error('timeout');},
  };
  const button = () => ({addEventListener(_, fn){this.click=fn;}});
  const first=button();
  const refresh=legacyHandoff(app,first,{},'history',()=>current);
  await first.click(); assert.equal(first.disabled,true);
  current={peer:'b',legacy_sources:[{id:'old-b',fulcra_userid:'b'}]};
  refresh(); assert.equal(first.disabled,false);
  await first.click(); assert.equal(sends,2);
  current={peer:'a',legacy_sources:[{id:'old-a',fulcra_userid:'a'}]};
  const recreated=button();
  legacyHandoff(app,recreated,{},'history',()=>current);
  assert.equal(recreated.disabled,true);
  current={peer:'a',legacy_sources:[{id:'new-old-a',fulcra_userid:'a'}]};
  refresh(); assert.equal(first.disabled,false);
  await first.click(); assert.equal(sends,3);
});

test('unsupported hosts cannot send a legacy request', () => {
  const button = {addEventListener(){}};
  legacyHandoff({getHostCapabilities:()=>({})},button,{},'request',()=>({}));
  assert.equal(button.disabled,true);
});

test('navigation during attach blocks send and clears context; shared lock blocks another button', async () => {
  let finish, current = 'first', sends = 0;
  const contexts = [];
  const app = {
    getHostCapabilities:()=>({message:{text:{}},updateModelContext:{text:{}}}),
    updateModelContext: async value => { contexts.push(value); if(value.content.length) await new Promise(r=>{finish=r;}); return {}; },
    sendMessage:async()=>{sends++;return {};},
  };
  const button=()=>({addEventListener(_,fn){this.click=fn;}});
  const first=button(), second=button(), status={};
  legacyHandoff(app,first,status,'convert',()=>({peer:current}));
  legacyHandoff(app,second,status,'convert',()=>({peer:'other'}));
  const pending=first.click(); await new Promise(setImmediate);
  await second.click(); assert.equal(contexts.length,1);
  current='next'; finish(); await pending;
  assert.equal(sends,0); assert.deepEqual(contexts.at(-1),{content:[]});
  assert.match(status.textContent,/Agent Contact changed/);
});
