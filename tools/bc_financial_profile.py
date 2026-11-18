"""Original document index for static BC profiles; amounts use shared views."""
from html import escape as esc
from tools.ingest_bc import INDEX,read,YEARS
from functools import lru_cache
@lru_cache(maxsize=1)
def source_index(modified):return read(INDEX,{'governments':{}})['governments']
def financial_sources_markup(band):
 row=source_index(INDEX.stat().st_mtime_ns if INDEX.exists() else None).get(str(band['id']))
 if not row:return '<section class="nation-details"><h3>Financial sources</h3><p>Not assessed. No financial values are inferred.</p></section>'
 filings=row.get('filings',[]);published={f['href']:f for f in band.get('filings',[])}
 text='<section class="nation-details"><h3>Financial sources</h3><p>Original public documents, 2014–15 through 2025–26. Unprocessed documents contain no verified figures here. Missing values are not zero.</p><p><a href="/bc-financial-coverage-report.md">BC coverage and review report</a></p>'
 if filings:
  text+='<details><summary>Available documents ('+str(len(filings))+')</summary><ul>'
  for f in sorted(filings,key=lambda f:f['year'],reverse=True):
   status='Validated' if f['href'] in published else {'manual_review_needed':'Manual review needed','available_pending_approval':'Validated candidate, pending approval'}.get(f.get('status'),'Available, pending extraction and approval')
   text+=f'<li>{esc(f["year"])} · <a href="{esc(f["href"],quote=True)}">{esc(f["docType"])}</a> · {status} · {esc(f["reportingEntity"])}</li>'
  text+='</ul></details>'
 checked=any(c['status']=='checked' and 'FederalFundingMain' in c['url'] for c in row['checks'])
 for y in YEARS[::-1]:
  if not any(f['year']==y for f in filings):text+=f'<p>{y}: '+('Not found in checked ISC listing; other official sources may contain records.' if checked else 'Not assessed against an accessible ISC listing. See official-site source checks.')+'</p>'
 for c in row['checks']:
  text+=f'<p><a href="{esc(c["url"],quote=True)}">Source checked</a> · {esc(c["status"].replace("_"," "))} · {esc(c["retrievedAt"][:10])}</p>'
  for f in c.get('documentCandidates',[]):text+=f'<p><a href="{esc(f["url"],quote=True)}">{esc(f["label"] or "Official PDF candidate")}</a> · Reporting entity, type and period need review.</p>'
 return text+'<p class="note">Search coverage is bounded. An unavailable website or absent listing does not establish that a government has not published financial records. Historic remuneration recipients are separate from current leadership.</p></section>'
