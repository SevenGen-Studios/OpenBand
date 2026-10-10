const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('assets/openband.js', 'utf8');
const list = {innerHTML:'',items:[],appendChild(item){this.items.push(item)}};
let bands=[];
const context = vm.createContext({Date, provinceBands:()=>bands,
  remFilingsByYear:b=>b.filings, hasRows:f=>Boolean(f.people?.length),
  el:()=>list, document:{createElement:()=>({querySelector:()=>({})})},
  nationLogoMarkup:()=>'', getFilingStatus:()=>({label:'Parsed'}),
  esc:String, timeAgo:v=>v, pick:()=>{}});
vm.runInContext(source.split('\n').filter(l=>['recentTimestamp','renderRecentlyUpdated'].some(n=>l.startsWith(`function ${n}(`))).join('\n'),context);
assert.equal(context.recentTimestamp({}, {manualSourceReview:{reviewedAt:'2026-10-10'}}),'2026-10-10');
assert.equal(context.recentTimestamp({}, {reparsed:'2026-10-11T01:00:00Z',manualSourceReview:{reviewedAt:'2026-10-10'}}),'2026-10-11T01:00:00Z');
assert.equal(context.recentTimestamp({scraped:'2026-09-18'}, {updated:'invalid',manualSourceReview:{reviewedAt:'bad'}}),'2026-09-18');
assert.equal(context.recentTimestamp(null, {manual_override:true,parse_confidence:'manual_reviewed',people:[{sourceReference:{checkedAt:'2026-10-09'}}]}),'2026-10-09');
bands=[{id:1,name:'Old scrape',scraped:'2026-09-18',filings:[{year:'2024-2025',people:[{}]}]},
       {id:2,name:'Reviewed schedule',scraped:'2026-09-18',filings:[{year:'2014-2015',people:[{}],manualSourceReview:{reviewedAt:'2026-10-10'}},{year:'2024-2025',people:[{}]}]}];
context.renderRecentlyUpdated();
assert.match(list.items[0].innerHTML,/Reviewed schedule/);
assert.match(list.items[0].innerHTML,/2014-2015/);
assert.equal(list.items.length,2,'One card per Nation');
bands=JSON.parse(fs.readFileSync('data.json','utf8')).bands.filter(b=>b.province==='SK');
list.items=[];context.renderRecentlyUpdated();
assert(list.items.some(i=>i.innerHTML.includes('Day Star First Nation')),'Live reviewed Day Star must enter the recent updates list');
assert(list.items.some(i=>i.innerHTML.includes('George Gordon First Nation')),'The next reviewed batch must appear');
console.log('Recent updates include source-reviewed corrections and preserve scraped fallbacks.');
