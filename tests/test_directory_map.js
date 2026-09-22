const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('assets/openband.js', 'utf8');
const extracted = source.split('\n').filter(line =>
  ['const PROVINCE_MAP_BOUNDS=', 'function fitDirectoryMap(', 'async function showDirectoryPage('].some(prefix => line.startsWith(prefix))).join('\n');
// Exercise the real Leaflet setup: hard geographic limits previously shifted
// Alberta east even though fitBounds received the correct province coordinates.
let mapOptions, tileOptions;
const mapStub = {on:()=>{}, createPane:()=>({style:{}})};
const addable = {addTo:()=>addable};
const setup = vm.createContext({
  directoryMap:null, directoryLayer:null, reserveLandData:null,
  el:()=>({}), fitDirectoryMap:()=>{},
  window:{L:{map:(id,options)=>{mapOptions=options;return mapStub;},
    tileLayer:(url,options)=>{tileOptions=options;return addable;},
    control:{zoom:()=>addable,scale:()=>addable},layerGroup:()=>addable}}
});
vm.runInContext(source.split('\n').find(line=>line.startsWith('function ensureDirectoryMap(')),setup);
setup.ensureDirectoryMap();
assert.equal(mapOptions.maxBounds,undefined,'Pan limits must not shift province centering');
assert.equal(tileOptions.bounds,undefined,'Tiles must fill the viewport west of Alberta');
let province = 'AB';
let lastBounds;
let renders = 0;
let ready = false;
let finishBoundaries;
const fields = Object.fromEntries(['directorySearch', 'treatyFilter', 'tribalCouncilFilter'].map(id => [id, {value:'', options:[{},{}]}]));
const context = vm.createContext({
  selectedProvince: () => province, el: id => fields[id],
  directoryMap: {fitBounds: bounds => {lastBounds = JSON.parse(JSON.stringify(bounds));}},
  window: {L:{latLngBounds: points => ({pad: () => points})}},
  setView:()=>{}, setDocumentMeta:()=>{}, loadCapitalData:async()=>{}, loadMapData:async()=>{},
  updateProvinceUI:()=>{}, renderDirectory:()=>{if(ready)renders++;},
  loadLeaflet:async()=>{}, ensureDirectoryMap:()=>{ready=true;},
  loadReserveLandData:()=>new Promise(resolve=>{finishBoundaries=resolve;}),
  renderReserveLandLayer:()=>{}, console
});
vm.runInContext(extracted, context);
context.fitDirectoryMap();
assert.deepEqual(lastBounds, [[49,-120],[60,-110]], 'Alberta initial viewport');
province = 'SK'; context.fitDirectoryMap();
assert.deepEqual(lastBounds, [[49,-110],[60,-101.35]], 'Switch to Saskatchewan');
province = ''; context.fitDirectoryMap();
assert.deepEqual(lastBounds, [[49,-120],[60,-101.35]], 'Reset to both provinces');
province = 'AB'; fields.directorySearch.value = 'Nation';
context.fitDirectoryMap([[53,-114]]);
assert.deepEqual(lastBounds, [[53,-114]], 'Search focuses matching communities');
context.fitDirectoryMap([]);
assert.deepEqual(lastBounds, [[49,-120],[60,-110]], 'Empty results retain selected province');
(async()=>{
  const pending = context.showDirectoryPage({history:true,scroll:false});
  await new Promise(resolve => setImmediate(resolve));
  assert.ok(finishBoundaries, 'Boundary request started');
  assert.ok(renders > 0, 'Map renders before boundary request completes');
  finishBoundaries(); await pending;
  console.log('Directory map viewport tests passed');
})().catch(error => {console.error(error);process.exitCode=1;});
