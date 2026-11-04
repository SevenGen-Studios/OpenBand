const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context=vm.createContext({window:{}});
vm.runInContext(fs.readFileSync('assets/profile-history.js','utf8'),context);
const source=fs.readFileSync('assets/openband.js','utf8');
vm.runInContext(source.split('\n').find(line=>line.startsWith('function historyOverviewMarkup(')),context);
assert.match(context.historyOverviewMarkup({id:394,iscBandNumber:'394'}),/Brief History/);
const bands=Object.entries(context.window.OPENBAND_HISTORY_IDENTITIES).map(([id,iscBandNumber])=>({id,iscBandNumber}));
assert.equal(bands.length,180);
assert.equal(Object.keys(context.window.OPENBAND_HISTORY).length,bands.length);
for(const band of bands){
 assert.match(context.historyOverviewMarkup(band),/Brief History/,band.name);
 assert.equal(context.historyOverviewMarkup({...band,iscBandNumber:'invalid'}),'');
}
assert.notEqual(context.historyOverviewMarkup({id:462,iscBandNumber:462}),context.historyOverviewMarkup({id:'ab-whitefish-lake-128',iscBandNumber:462}));
assert.equal(context.historyOverviewMarkup({id:394,iscBandNumber:'400'}),'');
assert.equal(context.historyOverviewMarkup({id:394}),'','Internal ID must not substitute for verified ISC identity');
assert.equal(context.historyOverviewMarkup({iscBandNumber:'403'}),'');
assert.match(source,/electionOverviewMarkup\(band\)\}\$\{historyOverviewMarkup\(band\)\}/);
context.window.OPENBAND_HISTORY=undefined;
assert.equal(context.historyOverviewMarkup({iscBandNumber:'394'}),'','Missing optional history must not break profile rendering');
console.log('Profile history runtime: all profiles, identity checks, duplicate ISC isolation, placement and missing-asset fallback passed');
