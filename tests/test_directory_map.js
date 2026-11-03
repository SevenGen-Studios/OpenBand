const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/openband.js','utf8');
const navigation=source.slice(source.indexOf('const PROVINCE_MAP_BOUNDS='),source.indexOf('const RESERVE_LAND_URL='));
// Small Leaflet-compatible geometry fixture; verify viewport restrictions in
// projected space rather than assuming a fixed geographic viewport size.
class Point{
  constructor(x,y){if(Array.isArray(x))[x,y]=x;this.x=x;this.y=y}
  add(p){return new Point(this.x+p.x,this.y+p.y)}
  subtract(p){return new Point(this.x-p.x,this.y-p.y)}
  divideBy(n){return new Point(this.x/n,this.y/n)}
}
class Bounds{
  constructor(a,b){this.south=Infinity;this.west=Infinity;this.north=-Infinity;this.east=-Infinity;(b?[a,b]:a).forEach(p=>this.extend(p))}
  extend(p){const [lat,lng]=Array.isArray(p)?p:[p.lat,p.lng];this.south=Math.min(this.south,lat);this.north=Math.max(this.north,lat);this.west=Math.min(this.west,lng);this.east=Math.max(this.east,lng);return this}
  pad(n){const h=(this.north-this.south)*n,w=(this.east-this.west)*n;return new Bounds([[this.south-h,this.west-w],[this.north+h,this.east+w]])}
  getNorthWest(){return {lat:this.north,lng:this.west}}
  getSouthEast(){return {lat:this.south,lng:this.east}}
  contains(p){return p.lat>=this.south&&p.lat<=this.north&&p.lng>=this.west&&p.lng<=this.east}
  toArray(){return [[this.south,this.west],[this.north,this.east]]}
}
let province='AB',reduced=false,lastBounds,lastOptions,flights=0,fits=0,completion,roster=[];
const fields=Object.fromEntries(['directorySearch','treatyFilter','tribalCouncilFilter'].map(id=>[id,{value:'',options:[{},{}]}]));
const map={
  size:new Point(1400,520),zoom:5,stop(){},off(){completion=null},once(event,fn){completion=fn},
  setMaxBounds(b){this.maxBounds=b},setMinZoom(n){this.minZoom=n},getZoom(){return this.zoom},getSize(){return this.size},getBoundsZoom(){return 5.37},
  project(p,z){const scale=2**z;return new Point(p.lng*scale,-p.lat*scale)},unproject(p,z){const scale=2**z;return {lat:-p.y/scale,lng:p.x/scale}},
  fitBounds(b,o){fits++;lastBounds=b.toArray();lastOptions=o},flyToBounds(b,o){flights++;lastBounds=b.toArray();lastOptions=o}
};
const context=vm.createContext({
  selectedProvince:()=>province,el:id=>fields[id],directoryMap:map,provinceBands:()=>roster,directoryMapRecord:b=>b,validMapPoint:r=>r&&Number.isFinite(r.latitude)&&Number.isFinite(r.longitude),
  window:{L:{latLngBounds:(a,b)=>new Bounds(a,b),point:p=>new Point(p)},matchMedia:()=>({matches:reduced})},
});
vm.runInContext(navigation,context);
const bounds=JSON.parse(vm.runInContext('JSON.stringify(PROVINCE_MAP_BOUNDS)',context));
assert.equal(Object.keys(bounds).length,13);
context.fitDirectoryMap();
assert.deepEqual(lastBounds,bounds.AB);assert.equal(fits,1);assert.equal(flights,0);
assert.equal(map.minZoom,4.62);assert.ok(map.maxBounds.contains({lat:54.5,lng:-115}));
context.fitDirectoryMap();assert.equal(fits,1,'Background renders preserve manual camera position');
for(const code of Object.keys(bounds)){
  province=code;context.fitDirectoryMap();assert.deepEqual(lastBounds,bounds[code],code+' uses its own boundary envelope');
  assert.equal(map.maxBounds,null,'Old pan restrictions removed during travel');completion();
  const b=map.maxBounds,half=map.size.divideBy(2),z=map.zoom;
  for(const c of [bounds[code][0],bounds[code][1]]){
    const p=map.project({lat:c[0],lng:c[1]},z);
    assert(b.contains(map.unproject(p.add(half),z))&&b.contains(map.unproject(p.subtract(half),z)),code+' pan limits allow viewport edges without shifting the province');
  }
}
// Recalculate pan envelope at different zooms and phone-sized viewports.
for(const width of [360,1800])for(const zoom of [3,12]){map.size=new Point(width,520);map.zoom=zoom;context.updateDirectoryPanBounds();assert(map.maxBounds.contains({lat:46.5,lng:-63}))}
province='AB';roster=[{latitude:60.1,longitude:-111}];context.fitDirectoryMap();completion();assert.equal(lastBounds[1][0],60.1,'Cross-border roster marker stays in frame');roster=[];
fields.directorySearch.value='Nation';context.fitDirectoryMap([[53,-114]]);completion();assert.deepEqual(lastBounds,[[53,-114],[53,-114]]);assert.equal(lastOptions.maxZoom,8);
context.fitDirectoryMap([],{force:true,reset:true});completion();assert.deepEqual(lastBounds,bounds.AB,'Reset ignores active filters and restores province');
context.fitDirectoryMap([],{force:true});completion();assert.deepEqual(lastBounds,bounds.AB,'Empty results retain province framing');
fields.directorySearch.value='';reduced=true;province='NU';const previousFlights=flights;context.fitDirectoryMap();assert.equal(flights,previousFlights);assert.equal(lastOptions.animate,false);assert(map.maxBounds);
province='';context.fitDirectoryMap();assert.deepEqual(lastBounds,[[49,-120],[60,-88.9]]);assert.equal(map.maxBounds,null,'Overview removes provincial restrictions');
// Exercise the actual map setup to catch option regressions and keep tiles
// available beyond the province even when the camera has soft pan limits.
let mapOptions,tileOptions;
const addable={addTo:()=>addable},mapStub={on(){},createPane:()=>({style:{}})};
const setup=vm.createContext({directoryMap:null,directoryLayer:null,reserveLandData:null,dataLoadErrors:{},el:()=>({}),setupDirectoryNavigation(){},selectedProvince:()=>province,mapReducedMotion:()=>false,updateDirectoryPanBounds(){},window:{L:{map:(id,o)=>{mapOptions=o;return mapStub},tileLayer:(u,o)=>{tileOptions=o;return addable},control:{zoom:()=>addable,scale:()=>addable},layerGroup:()=>addable}}});
vm.runInContext(source.split('\n').find(l=>l.startsWith('function ensureDirectoryMap(')),setup);setup.ensureDirectoryMap();
assert.equal(mapOptions.maxBounds,undefined);assert.equal(tileOptions.bounds,undefined);assert.equal(mapOptions.touchZoom,true);assert.equal(mapOptions.zoomSnap,.1);assert.equal(mapOptions.zoomDelta,.25);assert.equal(mapOptions.scrollWheelZoom,true);assert(tileOptions.keepBuffer>=3);
// Community markers must render before the slow reserve geometry arrives.
let ready=false,renders=0,finishBoundaries;
Object.assign(context,{setView(){},setDocumentMeta(){},loadCapitalData:()=>new Promise(()=>{}),loadMapData:async()=>{},updateProvinceUI(){},renderDirectory(){if(ready)renders++},loadLeaflet:async()=>{},ensureDirectoryMap(){ready=true},loadReserveLandData:()=>new Promise(resolve=>finishBoundaries=resolve),renderReserveLandLayer(){},renderProvinceFinance(){},renderDataLoadStatus(){},dataLoadErrors:{},document:{body:{dataset:{view:'directory'}}},console});
vm.runInContext(source.split('\n').find(l=>l.startsWith('async function showDirectoryPage(')),context);
(async()=>{const pending=context.showDirectoryPage({history:true,scroll:false});await new Promise(resolve=>setImmediate(resolve));assert.ok(finishBoundaries);assert(renders>0);finishBoundaries();await pending;console.log('Directory map: 13 regions, soft pan bounds, camera persistence, reset, motion preferences and nonblocking loading passed.');})().catch(error=>{console.error(error);process.exitCode=1});
