/* Integrates provincial controls into the existing static application. */
function selectedProvince(){return document.body.dataset.province||OpenBandProvinces.fromPath(location.pathname)||new URL(location.href).searchParams.get('province')||''}
function provinceBands(){return bandsData.filter(b=>OpenBandProvinces.inProvince(b,selectedProvince()))}
function provinceLabel(){return OpenBandProvinces.names[selectedProvince()]||'First Nations'}
function applyProvinceContext(province){
  const code=['SK','AB'].includes(province)?province:'';
  if(code)document.body.dataset.province=code;else delete document.body.dataset.province;
  document.querySelectorAll('[data-province-link]').forEach(link=>{const active=link.dataset.provinceLink===code;link.classList.toggle('active',active);if(active)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current')});
  const name=OpenBandProvinces.names[code],title=document.getElementById('heroTitle'),intro=document.getElementById('heroIntro'),searchLabel=document.querySelector('label[for="si"]'),hint=document.getElementById('heroHint'),browse=document.getElementById('heroBrowse'),homeBrowse=document.getElementById('homeBrowse'),navHome=document.getElementById('homeLink'),navBrowse=document.querySelector('#primaryNav>a[href^="/browse/"]'),overviewBrowse=document.querySelector('#provinceOverview .text-link'),howLink=document.getElementById('howLink'),homeTitle=document.getElementById('homeIntroTitle'),homeCopy=document.getElementById('homeIntroCopy');
  if(navHome)navHome.href=code?OpenBandProvinces.routeFor(code):'/';
  if(title)title.textContent=name?'First Nations Public Financial Records':'OpenBand';
  if(intro)intro.textContent=name?`Search ${name} First Nations to review public filings, financial records, and original ISC source documents.`:'Choose a province to search First Nations public financial records and original source documents.';
  if(searchLabel)searchLabel.textContent=`Search ${name||'First Nations'}`;
  if(hint)hint.textContent=name?`${name} First Nations · FNFTA public filings · Source: Indigenous Services Canada`:'Public FNFTA records organized by province';
  if(browse){browse.href=code?`/browse/?province=${code}`:'/browse/';browse.textContent=name?`Browse ${name} First Nations`:'Browse all First Nations'}
  if(homeBrowse){homeBrowse.href=code?`/browse/?province=${code}`:'/browse/';homeBrowse.textContent=name?`Browse ${name} First Nations`:'Browse all First Nations'}
  if(navBrowse)navBrowse.href=code?`/browse/?province=${code}`:'/browse/';
  if(overviewBrowse)overviewBrowse.href=code?`/browse/?province=${code}`:'/browse/';
  if(howLink)howLink.href=code?`${OpenBandProvinces.routeFor(code)}#how`:'/#how';
  if(homeTitle)homeTitle.textContent=name?`${name} public records, easier to review`:'Public records, easier to review';
  if(homeCopy)homeCopy.textContent=name?`OpenBand organizes ${name} First Nations FNFTA filings into searchable profiles while keeping original ISC source documents one click away.`:'OpenBand organizes public FNFTA filings into searchable profiles while keeping original source documents one click away.';
}
function updateProvinceUI(){
  const province=selectedProvince(),rows=provinceBands();
  const overviewTitle=document.querySelector('#provinceOverview h2');if(overviewTitle)overviewTitle.textContent=`${provinceLabel()} Coverage`;
  const count=document.getElementById('coverageCount');
  count.textContent=province?`${rows.length} of ${OpenBandProvinces.totals[province]}`:`${rows.length} indexed`;
  document.getElementById('coverageLabel').textContent=` ${provinceLabel()} First Nations tracked`;
  const source=document.getElementById('provinceCountSource');
  source.href=province==='AB'?'https://www.alberta.ca/first-nations-relations':'https://www.saskatchewan.ca/-/media/news-release-backgrounders/2025/jun/lgs-2024-25-annual-report.pdf';
  source.hidden=!province;
  document.getElementById('directoryTitle').textContent=`Explore ${provinceLabel()} First Nations`;
  document.getElementById('albertaCoverageLink').hidden=province==='SK';
  document.getElementById('albertaCoverageLink').innerHTML='<a href="/alberta-coverage-report.html">Alberta source coverage and review report</a>'+(province==='AB'?' · Cross-border community: <a href="/first-nations/onion-lake-cree-nation/">Onion Lake Cree Nation</a> (existing Saskatchewan profile).':'');
  for(const [id,values,label] of [['treatyFilter',rows.map(b=>b.treaty),'All treaties'],['tribalCouncilFilter',rows.map(b=>directoryMapRecord(b)?.tribalCouncil||b.tribalCouncil||'No affiliation listed'),'All affiliations']]){const select=document.getElementById(id),previous=select.value;select.innerHTML=`<option value="">${label}</option>`+[...new Set(values.filter(Boolean))].sort().map(v=>`<option value="${escAttr(v)}">${esc(v)}</option>`).join('');select.value=values.includes(previous)?previous:'';}
}
function renderProvinceFinance(){
  const root=document.getElementById('provinceFinance');if(!root)return;
  const rows=provinceBands();
  const years=[...new Set(rows.flatMap(b=>Object.keys(capitalData.bands?.[String(b.id)]?.years||{})))].sort().reverse();
  const oldYear=document.getElementById('provinceFiscalYear')?.value,latestReported=years.find(y=>rows.some(b=>OpenBandProvinces.summaryFor(capitalData,b,y))),year=years.includes(oldYear)?oldYear:latestReported||years[0];
  if(!year){root.innerHTML='<h2>Financial comparisons</h2><p>No validated financial summaries are available for this selection yet.</p>';return}
  const first=document.getElementById('compareFirst')?.value,second=document.getElementById('compareSecond')?.value;
  const options=rows.map(b=>`<option value="${escAttr(b.id)}">${esc(b.name)}</option>`).join('');
  root.innerHTML=`<div class="section-head"><div><h2>Financial comparisons</h2><p>Reported figures for one fiscal year. Missing values are not zero.</p></div><label>Fiscal year <select id="provinceFiscalYear">${years.map(y=>`<option ${year===y?'selected':''}>${esc(y)}</option>`).join('')}</select></label></div><div id="provinceFinancialTotals"></div><div class="compare-controls"><label>First Nation <select id="compareFirst">${options}</select></label><label>Compare with <select id="compareSecond">${options}</select></label></div><div id="provinceComparison" class="comparison-scroll"></div>`;
  for(const [id,previous,fallback] of [['compareFirst',first,0],['compareSecond',second,1]]){
    const select=document.getElementById(id);select.value=rows.some(b=>String(b.id)===previous)?previous:String(rows[fallback]?.id||rows[0]?.id||'');select.addEventListener('change',renderFinancialComparison);
  }
  document.getElementById('provinceFiscalYear').addEventListener('change',renderFinancialComparison);
  renderFinancialComparison();
}
function renderFinancialComparison(){
  const year=document.getElementById('provinceFiscalYear').value,province=selectedProvince(),summary=OpenBandProvinces.aggregate(bandsData,capitalData,province,year);
  const labels={totalRevenue:'Revenue',totalExpenses:'Expenses',annualSurplusDeficit:'Annual surplus / deficit',totalAssets:'Assets',totalLiabilities:'Liabilities',governmentRevenue:'Identified government revenue',ownSourceRevenue:'Identified own-source revenue'};
  document.getElementById('provinceFinancialTotals').innerHTML=`<p class="note"><strong>Partial reported coverage:</strong> ${summary.reporting} of ${summary.tracked} indexed Nations have validated summaries for ${esc(year)}. Each subtotal covers only the Nations reporting that field; these are not whole-province totals.</p><dl class="province-subtotals">${Object.entries(labels).map(([key,label])=>`<div><dt>${esc(label)}</dt><dd>${summary.fields[key].total===null?'Unavailable':formatMoney(summary.fields[key].total)} <small>(${summary.fields[key].reporting} reporting)</small></dd></div>`).join('')}</dl>`;
  const selected=['compareFirst','compareSecond'].map(id=>bandsData.find(b=>String(b.id)===document.getElementById(id).value));
  document.getElementById('provinceComparison').innerHTML=`<table><caption>Same fiscal year: ${esc(year)}</caption><thead><tr><th scope="col">Reported measure</th>${selected.map(b=>`<th scope="col">${esc(b?.name||'')}</th>`).join('')}</tr></thead><tbody>${Object.entries(labels).map(([key,label])=>`<tr><th scope="row">${esc(label)}</th>${selected.map(b=>{const s=b&&OpenBandProvinces.summaryFor(capitalData,b,year);return`<td>${typeof s?.[key]==='number'?formatMoney(s[key]):'Unavailable / under review'}</td>`}).join('')}</tr>`).join('')}<tr><th scope="row">Audited source</th>${selected.map(b=>{const s=b&&OpenBandProvinces.summaryFor(capitalData,b,year);return`<td>${s?.sourceUrl?`<a href="${escAttr(s.sourceUrl)}" target="_blank" rel="noopener">Original statement</a>`:'No validated summary'}</td>`}).join('')}</tr></tbody></table>`;
}
function nationDetailsMarkup(band){
  if(band.province!=='AB')return'';
  const leadership=band.leadership,officials=leadership?.officials||[],today=new Date().toISOString().slice(0,10);
  const current=officials.filter(p=>{const end=p.expiryDate?.split('/');const start=p.appointmentDate?.split('/');return end?.length===3&&start?.length===3&&`${start[2]}-${start[0]}-${start[1]}`<=today&&`${end[2]}-${end[0]}-${end[1]}`>=today});
  const links=(band.sources||[]).filter(s=>['identity','profile','treaty','reserves','population'].includes(s.field));
  return`<details class="nation-details nation-details-disclosure"><summary><span>Nation profile</span><small>Population, reserves, leadership and source details</small></summary><div class="nation-details-body"><dl class="province-subtotals"><div><dt>ISC band number</dt><dd>${esc(band.iscBandNumber)}</dd></div><div><dt>Province / treaty</dt><dd>Alberta · ${esc(band.treaty||'Unverified')}</dd></div><div><dt>Registered population</dt><dd>${typeof band.population?.registeredMembers==='number'?formatNumber(band.population.registeredMembers):'Unavailable'}</dd></div><div><dt>Registered members on own reserve</dt><dd>${typeof band.population?.onOwnReserve==='number'?formatNumber(band.population.onOwnReserve):'Unavailable'}</dd></div><div><dt>Population reference period</dt><dd>${esc(band.population?.sourcePeriod||'Unavailable')}</dd></div><div><dt>Tribal council</dt><dd>${esc(band.tribalCouncil||'Not verified')}</dd></div><div><dt>Main reserve / most populated site</dt><dd>${esc(band.mainReserve||'Not verified')}</dd></div></dl>${band.identityNote?`<p class="note">${esc(band.identityNote)}</p>`:''}${(band.relatedDisclosureSources||[]).map(s=>`<p><a href="${escAttr(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a> · ${esc(s.scope)}</p>`).join('')}${band.website?`<p><a href="${escAttr(band.website)}" target="_blank" rel="noopener">Official website listed by source</a></p>`:''}${band.reserves?.length?`<details><summary>Reserve names (${band.reserves.length})</summary><ul>${band.reserves.map(r=>`<li>${esc(r.name)}</li>`).join('')}</ul></details>`:''}<p>${links.map(s=>`<a href="${escAttr(s.url)}" target="_blank" rel="noopener">${esc(s.field)} source</a>`).join(' · ')}</p><h3>Current leadership</h3>${current.length?`<p>ISC-listed officials with terms covering today; checked ${esc(leadership.retrievedAt?.slice(0,10))}. These are appointment dates, not verified election dates.</p><ul>${current.map(p=>`<li>${esc(p.position)} ${esc(p.givenName)} ${esc(p.surname)} · ${esc(p.appointmentDate)}–${esc(p.expiryDate)}</li>`).join('')}</ul>`:'<p>No current term-verified leadership is indexed. Historic remuneration records remain separate.</p>'}${leadership?.sourceUrl?`<a href="${escAttr(leadership.sourceUrl)}" target="_blank" rel="noopener">ISC governance source</a>`:''}</div></details>`;
}
function nationBusinessMarkup(band){
  if(band.province!=='AB')return'';
  const rows=(enterpriseData.businesses||[]).filter(b=>(b.owningNationIds||[]).some(id=>String(id)===String(band.id))&&b.verificationStatus==='Verified');
  const sources=new Map((enterpriseData.sources||[]).map(s=>[s.id,s]));
  return `<details class="nation-details nation-business-disclosure"><summary><span>Nation-owned businesses</span><small>${rows.length?`${rows.length} verified listing${rows.length===1?'':'s'}`:'No verified listings indexed'}</small></summary><div class="nation-details-body">${rows.length?rows.map(b=>`<article><h4>${esc(b.name)}</h4><p>${esc(b.industry)} · ${esc(b.description)}</p><p>${b.website?`<a href="${escAttr(b.website)}" target="_blank" rel="noopener">Business website</a> · `:''}${b.sourceIds.map(id=>sources.get(id)).filter(Boolean).map(s=>`<a href="${escAttr(s.url)}" target="_blank" rel="noopener">Ownership source</a>`).join(' · ')}</p></article>`).join(''):'<p>No verified Nation-owned business is indexed yet. This does not mean the Nation has no businesses.</p>'}<p class="note">Ownership does not establish revenue or profit. Business figures are shown only when separately reported and verified.</p></div></details>`;
}
function extendedFinancialMarkup(band){
  if(!band||band.province!=='AB')return'';
  const year=getCapitalDisplayYear(band),summary=OpenBandProvinces.summaryFor(capitalData,band,year);
  if(!summary)return'';
  const sections={
    'Financial position':{cash:'Cash',investments:'Investments',accountsReceivable:'Accounts receivable',restrictedCash:'Restricted cash',otherFinancialAssets:'Other financial assets',tangibleCapitalAssets:'Tangible capital assets',totalAssets:'Total assets',accountsPayable:'Accounts payable',deferredRevenue:'Deferred revenue',longTermDebt:'Long-term debt',otherLiabilities:'Other liabilities',totalLiabilities:'Total liabilities',accumulatedSurplus:'Accumulated surplus / deficit',netFinancialAssetsDebt:'Net financial assets / debt'},
    'Identified revenue':{iscRevenue:'ISC revenue',federalGovernmentRevenue:'Federal revenue (includes ISC)',albertaGovernmentRevenue:'Alberta government revenue',otherGovernmentRevenue:'Other government revenue',taxationRevenue:'Taxation revenue',businessRevenue:'Business revenue',rentalLeaseRevenue:'Rental / lease revenue',investmentIncome:'Investment income',ownSourceRevenue:'Identified own-source revenue',otherRevenue:'Other revenue'},
    'Cash flows':{operatingCashFlow:'Operating cash flow',investingCashFlow:'Investing cash flow',financingCashFlow:'Financing cash flow',capitalAssetPurchases:'Capital asset purchases',debtRepayments:'Debt repayments'}
  };
  return `<section class="nation-details"><h3>Additional reported figures · ${esc(year)}</h3><p>Explicit source labels only. Unavailable fields have not been reliably extracted. Revenue categories can overlap; do not add federal revenue to ISC revenue or own-source revenue to its components.</p>${Object.entries(sections).map(([heading,fields])=>`<details><summary>${esc(heading)}</summary><dl class="province-subtotals">${Object.entries(fields).map(([key,label])=>`<div><dt>${esc(label)}</dt><dd>${typeof summary[key]==='number'?formatMoney(summary[key]):'Unavailable'}</dd></div>`).join('')}</dl></details>`).join('')}<p><a href="${escAttr(summary.sourceUrl)}" target="_blank" rel="noopener">Original audited statement</a></p></section>`;
}
