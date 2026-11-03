/* Shared province/search and compatible-year financial calculations. */
(function(root){
  'use strict';
  const names={SK:'Saskatchewan',AB:'Alberta',MB:'Manitoba',BC:'British Columbia',ON:'Ontario',QC:'Quebec',NB:'New Brunswick',NS:'Nova Scotia',PE:'Prince Edward Island',NL:'Newfoundland and Labrador',YT:'Yukon',NT:'Northwest Territories',NU:'Nunavut'};
  const totals={SK:75,AB:48,MB:63};
  const routes={SK:'/saskatchewan/',AB:'/alberta/',MB:'/manitoba/'};
  function normalize(value){return String(value||'').replace(/[łŁ]/g,'l').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim()}
  function matches(band,query){const q=normalize(query);return !q||[band.name,band.officialName,band.id,band.iscBandNumber,...(band.aliases||[])].some(value=>normalize(value).includes(q))}
  function inProvince(band,province){return !province||band.province===province}
  function fromPath(path){const value=String(path||'').toLowerCase();if(/^\/saskatchewan(?:\/|$)/.test(value)||/^\/sk(?:\/|$)/.test(value))return'SK';if(/^\/alberta(?:\/|$)/.test(value)||/^\/ab(?:\/|$)/.test(value))return'AB';if(/^\/manitoba(?:\/|$)/.test(value)||/^\/mb(?:\/|$)/.test(value))return'MB';return''}
  function routeFor(province){return routes[province]||(names[province]?`/browse/?province=${province}`:'/')}
  function summaryFor(capital,band,year){const row=capital?.bands?.[String(band.id)]?.years?.[year];return row&&row.parseStatus==='parsed'&&row.publishable!==false&&!row.sharedFinancialScope?row:null}
  function aggregate(bands,capital,province,year){
    const selected=bands.filter(b=>inProvince(b,province)),fields=['totalRevenue','totalExpenses','annualSurplusDeficit','totalAssets','totalLiabilities','governmentRevenue','ownSourceRevenue'];
    const result={year,tracked:selected.length,expected:totals[province]||null,reporting:0,fields:{}};
    fields.forEach(key=>result.fields[key]={total:null,reporting:0});
    const documents=new Set();
    selected.forEach(band=>{const row=summaryFor(capital,band,year);if(!row)return;const key=row.sha256||row.sourceUrl||String(band.id);if(documents.has(key))return;documents.add(key);result.reporting++;
      fields.forEach(key=>{const value=row[key];if(typeof value!=='number'||!Number.isFinite(value))return;const field=result.fields[key];field.total=(field.total??0)+value;field.reporting++})});
    return result;
  }
  root.OpenBandProvinces={names,totals,routes,normalize,matches,inProvince,fromPath,routeFor,summaryFor,aggregate};
  if(typeof module!=='undefined')module.exports=root.OpenBandProvinces;
})(typeof window!=='undefined'?window:globalThis);
