import test from 'node:test';
import assert from 'node:assert/strict';
import { discoverThreads, conversionSources } from './connections-discovery.js';
import { messageText } from './messages.js';
import { matchesPost } from './connection-send.js';
import schema from '../tests/fixtures/connection-schema.json' with { type: 'json' };

const own = '00000000-0000-4000-8000-000000000001', peer = '00000000-0000-4000-8000-000000000002';
const id = 'Event/00000000-0000-4000-8000-000000000003';
const old = 'MomentAnnotation/00000000-0000-4000-8000-000000000004';
const entry = { id, name:'Agent connection', description:'connect-agents-with-anyone channel', ...schema };
const share = { datashare_name:'connect-agents-with-anyone: synthetic', share_all_data:false,file_paths:[],file_history_paths:[],data_types:[id], with_user_ids:[peer] };
function app(catalog, outgoing=[share], incoming=[]) {
  return { callServerTool: async ({name, arguments: args}) => ({content:[{type:'text',text:name === 'get_data_catalog'
    ? 'Available data types, grouped by compatible tool: ' + JSON.stringify({'data types usable with: get_records':catalog.filter(e => !args.data_type || e.id === args.data_type)})
    : 'Shares: ' + JSON.stringify({own_fulcra_userid:own,outgoing,incoming})}]}) };
}
test('discovers Event contacts and isolates legacy without reading records', async () => {
  const result = await discoverThreads(app([entry,{id:old,name:'Mesh Outbox old',fulcra_userid:peer}],[share],
    [{grant_type:'user',sharing_fulcra_userid:peer,file_paths:[],file_history_paths:[],data_types:[old]}]));
  assert.equal(result.threads.length,1); assert.equal(result.legacy.length,1);
  assert.deepEqual(result.threads[0].sources.map(s=>s.id),[id]);
});
for (const prefix of ['connect-agents-with-anyone', 'connect-our-agents']) {
  test(`discovers ${prefix} channels and preserves grant checks`, async () => {
    const channel = { ...entry, description: `${prefix} channel` };
    const incoming = { grant_type: 'user', sharing_fulcra_userid: peer,file_paths:[],file_history_paths:[],data_types: [id], datashare_name: `${prefix}: test` };
    assert.equal((await discoverThreads(app([{ ...channel, fulcra_userid: peer }], [], [incoming]))).threads.length, 1);
    assert.equal((await discoverThreads(app([channel], [{ ...share, datashare_name: `${prefix}: test` }]))).threads.length, 1);
    assert.equal((await discoverThreads(app([channel], [share, { share_all_data: true }]))).threads.length, 1);
    assert.equal((await discoverThreads(app([{ ...channel, fields: {} }]))).threads.length, 0);
  });
}
test('same-peer broad overlap retains both directions without changing the audience', async () => {
  const incoming = { ...share, grant_type: 'user', sharing_fulcra_userid: peer };
  for (const extra of [
    { share_all_data: true, data_types: [] },
    { data_types: ['Event'] }, { data_types: ['Event/*'] },
    { data_types: ['*'] }, { data_types: [id, 'StepCount'] },
  ]) {
    const broad = { ...share, ...extra, datashare_name: 'Personal sharing' };
    const result = await discoverThreads(app([entry, { ...entry, fulcra_userid: peer }],
      [share, broad], [incoming, { ...incoming, ...extra }]));
    assert.equal(result.threads.length, 1);
    assert.deepEqual(result.threads[0].sources.map(s => s.direction).sort(), ['Incoming', 'Outgoing']);
    assert.equal(result.threads[0].peer, peer);
    assert.equal(result.threads[0].expectedPeerUserids, undefined);
    assert.equal(result.warnings.length, 0);
  }
});

test('broad access policy neither establishes nor expands a contact', async () => {
  const broad = { ...share, share_all_data: true, data_types: [], datashare_name: 'Personal sharing' };
  assert.equal((await discoverThreads(app([entry], [broad]))).threads.length, 0);
  for (const change of [
    { with_user_ids: [peer, 'another-peer'] }, { with_user_ids: [] },
    { with_group_ids: ['group'] }, { group_id: 'group' },
    { time_start: '2026-01-01T00:00:00Z' }, { time_end: '2027-01-01T00:00:00Z' },
  ]) {
    const result = await discoverThreads(app([entry], [share, { ...broad, ...change }]));
    assert.equal(result.threads.length, 1);
    assert.equal(result.threads[0].peer, peer);
    assert.equal(result.threads[0].expectedPeerUserids, undefined);
  }
  const multi = { ...share, with_user_ids: [peer, 'another-peer'] };
  const result = await discoverThreads(app([entry], [multi, broad]));
  assert.deepEqual(result.threads[0].expectedPeerUserids, ['another-peer', peer].sort());
});

test('all covering grants and channel schema are checked', async () => {
  assert.equal((await discoverThreads(app([entry],[share,{share_all_data:true}]))).threads.length,1);
  assert.equal((await discoverThreads(app([{...entry,fields:{}}]))).threads.length,0);
});
test('legacy group-only entries are excluded and owned provenance suppresses repeat conversion', async () => {
  const legacy={id:old,name:'Mesh Outbox old',fulcra_userid:peer};
  const grant={grant_type:'user',sharing_fulcra_userid:peer,file_paths:[],file_history_paths:[],data_types:[old]};
  assert.equal((await discoverThreads(app([legacy],[],[{...grant,grant_type:'group'}]))).legacy.length,0);
  const description=entry.description+'\nconverted_from_mesh: '+JSON.stringify([{id:old,fulcra_userid:peer}]);
  assert.equal((await discoverThreads(app([{...entry,description},legacy],[share],[grant]))).legacy.length,0);
});
test('a two-way contact with the same peer hides its legacy connection', async () => {
  const legacy={id:old,name:'Mesh Outbox old',fulcra_userid:peer};
  const grant={grant_type:'user',sharing_fulcra_userid:peer,file_paths:[],file_history_paths:[],data_types:[old]};
  const theirs={...entry,id:'Event/00000000-0000-4000-8000-000000000005',fulcra_userid:peer};
  const incoming={...grant,data_types:[theirs.id],datashare_name:'connect-our-agents: test'};
  assert.equal((await discoverThreads(app([entry,theirs,legacy],[share],[grant,incoming]))).legacy.length,0);
  assert.equal((await discoverThreads(app([entry,legacy],[share],[grant]))).legacy.length,1);
});
test('conversion metadata is bounded and exact owner scoped', () => {
  const refs = [{id:old,fulcra_userid:peer}];
  assert.deepEqual(conversionSources('connect-agents-with-anyone channel\nconverted_from_mesh: '+JSON.stringify(refs),own,peer),refs);
  assert.deepEqual(conversionSources('converted_from_mesh: '+JSON.stringify([{id:old,fulcra_userid:'attacker'}]),own,peer),[]);
});
test('renders Event body literally, never decodes legacy envelopes', () => {
  assert.equal(messageText({sender:'agent',kind:'message',body:'<script>not executable</script>'}),'<script>not executable</script>');
  assert.doesNotMatch(messageText({note:'{"v":1,"body":"legacy secret"}'}),/legacy secret/);
});
test('Event readback matches only the message id', () => {
  const record = {id:'stable',sender:'me',kind:'message',body:'hi',topic:'chat',priority:'P2'};
  const source = {id,fulcra_userid:own};
  const post = {source,envelope:record};
  assert.equal(matchesPost({direction:'Outgoing',source,record:{...record,start_time:'now'}},post),true);
  assert.equal(matchesPost({direction:'Incoming',source:{},record:{id:'stable',recipients:['other']}},post),true);
  assert.equal(matchesPost({record:{...record,id:'different'}},post),false);
});
