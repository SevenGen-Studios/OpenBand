const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elections=JSON.parse(fs.readFileSync('elections-data.json','utf8'));
const rows=elections.records.filter(row=>row.firstNationId===458);
assert.equal(rows.length,11);
assert.equal(rows.filter(row=>row.position==='Chief').length,1);
assert.equal(rows.find(row=>row.position==='Chief').candidateName,'Margo Auger');
assert.equal(rows.filter(row=>row.position==='Councillor').length,10);
assert(rows.every(row=>row.electionDate==='2026-09-29'&&row.votesReceived===null));
assert(!elections.coverage.unverifiedNationIds.includes(458));
const source=fs.readFileSync('assets/openband.js','utf8');
const funcs=source.slice(source.indexOf('function electionRecordsForBand('),source.indexOf('function identitySourceUrl('));
const escape=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const context=vm.createContext({electionsData:elections,esc:escape,escAttr:escape,formatNumber:n=>String(n)});
vm.runInContext(funcs,context);
const live=context.electionOverviewMarkup({id:458,leadership:{officials:[]}});
const page=fs.readFileSync('first-nations/bigstone-cree-nation/index.html','utf8');
const card=page.match(/<section class="election-card"[\s\S]*?<\/section>/)[0];
for(const markup of [live,card]){
 for(const row of rows)assert(markup.includes(row.candidateName),row.candidateName);
 assert.equal((markup.match(/<li>/g)||[]).length,11);
 assert(markup.includes('Latest election'));
 assert(markup.includes('Next Election - 2030'));
 assert(markup.includes('Lakeside Leader'));
 assert(!markup.includes('0 votes'));
 assert(!markup.includes('not yet indexed'));
}
assert(live.includes('September 29, 2026'));
assert(card.includes('2026-09-29'));
console.log('Bigstone leadership: verified roster, election date, static/live parity and absent vote totals passed');
