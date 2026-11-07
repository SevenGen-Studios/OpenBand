(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let token = '', report = null, selected = null, pdfObject = null, pageObject = null, timer = null;
  $('endpoint').value = window.OPENBAND_FILING_REVIEW_ENDPOINT || `${location.origin}/v1/filing-review`;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function safeUrl(value) { try { const url = new URL(value); return url.protocol === 'https:' ? url.href : ''; } catch { return ''; } }
  const link = (url, label) => safeUrl(url) ? `<a href="${esc(safeUrl(url))}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>` : 'Not documented';
  function message(text) { $('message').textContent = text; }
  async function api(path = '', body) {
    const endpoint = new URL($('endpoint').value);
    if (endpoint.protocol !== 'https:' && !(['127.0.0.1','localhost'].includes(endpoint.hostname) && endpoint.protocol === 'http:')) throw Error('Use HTTPS or a local loopback API.');
    const response = await fetch(endpoint.href.replace(/\/$/, '') + path, {method:body ? 'POST':'GET', headers:{Authorization:`Bearer ${token}`, ...(body ? {'Content-Type':'application/json'} : {})}, ...(body ? {body:JSON.stringify(body)} : {}), cache:'no-store', credentials:'omit', redirect:'error'});
    if (!response.ok) { let error; try {error = await response.json();} catch {} throw Error(error?.error || error?.status || `API returned ${response.status}`); }
    return (path.startsWith('/pdf') || path.startsWith('/page')) ? response.blob() : response.json();
  }
  const run = fn => async event => { event?.preventDefault(); try { await fn(event); } catch (error) { message(error.message); } };
  async function refresh() {
    report = await api(); $('workspace').hidden = false; $('login').hidden = true;
    const labels={totalFirstNationsReviewed:'First Nations reviewed',totalExpectedSlots:'Expected filing slots',filingsAlreadyIndexed:'Filings already indexed',existingValidRecords:'Existing valid records',missingFilingsDiscoveredPublicly:'Missing filings found publicly',newlyVerifiedDocuments:'Newly verified documents',awaitingManualReview:'Documents awaiting review',notPubliclyLocated:'Not publicly located',ocrExtractionFailures:'OCR failures',duplicateDocumentsDetected:'Duplicate documents',searchPending:'Search pending'};
    $('coverage').innerHTML=Object.entries(report.counts).map(([key,value])=>`<article class="portal-card"><p class="coverage-value">${esc(value)}</p><p>${esc(labels[key] || key)}</p></article>`).join('');
    for (const [id,values] of [['province',[...new Set(report.slots.map(s=>s.province))].sort()],['year',report.years]]) {
      const current=$(id).value;$(id).innerHTML=`<option value="">All ${id==='year'?'fiscal years':'provinces'}</option>`+values.map(v=>`<option>${esc(v)}</option>`).join('');$(id).value=current;
    }
    $('progress').textContent=report.lastJobError ? `Batch failed: ${report.lastJobError}` : report.running ? 'Batch running. Completed work is checkpointed.' : 'Queue ready. Discovery and extraction can resume from saved progress.';
    document.querySelectorAll('[data-job]').forEach(b=>b.disabled=report.running);
    renderRows();message(`Coverage updated ${new Date(report.generatedAt).toLocaleString()}.`);
    clearTimeout(timer);if (report.running) timer=setTimeout(()=>refresh().catch(e=>message(e.message)),5000);
  }
  function renderRows() {
    const needle=$('nation').value.toLocaleLowerCase().trim();
    const slots=report.slots.filter(s=>(!$('province').value || s.province===$('province').value) && (!$('year').value || s.fiscalYear===$('year').value) && (!$('status').value || s.status===$('status').value) && (!$('missing').checked || !s.existingValid || s.gaps.length) && (!needle || `${s.name} ${s.bandNumber} ${(s.aliases||[]).join(' ')}`.toLocaleLowerCase().includes(needle)));
    $('resultCount').textContent=`${slots.length} of ${report.slots.length} filing slots`;
    $('rows').innerHTML=slots.map(s=>{
      const docs=s.candidates;const c=docs.find(c=>['approved','imported'].includes(c.state)) || docs.find(c=>c.payload.documentValid) || docs[0];const p=c?.payload || {};
      return `<tr><td>${esc(s.name)}<small>${esc(s.gaps.join(', '))}</small></td><td>${esc(s.bandNumber || 'Identity review')}</td><td>${esc(s.province)}</td><td>${esc(s.fiscalYear)}</td><td>${esc(s.status)}<small>${s.existingValid?'Existing valid index record':s.indexed?'Existing index requires review':'No existing audit index'}</small></td><td>${link(p.sourceUrl || c?.source,'Original source')}</td><td>${esc(p.extractionStatus || c?.state || 'Not started')}<small>${esc(p.extractionMethod || p.message || '')}</small></td><td>${p.confidenceScore===undefined?'Unassessed':esc(p.confidenceScore)+'/100'}</td><td>${esc(p.issues?.length ?? '—')}</td><td>${docs.map(d=>`<button data-review="${esc(d.id)}">Review ${esc(d.state)}</button>`).join(' ')} <button data-search="${esc(s.id)}">Retry search</button><button data-candidate="${esc(s.id)}">Add PDF</button></td></tr>`;
    }).join('');
  }
  async function showReview(id) {
    selected=(await api(`/evidence?id=${encodeURIComponent(id)}`));const c=selected.candidate,p=c.payload;
    const slot=report.slots.find(s=>s.id===c.slot_id);$('reviewTitle').textContent=`${slot?.name || 'Document'} · ${slot?.fiscalYear || ''}`;
    if(pdfObject){URL.revokeObjectURL(pdfObject);pdfObject=null;}
    if(pageObject){URL.revokeObjectURL(pageObject);pageObject=null;}
    $('reviewBody').innerHTML=`<p>${link(p.sourceUrl || c.source,'Original source')} · ${link(p.pdfUrl || c.url,'Public PDF')} · SHA-256: ${esc(c.sha256 || 'Pending')}</p><p>${esc(p.documentType || 'Unverified document')} · Auditor: ${esc(p.auditor || 'Unconfirmed')} · Opinion: ${esc(p.opinion || 'Unconfirmed')} · Year end: ${esc(p.yearEnd || 'Unconfirmed')}</p><p>${esc(p.message || '')}</p><div class="evidence-grid"><div><div class="review-toolbar"><label>Source page<input id="sourcePageNumber" type="number" min="1" value="1"></label><button id="loadPage" type="button">View page</button><button id="downloadPdf" type="button">Download stored PDF</button></div><p id="pageStatus" role="status">Loading original source page…</p><img id="sourcePage" alt="Rendered original PDF source page"></div><div><h3>Extraction comparison</h3><p>Score: 85 for independent agreement with clean evidence; 35 for incomplete evidence; 95 after documented administrator review. OCR confidence alone never establishes correctness.</p><div class="review-table"><table><thead><tr><th>Metric / source</th><th>Primary</th><th>Independent OCR</th><th>Status</th></tr></thead><tbody>${(p.records || []).map(r=>`<tr><td>${esc(r.metric)} ${esc(r.dimension)}<small>${esc(r.statementTitle)} · page ${esc(r.sourcePage)} · ${esc(r.fiscalYear)} · ${esc(r.unit)} ${esc(r.currency)} · ${esc(r.extractionMethod)}</small></td><td>${esc(r.value)}<small>Raw: ${esc(JSON.stringify(r.rawOcrValue))}</small></td><td>${esc((r.secondaryObservations||[]).map(v=>v.value).join(', ') || 'Not extracted')}</td><td>${esc(r.verificationStatus)}</td></tr>`).join('')}</tbody></table></div><details><summary>Financial reconciliation and full figure provenance</summary><pre class="evidence-json">${esc(JSON.stringify({checks:p.checks,records:p.records,unlocatedObservations:p.unlocatedObservations},null,2))}</pre></details></div></div>
    <details><summary>Search attempts and permanent history</summary><pre class="evidence-json">${esc(JSON.stringify({searches:selected.searches,history:selected.history},null,2))}</pre></details>
    <h3>Resolve discrepancies</h3><p>Check each issue against the source. Explain the accounting presentation or the exact original amount, sign, unit and actual-year column. An unreported figure requires a reason; do not substitute zero.</p>
    <form id="approval">${(p.issues||[]).map((issue,i)=>`<div class="issue"><label>${esc(issue)}<input type="number" min="1" max="${p.pages?.length || 300}" id="page${i}" placeholder="Page" required></label><label>Source-based resolution<textarea id="resolve${i}" minlength="12" required></textarea></label></div>`).join('')}<label><input id="confirm" type="checkbox" required> I checked the original source, Nation reporting entity, fiscal year, actual columns, currency, units, important figures and accounting presentation.</label><div class="review-toolbar"><button ${c.state!=='done' || !p.documentValid || !p.records?.length?'disabled':''}>Approve verified record</button><button type="button" id="reject">Reject filing</button><button type="button" id="retry">Retry extraction</button><button type="button" id="import" ${c.state!=='approved'?'disabled':''}>Import approved record</button></div></form><div id="replacement"></div>`;
    if(c.sha256){
      $('downloadPdf').onclick=run(async()=>{const blob=await api(`/pdf?sha=${c.sha256}`);const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`${slot?.bandNumber || 'nation'}-${slot?.fiscalYear || 'audit'}.pdf`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
      $('sourcePageNumber').max=p.pages?.length || 300;
      $('sourcePageNumber').value=p.records?.find(r=>r.sourcePage)?.sourcePage || 1;
      const loadPage=async()=>{const n=Number($('sourcePageNumber').value);$('pageStatus').textContent='Rendering original source page…';const blob=await api(`/page?sha=${c.sha256}&page=${n}`);if(pageObject)URL.revokeObjectURL(pageObject);pageObject=URL.createObjectURL(blob);$('sourcePage').src=pageObject;$('pageStatus').textContent=`Original PDF · page ${n}`;};
      $('loadPage').onclick=run(loadPage);
      loadPage().catch(error=>{$('pageStatus').textContent=error.message;});
    }
    if(c.state==='done' && p.documentValid) {
      const form=document.createElement('form');form.id='figureForm';form.className='review-toolbar';
      form.innerHTML='<h3>Propose a source-checked figure</h3><label>Metric<select name="metric">'+['totalRevenue','totalExpenses','annualSurplusDeficit','totalAssets','totalLiabilities','netFinancialAssetsDebt','accumulatedSurplus','governmentRevenue','cash'].map(m=>'<option>'+m+'</option>').join('')+'</select></label><label>Exact printed amount<input name="raw" required></label><label>Printed units<select name="scale"><option value="1">Dollars</option><option value="1000">Thousands of dollars</option><option value="1000000">Millions of dollars</option></select></label><label>PDF page<input name="page" type="number" min="1" required></label><label>Statement title<input name="title" minlength="8" required></label><label>Source verification explanation<input name="explanation" minlength="12" required></label><button>Save proposed figure</button>';
      $('reviewBody').append(form);
      form.onsubmit=run(async event=>{const data=Object.fromEntries(new FormData(event.target));await api('/figure',{id,...data,page:Number(data.page),scale:Number(data.scale)});await refresh();await showReview(id);});
    }
    $('approval').onsubmit=run(async()=>{
      const resolutions={};(p.issues||[]).forEach((issue,i)=>resolutions[issue]={page:Number($(`page${i}`).value),explanation:$(`resolve${i}`).value});
      await api('/review',{id,action:'approve',evidence:{resolutions,confirmedSourceAndPresentation:$('confirm').checked}});await refresh();await showReview(id);
    });
    for(const action of ['reject','retry'])$(action).onclick=run(async()=>{await api('/review',{id,action});await refresh();await showReview(id);});
    $('import').onclick=run(async()=>{
      const result=await api('/import',{id});
      if(result.status==='replacement_requires_approval'){
        $('replacement').innerHTML=`<h3>Proposed replacement</h3><p>Existing values remain preserved. Review the differences before explicitly approving replacement.</p><pre class="evidence-json">${esc(JSON.stringify(result.differences,null,2))}</pre><button id="replace">Approve replacement and import</button>`;
        $('replace').onclick=run(async()=>{const imported=await api('/import',{id,replaceExisting:true});message(imported.status);await refresh();await showReview(id);});
      } else {await refresh();await showReview(id);}
    });
    if(!$('review').open)$('review').showModal();
  }
  $('login').onsubmit=run(async()=>{token=$('token').value;$('token').value='';await refresh();});
  $('refresh').onclick=run(refresh);
  $('logout').onclick=()=>{token='';report=null;selected=null;clearTimeout(timer);$('workspace').hidden=true;$('login').hidden=false;$('rows').replaceChildren();$('review').close();$('reviewBody').replaceChildren();if(pdfObject)URL.revokeObjectURL(pdfObject);if(pageObject)URL.revokeObjectURL(pageObject);message('Signed out.');};
  $('closeReview').onclick=()=>{$('review').close();if(pdfObject)URL.revokeObjectURL(pdfObject);if(pageObject)URL.revokeObjectURL(pageObject);};
  for(const id of ['province','nation','year','status','missing'])$(id).addEventListener('input',()=>report&&renderRows());
  document.querySelectorAll('[data-job]').forEach(b=>b.onclick=run(async()=>{await api('/jobs',{action:b.dataset.job,years:$('years').value.split(',').map(v=>v.trim()).filter(Boolean),limit:Number($('limit').value)});await refresh();}));
  $('rows').onclick=run(async event=>{
    const b=event.target.closest('button');if(!b)return;
    if(b.dataset.review)return showReview(b.dataset.review);
    if(b.dataset.search){await api('/reset-search',{slotId:b.dataset.search});message('Search reset. Start a public source discovery batch.');}
    if(b.dataset.candidate){
      // A concrete source submission form; never accept an arbitrary unapproved host.
      $('reviewTitle').textContent='Submit a public audited PDF';$('reviewBody').innerHTML='<form id="candidateForm" class="review-toolbar"><label>Public PDF URL<input name="url" type="url" required></label><label>Original source page<input name="source" type="url" required></label><button>Queue PDF for verification</button></form>';
      $('candidateForm').onsubmit=run(async e=>{const data=Object.fromEntries(new FormData(e.target));await api('/candidate',{slotId:b.dataset.candidate,...data});$('review').close();await refresh();});$('review').showModal();
    }
  });
  $('sourceForm').onsubmit=run(async event=>{const data=Object.fromEntries(new FormData(event.target));await api('/sources',{...data,termsReviewed:data.termsReviewed==='on'});message('Source registered. Retry discovery for affected filing slots.');event.target.reset();});
  $('export').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='openband-five-year-filing-coverage.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
})();
