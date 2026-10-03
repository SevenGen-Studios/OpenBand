const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/openband.js','utf8');
const functions=['remFilings','auditedFilings','auditedFilingsByYear','isManualReview','getFilingStatus','isReliableParsed','filingScore','disclosureYears','remFilingsByYear','bestYear','directoryStatus','capitalYearsForBand','getCapitalSummary','getCapitalAvailableYears','capitalYearStatus','getCapitalParsedYears','getCapitalDisplayYear','capitalYearControlMarkup','renderCommunityCapital'];
const panel={dataset:{},innerHTML:''};
const context=vm.createContext({capitalData:{bands:{}},curCapitalYear:'2025-2026',curYear:null,
    hasRows:f=>Boolean(f?.people?.length),esc:String,escAttr:String,
    el:()=>panel,capitalMemberChip:()=>'',renderCapitalTrendSection:()=>'',
    getSourceLinks:()=>({profile:'https://example.test/filings'}),selectedBand:()=>context.band});
vm.runInContext(source.split('\n').filter(line=>functions.some(name=>line.startsWith(`function ${name}(`))).join('\n'),context);
const posted={year:'2024-2025',docType:'Schedule of Remuneration and Expenses',posted:true,href:'https://example.test/pay.pdf',people:[{name:'Example Chief'}]};
context.band={id:1,province:'AB',filings:[posted,{year:'2024-2025',docType:'Audited financial statements',posted:true,href:'https://example.test/older-audit.pdf'}]};
const snapshot=JSON.stringify(context.band);
const missing=context.remFilingsByYear(context.band).find(f=>f.year==='2025-2026');
assert.equal(context.getFilingStatus(missing).label,'Not posted');
assert.equal(context.getFilingStatus(context.remFilingsByYear(context.band).find(f=>f.year===posted.year)).label,'Parsed');
assert.equal(context.capitalYearStatus(context.band,'2025-2026'),'Not posted');
context.renderCommunityCapital(context.band);
assert.match(panel.innerHTML,/<h3>Not posted<\/h3>/);
assert.doesNotMatch(panel.innerHTML,/older-audit\.pdf/,'A missing year must not link another year’s audit');
assert.equal(JSON.stringify(context.band),snapshot,'Display placeholders must not create source filings');
assert.equal(context.bestYear(context.band),'2024-2025','Opening a profile should still prefer its available data');
assert.equal(context.directoryStatus(context.band).label,'Parsed','A missing latest year must not hide existing parsed coverage');
assert.equal(context.remFilingsByYear({...context.band,province:'SK'}).length,1);
posted.manual_review_required=true;
assert.equal(context.getFilingStatus(context.remFilingsByYear(context.band).find(f=>f.year===posted.year)).label,'Manual review needed');
const bands=JSON.parse(fs.readFileSync('data.json','utf8')).bands.filter(b=>b.province==='AB');
for(const band of bands){
    const years=context.remFilingsByYear(band);
    for(let start=2014;start<new Date().getFullYear();start++)assert(years.some(f=>f.year===`${start}-${start+1}`),band.name);
}
console.log('Missing Alberta years show Not posted while source filings, review flags and Saskatchewan coverage remain intact.');
