const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('assets/openband.js','utf8');
const lines = source.split('\n');
const status={hidden:true,textContent:''};
let requests=0, mode='error';
const context=vm.createContext({console:{warn:()=>{}},AbortSignal,
  el:()=>status, mapPromise:null,mapData:{},
  fetch:async()=>{requests++;if(mode==='error')return {ok:false,status:503};
    return {ok:true,json:async()=>mode==='invalid'?{communities:null}:{communities:[{id:448}]}};}});
vm.runInContext(lines.filter(line=>['const dataLoadErrors=', 'function renderDataLoadStatus(',
  'async function fetchDataset(', 'async function loadMapData(', 'function validMapPoint(', 'function renderNote(', 'function renderSummary(', 'function iscLeadershipNote(', 'function updateMapLoadStatus('].some(prefix=>line.startsWith(prefix))).join('\n'),context);
(async()=>{
  await context.loadMapData();
  assert.equal(status.hidden,false);
  assert.match(status.textContent,/map \(HTTP 503\)/);
  mode='invalid';await context.loadMapData();
  assert.match(status.textContent,/Invalid dataset/);
  mode='ok';await context.loadMapData();
  assert.equal(status.hidden,true,'A successful retry clears the error');
  assert.equal(context.mapData.communities.length,1);
  await context.loadMapData();assert.equal(requests,3,'Successful requests remain cached');
  assert.equal(context.validMapPoint({latitude:null,longitude:null}),false);
  assert.equal(context.validMapPoint({latitude:Infinity,longitude:-110}),false);
  assert.equal(context.validMapPoint({latitude:91,longitude:-110}),false);
  assert.equal(context.validMapPoint({latitude:54,longitude:-110}),true);
  const nodes={srcNote:{innerHTML:''},sTotal:{nextElementSibling:{}},sRemun:{},sExp:{},sOther:{},sCount:{}};
  Object.assign(context,{el:id=>nodes[id],getFilingStatus:()=>({label:'Parsed'}),
    getSourceLinks:()=>({pdf:'https://example.org/source.pdf'}),methodName:()=> 'source review',
    esc:value=>String(value).replaceAll('<','&lt;').replaceAll('>','&gt;'),formatMoney:String,
    currentFiling:()=>({manualSourceReview:{totalMethod:'sum_of_reported_components'}})});
  context.renderNote({warnings:['Printed total differs by $1. <script>'],parse_status:'parsed'},{});
  assert.match(nodes.srcNote.innerHTML,/Printed total differs by \$1/);
  assert.ok(!nodes.srcNote.innerHTML.includes('<script>'),'Source notes must be escaped');
  context.renderSummary({total:100,remuneration:80,travelExpenses:20,other:0,officials:1});
  assert.equal(nodes.sTotal.nextElementSibling.textContent,'Sum of reported components');
  assert.match(context.iscLeadershipNote({leadership:{retrievedAt:'2026-10-02',officials:[{expiryDate:'09/30/2026'}]}},'2026-10-09'),/1 listed term has ended/);
  assert.match(context.iscLeadershipNote({leadership:{officials:[]}},'2026-10-09'),/Confirm current officeholders/);
  nodes.mapLoading={};context.directoryMap={};
  vm.runInContext("dataLoadErrors.map='HTTP 503'",context);context.updateMapLoadStatus();
  assert.equal(nodes.mapLoading.hidden,false);
  vm.runInContext('delete dataLoadErrors.map',context);context.updateMapLoadStatus();
  assert.equal(nodes.mapLoading.hidden,true,'Recovered map data clears an existing failure overlay');
  console.log('Dataset failure, schema, retry, cache and map coordinate tests passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
