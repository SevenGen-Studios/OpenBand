const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const component=require('../assets/nation-name.js');
const provinces=require('../assets/provinces.js');
const bands=JSON.parse(fs.readFileSync('data.json','utf8')).bands;
const source=fs.readFileSync('assets/openband.js','utf8');
const context=vm.createContext({OpenBandNationName:component,ISC_FILING:id=>`https://example.test/?BAND_NUMBER=${id}`});
vm.runInContext(source.split('\n').filter(line=>['function identitySourceUrl(','function identitySourceLabel('].some(prefix=>line.startsWith(prefix))).join('\n'),context);
for(const band of bands){
  const markup=component.markup(band);
  if(band.iscBandNumber){
    assert.match(markup,new RegExp(`>${band.iscBandNumber}</span>`));
    assert.equal(context.identitySourceLabel(band),'ISC profile');
    assert.match(context.identitySourceUrl(band),new RegExp(`BAND_NUMBER=${band.iscBandNumber}$`));
  }else{
    assert.ok(!markup.includes('nation-band-number'));
    assert.equal(context.identitySourceLabel(band),'Community identity source');
    assert.ok(!context.identitySourceUrl(band).includes('BAND_NUMBER='));
  }
}
assert.equal(provinces.matches(bands.find(b=>b.id===399),'399'),true);
assert.equal(bands.filter(b=>provinces.matches(b,'370')).length,3);
assert.equal(component.number({iscBandNumber:7}),'007');
assert.equal(component.number({id:399}),'');
assert.equal(component.number({iscBandNumber:'<399>'}),'');
assert.match(component.markup({name:'A & Company',iscBandNumber:399},'amp'),/A &amp; Company/);
assert.match(component.markup({name:'<Test & Nation>',iscBandNumber:399},'<Test'),/<strong>&lt;Test<\/strong> &amp; Nation&gt;/);
const nodes={pendingTitle:{textContent:''},pendingMsg:{innerHTML:''}};
Object.assign(context,{remFilingsByYear:()=>[],hasRows:()=>false,getFilingStatus:()=>({key:'missing',label:'No filing found'}),getSourceLinks:()=>({profile:'https://www.fsin.ca/sask-fn-listings'}),el:id=>nodes[id]});
vm.runInContext(source.split('\n').find(line=>line.startsWith('function renderPending(')),context);
context.renderPending(null,{name:'Newly listed community'});
assert.match(nodes.pendingMsg.innerHTML,/No source-verified remuneration schedule/);
assert.ok(!nodes.pendingMsg.innerHTML.includes('null'));
console.log('All 186 name displays, numeric search, identity sources, escaping and unknown-number cases passed.');
