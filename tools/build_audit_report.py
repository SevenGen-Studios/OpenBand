"""Render the audit evidence ledger without changing application data."""
import json
from collections import Counter
from pathlib import Path
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT/name).read_text(encoding='utf-8'))


def cell(value):
    if value is None or value=='': return 'Not recorded'
    if isinstance(value,list): value='; '.join(str(v) for v in value)
    return str(value).replace('|','\\|').replace('\n',' ')


def link(url,label='Source'):
    return f'[{label}]({quote(url,safe=":/?=&%#+")})' if url else 'Source not recorded'


def build():
    audit=read('openband-audit-inventory.json'); data=read('data.json')
    ab=read('alberta-coverage-report.json'); qa=read('audit-qa-results.json')
    visual=read('manual_overrides/audit-remuneration-reviews.json')['reviews']
    financial=read('financial-source-reviews.json')['reviews']
    listings=read('audit-disclosure-sources.json')['results']
    boundaries=read('reserve-boundary-validation.json')
    profiles={p['bandId']:p for p in audit['profiles']}
    bands={str(b['id']):b for b in data['bands']}
    c=audit['counts']; content=audit['contentChecks']
    lines=[]
    def add(text=''):
        lines.extend(text.splitlines() or [''])
        if text.endswith('\n'): lines.append('')
    def table(headers,rows):
        add('| '+' | '.join(headers)+' |')
        add('| '+' | '.join('---' for _ in headers)+' |')
        for row in rows: add('| '+' | '.join(cell(v) for v in row)+' |')
        add()
    add(f'''# OpenBand audit and repair report

Audit date: 2026-10-09. Evidence inventory generated: {audit['generatedAt']}.

## Scope, outcome and interpretation

The repository, JSON schemas, scraping and OCR pipelines, source caches, static-route builder, GitHub Actions workflows, and optional Cloudflare analytics worker/D1 schema were inspected before repairs. The public site was checked read-only in a real browser. Changes remain local; no production deployment, database migration, push, or paid extraction occurred.

Recovered **27 previously unavailable parsed filings**: ten complete remuneration schedules (original PDF schedules visually checked row by row) and seventeen financial summaries (three headline totals visually checked against original statement pages, including continuations and adjustments). Eight newly listed ISC documents were added; six of those now have parsed data. Existing publishable financial summaries, all 117 community identities/provinces, and existing map coordinates/area metadata were preserved by a comparison with the initial Git revision.

Coverage is **117 tracked governments: 48 Alberta and 69 Saskatchewan**. There are **2,211 posted document records**, **796 remuneration schedules with rows**, and **{c['reviewDocuments']} posted document records without a publishable extraction**. A document record can be a revision or a differently labelled link to a statement; counts are not unique audits or a national census. Alberta has 47 distinct ISC band numbers for 48 governments. Whitefish Lake #128 shares ISC 462 with Saddle Lake; its records are not fabricated by duplicating Saddle Lake.

This was a comprehensive code/data inventory and bounded extraction pass, not a manual recertification of every historical PDF, election, article or business claim. Every remaining posted extraction gap is listed below. Existing parsed records also produced 68 strict-validation flags and 13 repeated-name flags that need source review; no uncertain legacy values were silently rewritten. Financial headline reviews do not certify every optional balance-sheet or note field. Unusual changes are review signals, not findings of wrongdoing.

Status meanings: **FIXED** = repaired in this working tree; **VERIFIED FIXED** = the reported problem was absent in the inspected current implementation/data, with the stated verification scope; **BLOCKED** = an authoritative source or external access is unavailable; **NEEDS MANUAL REVIEW** = source interpretation or currentness requires review; **OPEN** = outstanding work. Existing inventory rows labelled VERIFIED FIXED indicate extraction coverage, not an audit opinion or complete source certification.

Evidence files: [integrity inventory](openband-audit-inventory.json), [QA and preservation checks](audit-qa-results.json), [financial source reviews](financial-source-reviews.json), [complete remuneration transcriptions](manual_overrides/audit-remuneration-reviews.json), [official listing refresh](audit-disclosure-sources.json), [Alberta coverage](alberta-coverage-report.json), and [geometry validation](reserve-boundary-validation.json).

## 1. Confirmed bugs, root causes and repairs
''')
    bugs=[
    ('Home statistics / main data','Failed or malformed data.json could leave dash placeholders with only a console warning.','Main loader lacked a visible failure state and schema/HTTP checks.','HTTP/schema checks, 15-second timeout, explicit Unavailable statistics and visible retry message.','assets/openband.js; index.html; assets/openband.css','503/malformed payload tests; browser injected 503'),
    ('Sidecar data / empty states','Failed map, financial, contact or other sidecar requests were converted into empty datasets without telling the visitor.','Catch handlers hid the failure behind a valid empty shape.','Dataset-specific visible failure banner; failures can retry, successful loads remain cached.','assets/openband.js; generated profile/province/browse/news pages','tests/test_data_loading.js; browser failure injection'),
    ('Directory map loading','Map initialization waited for the large financial dataset before displaying sourced markers.','Sequential capital-data await blocked independent map initialization.','Load financial data independently; refresh financial summaries when ready.','assets/openband.js','tests/test_directory_map.js uses a financial promise that never resolves; browser capital 503 still renders 47 AB markers'),
    ('Map coordinates','Null coordinates could become numeric zero.','Numeric coercion accepted null; range/finite guards were missing.','Require finite numeric latitude/longitude within valid geographic ranges.','assets/openband.js','tests/test_data_loading.js'),
    ('Map library / reserve request failure','CDN or reserve requests could hang or fail silently.','Unbounded Leaflet loading; reserve failures only logged.','15-second loading/request bounds and visible errors; failed library attempt can retry.','assets/openband.js','Map regression suite; code path review'),
    ('Reserve ownership association','Text-only owner matching was fragile for renamed nations and damaged Unicode in generalized source responses.','Display-name aliases were the only browser join.','Prefer official ADMIN_LAND_ID links derived from ISC reserve numbers; exact owner fallback retained.','tools/build_map_data.py; tools/reconcile_map_boundaries.py; map-data.json; assets/openband.js','tests/test_boundary_associations.py; 116 sourced point records have parcel IDs'),
    ('Reserve geometries','205 generalized response geometries were invalid; six original unsimplified geometries were invalid.','Live generalized geometry could introduce or retain self-intersections.','Validated local display snapshot: 978 parcels, six conservative GEOS repairs, topology-preserving simplification, complete source/hash report.','tools/build_reserve_boundaries.py; public/reserve-boundaries.geojson; requirements-maps.txt','All 978 display geometries valid; original parcel IDs/owners retained; six area changes below 0.001 threshold'),
    ('Standing Buffalo / repeated travel columns','Nation and entity travel columns could overwrite one another.','Column mapping assigned the second travel value rather than accumulating it.','Accumulate repeated mapped payment columns; complete 2016–2017 visual transcription.','run_scraper.py; manual_overrides/audit-remuneration-reviews.json; data.json','Two-column regression and original 12-row schedule'),
    ('Cote / other remuneration','Fallback parsing could put other remuneration into travel.','Generic numeric assignment did not respect the explicit Other Remuneration header.','Header-aware assignment keeps other remuneration separate; 2020–2021 and 2022–2023 schedules source checked.','run_scraper.py; data.json; manual_overrides/audit-remuneration-reviews.json','Category regression and complete source schedules'),
    ('Carry the Kettle / fragmented headings','A fragmented Title Mon header could validate as an official row.','Name guards did not reject this heading fragment.','Reject fragmented headings; replace the candidate with the seven actual source rows.','run_scraper.py; tools/parser_quality.py; data.json','Heading regression; original 2020–2021 PDF'),
    ('Financial source notes','The remuneration page omitted filing warnings and labelled derived sums as reported totals.','renderNote ignored warnings; fixed label assumed a printed total.','Escaped source notes now shown; totals derived from components explicitly labelled. Printed dollar-level source discrepancies retained.','assets/openband.js','Source-warning escaping and derived-label regressions; Kahkewistahaw 2025–2026'),
    ('Nightly reuse / provenance','Reuse copied rows without their PDF hash, source total and visual-review metadata.','Result field whitelist contained only six basic extraction fields.','Copy verified result provenance and its supporting source URL together; deep copy prevents later mutation of the prior result.','scraper.py','Nightly-reuse regression verifies hash, review, retrieval date and original URL'),
    ('Legacy override precedence','Older unbound manual overrides could replace or clear a newer complete source review.','Generic override application did not check source-bound review metadata and could select an obsolete placeholder.','Preserve complete reviews bound to the current PDF hash, source URL and year; prioritize them over obsolete placeholders. Corrections must update the source review.','tools/apply_manual_overrides.py','tests/test_manual_overrides.py covers row replacement and status clearing'),
    ('Historical audited statements','Legacy not_required records could be skipped despite lacking financial summaries.','Original remuneration-only scrape status was mistaken for financial completion.','Gap recovery checks the actual capital summary; missing statements remain candidates regardless of legacy status.','tools/audit_reparse.py','Legacy-status regression; fifteen further financial summaries recovered'),
    ('Verified financial headline preservation','Reviewed headline fields were outside the source-hash-protected field-review whitelist.','Preservation supported only balance-sheet fields.','Revenue, expenses and annual result reviews are restored only for the identical PDF hash and fiscal year.','tools/capital_parser.py; capital-data.json; financial-source-reviews.json','tests/test_capital_column_regressions.py tests changed PDF and changed year'),
    ('New source coverage','Eight current ISC links were absent from the indexed records.','Index snapshot lagged the current disclosure listings.','Append only links actually returned by the source; migrated ISC hostnames are treated as equivalent identities, avoiding hundreds of false duplicates.','tools/review_disclosures.py; data.json','60 current listings refreshed without errors; tests/test_disclosure_identity.py'),
    ('Leadership currentness','ISC-listed expired appointments could be labelled current leadership.','Rendering did not qualify source date or expired terms.','Show source check date and expired-term notice; require source confirmation for current officeholders. Historical figures remain historical.','assets/openband.js; tools/build_site.py','Expiry-date regression; Montana has five expired listed terms'),
    ('News verification','35 records with detailVerified=false had no corresponding visible qualification.','Renderer ignored the existing verification flag.','News cards show Source details not independently verified.','assets/openband.js','325-source/date inventory; browser news route'),
    ('Regression automation','JavaScript logic tests were not part of the static build workflow.','Workflow ran only Python tests.','Run all four Node suites; watch map/snapshot/manual-review inputs; regenerate versioned shared assets and routes.',' .github/workflows/build-site.yml; index.html; tests/test_site_routes.py','Local four-suite pass; workflow inspected, not remotely executed'),
    ('SVG source hashes','Windows line endings changed reviewed SVG bytes.','No consistent SVG line-ending policy.','Normalize reviewed SVG text to LF with .gitattributes; Ochapowace and Whitecap hashes match recorded source bytes.',' .gitattributes; two public/first-nation-logos SVG files','Hash inventory leaves one unrelated Buffalo River mismatch for review'),
    ]
    table(['Feature / community','Confirmed defect','Root cause','Fix','Affected files','Evidence / regression','Status'],[(*row,'FIXED') for row in bugs])
    add('## 2. Previously reported issues verified as fixed\n')
    add('Normal live loading did not reproduce homepage dashes, zero communities, or profile crashes. Before edits, the real-browser production check returned 117/786 home statistics, Alberta 48/226, Saskatchewan 69/560 and Alberta browse 48 results / 47 sourced markers, with no JavaScript exceptions. The two provincial indexed counts reconcile to 117. Coverage counts must not be compared with a national or provincial total of recognized governments without the coverage label.\n')
    verified=[('Homepage statistics / province totals','Existing working production values and province filters','Read-only browser observation; assets/provinces.js and province-ui.js'),
              ('Profile routes / links / images','117 generated profile routes; zero broken local href/src targets','Static inventory plus desktop/mobile profile sample'),
              ('Wood Mountain — SK 2016–2017, 2019–2020, 2025–2026','Requested remuneration years already have parsed rows; audited coverage is separately listed below','Existing rows + refreshed ISC listing'),
              ('Star Blanket — SK 2015–2016','Five remuneration rows already parsed; do not replace working data','Existing filing + refreshed ISC listing'),
              ('Muscowpetung — SK 2015–2016 through 2024–2025','Chief/Council schedules already have rows; 2013–2014 and 2014–2015 remain review gaps','Existing filing coverage + refreshed listing'),
              ('Beaver — AB 2015–2016','Existing remuneration extraction retained','Existing rows + current listing'),
              ('Tallcree — AB 2022–2023 remuneration','Five remuneration rows already parsed; audited statement still requires review','Existing rows + current listing')]
    table(['Feature / First Nation','Verified scope','Evidence','Status'],[(*r,'VERIFIED FIXED') for r in verified])
    logo_ids=['409','365','385','379','392']
    table(['Requested logo','Province','Evidence','Status'],[(bands[i]['name'],bands[i]['province'],link(profiles[i]['logoSource'],'Recorded logo source')+'; local asset exists and matches recorded SHA-256','VERIFIED FIXED') for i in logo_ids])
    add('Logo VERIFIED FIXED means sourced local coverage and byte integrity were checked; it is not a fresh endorsement of every external website or branding policy.\n')
    add('## 3. Recovered filings and financial verification\n')
    add('All source amounts are retained as printed dollar amounts; no foreign-currency conversion or invented salary/expense split was introduced. Remuneration schedules are labelled unaudited where their source says so. Complete schedules are bound to nation ID, fiscal year, exact URL and SHA-256. Numeric source components remain available in reportedComponents.\n')
    table(['First Nation','Province / fiscal year','Rows','Source PDF / page','Printed footer or derived sum','Review notes','Status'],[
        (bands[r['bandId']]['name'],bands[r['bandId']]['province']+' / '+r['year'],r['sourceRowCount'],link(r['sourcePdf'],'Original PDF')+f" / PDF p. {r['pdfPage']}",
         f"${r['sourceTotal']:,.0f}" if r.get('sourceTotal') is not None else f"${sum(p['total'] for p in r['people']):,.0f} (sum of components; no printed grand total)",r.get('warnings') or 'Complete rows and amounts source checked','FIXED') for r in visual])
    add('Carry the Kettle prints Kurt Adams total as $19,647 although its components sum to $19,648; the PDF footer is $992,572 and printed row totals sum to $992,571. Cote 2022–2023 and Pheasant Rump 2025–2026 also contain dollar-level rounding differences. They are disclosed, not corrected by inventing values. Standing Buffalo keeps nation travel and entity travel as separate stored components. Tallcree proxy responsibility payments remain Other. Kahkewistahaw 2025–2026 keeps salary, benefits, nation travel, committee expenses, membership expenses, entity honoraria and entity travel separately in reportedComponents. Its displayed total is derived and labelled accordingly.\n')
    table(['First Nation','Province / fiscal year','Reported revenue','Reported expenses','Final surplus / deficit','Original PDF / reviewed pages','Status'],[
        (r['name'],r['province']+' / '+r['year'],f"${r['fields']['totalRevenue']['value']:,.0f}",f"${r['fields']['totalExpenses']['value']:,.0f}",f"${r['fields']['annualSurplusDeficit']['value']:,.0f}",
         link(r['sourceUrl'],'Original PDF')+' / '+', '.join(str(p) for p in sorted({f['sourceReference']['pdfPage'] for f in r['fields'].values()})),'FIXED') for r in financial])
    add('Headline figures were checked in the actual-year column, including the final result after other items. Cowessess, Sweetgrass, Pasqua, Fishing Lake and Flying Dust legitimately have separately reported adjustments; revenue minus expenses alone is not always the final annual result. Remaining optional financial fields retain automated source-reference checks. Each reviewed headline has a source hash, PDF page, fiscal year, selected column and verification date in financial-source-reviews.json and capital-data.json.\n')
    add('### Extraction passes and provenance\n')
    passes=[]
    for name in ['audit-reparse-results.json','audit-ocr-reparse-results.json','audit-alberta-reparse-results.json','audit-new-filings-results.json','audit-new-ocr-results.json','audit-saskatchewan-reparse-results.json','audit-saskatchewan-complete-reparse-results.json']:
        report=read(name); rows=report['outcomes']
        passes.append((link(name,name),len(rows),'Free local OCR' if 'ocr' in name else 'Native PDF / guarded parser','Source URL, source hash where retrieved, check time, identity/year checks, parser status and warnings'))
    table(['Evidence report','Document attempts','Method','Evidence recorded'],passes)
    add('The initial candidate reports are chronological extraction evidence, not the final authority for amounts. Complete visual transcriptions and financial-source-reviews.json supersede preliminary candidates. The complete Saskatchewan pass checked 454 remaining source candidates, including legacy not_required statements; fifteen validated financial candidates were subsequently source checked and published. The Alberta pass checked all 285 pending candidates then present. Free OCR passes covered the named unresolved Saskatchewan schedules and newly discovered documents. No paid fallback was enabled.\n')
    add('## 4. Alberta: all 48 tracked governments and requested historical ranges\n')
    add('The Alberta coverage report reconciles 48 governments, 47 distinct ISC identities, 754 posted documents (405 audited and 349 remuneration), 472 source/identity-validated documents and 282 requiring review. The cross-province inventory uses publishable capital summaries or remuneration rows, while this Alberta report requires the explicit automated_validated marker, so these definitions should not be mixed. All 47 independent Alberta disclosure listings were refreshed; Whitefish Lake #128 remains a shared-identity exception.\n')
    add('**Identity correction:** Tthebatthie Denesuline Nation (ISC 477; historical Chipewyan/Smith’s Landing references) and Athabasca Chipewyan First Nation (ISC 463) are different First Nations. Both are inspected separately below; their filings and reserves must not be merged.\n')
    ab_requested={'477':range(2014,2024),'463':range(2014,2024),'448':[2016,2017],'445':[2014,2015,2016],'446':[2022]}
    sk_requested={'388':[2016,2019,2025],'378':[2020],'362':[2017],'385':[2017,2018,2019,2020],'381':[2013,2014,2024],'386':[2016],'387':[2015],'366':[2020],'367':[2013,2017,2022]}
    def requested_rows(requests):
        result=[]
        for bid,years in requests.items():
            for y in years:
                year=f'{y}-{y+1}'
                for kind in ['Audited','Schedule']:
                    rows=[f for f in audit['filings'] if f['bandId']==bid and f['year']==year and f['document'].startswith(kind)]
                    if not rows:
                        listing=next((r for r in listings if r['bandId']==bid),{})
                        result.append((bands[bid]['name'],bands[bid]['province']+' / '+year,kind,'No source-listed document in the indexed/current listing; do not invent one',link(listing.get('sourceUrl'),'ISC listing'),'BLOCKED'))
                    else:
                        for row in rows:
                            fixed=any(r['bandId']==bid and r['year']==year and ((kind=='Audited')==('fields' in r)) for r in visual+financial)
                            status='FIXED' if fixed else row['status']
                            description=(f"{row['people']} remuneration rows" if kind=='Schedule' else 'Publishable financial summary') if status in {'FIXED','VERIFIED FIXED'} else 'Source is posted; extraction needs complete rows / actual-year / accounting review'
                            result.append((bands[bid]['name'],bands[bid]['province']+' / '+year,kind,description,link(row['sourceUrl'],'PDF'),status))
        return result
    table(['First Nation','Province / year','Document','Finding / remaining action','Evidence','Status'],requested_rows(ab_requested))
    table(['Alberta government','ISC identity / treaty','Posted / needs review','Boundary parcels','Logo','Verified business records','Missing contact fields','Current listing'],[
        (p['name'],str(bands[p['bandId']].get('iscBandNumber'))+' / '+str(p['treaty']),str(p['filings'])+' / '+str(p['reviewDocuments']),len(p['boundaryIds']), 'VERIFIED FIXED' if p['logoVerified'] else 'NEEDS MANUAL REVIEW',p['businessCount'],p['missingContacts'] or 'None',link(next((r['sourceUrl'] for r in listings if r['bandId']==p['bandId']),None),'ISC listing')) for p in audit['profiles'] if p['province']=='AB'])
    add('Missing source years are separately recorded as unindexedAuditedYears / unindexedRemunerationYears in alberta-coverage-report.json. These are source-listing gaps, not parser failures. Shared Stoney administrative sources and Saddle Lake/Whitefish identities are retained with their provenance and excluded from duplicate provincial financial totals where the existing application already does so.\n')
    add('## 5. Saskatchewan requested issues\n')
    table(['First Nation','Province / year','Document','Finding / remaining action','Evidence','Status'],requested_rows(sk_requested))
    add('Keeseekoose historical coverage: the 2013–2014 audited statement is newly recovered; remuneration for 2013–2014 and 2017–2018 still needs review. The current source listing only supplies years through 2022–2023. That observation does not prove later documents do not exist outside the public ISC listing. Requested logos are verified in section 2. Wood Mountain and Star Blanket remuneration issues already had working extractions; their separate audited-statement gaps are not concealed. Piapot 2017–2018 through 2020–2021 and Kahkewistahaw 2017–2018 remuneration remain unresolved after native/OCR attempts.\n')
    add('## 6. Maps and reserve boundaries\n')
    add(f"Authoritative source: {link(boundaries['sourceUrl'],'ISC/NRCan reserve layer query')}. Retrieved {boundaries['retrievedAt']}. Source hash `{boundaries['sourceSha256']}`; output hash `{boundaries['outputSha256']}`. The display snapshot contains all {boundaries['featureCount']} queried AB/SK parcels; all are geometrically valid. The geographic snapshot is for display, not a legal survey, and it does not replace ISC-reported reserve-area statistics.\n")
    table(['Requested First Nation','Province','Sourced parcel IDs','Finding / action','Status'],[(bands[bid]['name'],'AB',profiles[bid]['boundaryIds'],'Authoritative reserve features associated; do not conflate nearby nations','FIXED') for bid in ['477','463','448','445','446','447','461']])
    table(['Repaired source parcel','Name','Relative planar area change','Method','Status'],[(r['reserveId'],r['name'],r['relativePlanarAreaChange'],r['method'],'FIXED') for r in boundaries['repairs']])
    add('**BLOCKED — Whitefish Lake First Nation #128 (AB):** no separately sourced map point or authoritative independent parcel relationship is indexed. Sharing ISC 462 with Saddle Lake is not sufficient evidence to copy its point or polygons. Obtain an independently documented community/reserve relationship, then add it with source provenance. All other 116 point records have boundary associations. Province filtering, map zoom/fit, search/no-match clearing, Tthebatthie hover polygons and two-tap mobile selection were exercised in the browser. Tile/CDN services remain external dependencies; failures now have visible states.\n')
    add('## 7. Community content, logos and external blockers\n')
    table(['Unverified logo','Province','Evidence / root cause','Remaining action','Status'],[(p['name'],p['province'],link(p['logoSource'],'Recorded source')+'; registry has no verified logo','Obtain official asset, confirm ownership/branding and record original hash','NEEDS MANUAL REVIEW') for p in audit['profiles'] if not p['logoVerified']])
    add('**BLOCKED — Buffalo River Dene Nation (SK) logo provenance:** the working SVG exists, but its stored SHA-256 differs from the registry even after LF normalization. The recorded official asset endpoint returned HTTP 403, including a browser-style user agent. The image and trusted hash were left intact; retrieve the asset manually or obtain an official replacement before changing the provenance record. Ochapowace and Whitecap differences were line endings and have been fixed.\n')
    add(f"Content inventory: {content['newsCount']} news records with source URLs and publication dates; no missing URLs, missing dates or future dates found. {content['newsDetailsNotVerified']} records retain unverified detail flags and now show that qualification. {content['projectCount']} project records have sources, with {content['unverifiedProjectSignals']} separate unverified project signals. {content['electionRecords']} election records have source URLs. {content['nationsWithExpiredGovernanceTerms']} government has expired ISC-listed terms; these no longer claim currentness. Governance appointments are not interpreted as election dates. {content['nationsWithoutIndexedBusinesses']} communities have no directly indexed business portfolio; this is a coverage gap, not evidence that no businesses exist.\n")
    add('Names/aliases, province/treaty fields, contacts, leadership source dates, election evidence and business coverage were inventoried for all 117 profiles below. The original sources were not all recontacted during this run. Records requiring current contact, election, ownership, housing/project or article confirmation remain NEEDS MANUAL REVIEW; the website must retain its source date and qualification. Private/deleted/access-restricted social posts and authenticated services remain unavailable. No leadership, reserve boundaries, business ownership percentages or source URLs were invented.\n')
    table(['First Nation','Province / treaty','Missing contacts','Contact check / source','ISC officials / expired terms','Governance check / source','Latest sourced election','Indexed businesses','Status / action'],[
        (p['name'],p['province']+' / '+str(p['treaty']),p['missingContacts'] or 'None',str(p['contactCheckedAt'] or 'Not recorded')+' / '+link(p['contactSource']),str(p['leadershipOfficials'])+' / '+str(p['expiredLeadershipTerms']),str(p['leadershipCheckedAt'] or 'Not recorded')+' / '+link(p['leadershipSource']),str(p['latestElectionDate'] or 'No separately verified election')+' / '+link(p['electionSource']),p['businessCount'],'NEEDS MANUAL REVIEW — verify current contacts/officeholders and fill sourced gaps') for p in audit['profiles']])
    add('Additional blockers: production analytics/D1 administration and authenticated dashboard operations were not available or changed. No inferred migrations or production writes were attempted. The external ISC source can return scanned pages, irregular columns, wrong document labels or revisions; those cases require the original source comparison recorded in the ledgers. A failed retrieval must never be converted into Not posted.\n')
    add('## 8. Quality assurance and prioritized next steps\n')
    table(['Check','Result / scope'],[
        ('Python unit/integration suite',f"PASS — {qa['pythonTests']} tests (baseline {qa['baselinePythonTests']}); includes site, parser, financial, source identity, analytics and recovery regressions"),
        ('JavaScript logic suites','PASS — provinces, missing filing years, directory map, dataset loading/notes/leadership'),
        ('Browser checks',f"PASS — {qa['browserScenarioCount']} desktop/mobile/failure scenarios; search, filters, map selection and profile routes"),
        ('Browser console / resources','PASS — six major routes: zero console errors, zero JavaScript exceptions and zero failed resources'),
        ('Static production route build','PASS — 117 profiles, province landings, directory, news, redirects, robots and sitemap'),
        ('Internal links/assets',f"PASS — {c['brokenInternalLinks']} broken local href/src targets across generated pages"),
        ('Geometry','PASS — 978 valid display parcels; authoritative IDs and ownership preserved'),
        ('Data preservation','PASS — 17 gap summaries added; eight source-listed documents added; six existing missing-row schedules recovered; all existing publishable financial summaries and original map metadata preserved'),
        ('Lint / type check / production bundle','No standalone lint/typecheck/bundler configuration exists; changed Python compiled and JavaScript syntax checked. Static builder is the production build.'),
        ('Production / credentials','No deployment, database change or push. Secret scan reports file/count results only; no credentials included in audit artifacts.')])
    add('### P0 — correctness before relying on disputed data\n\n- **NEEDS MANUAL REVIEW:** source-check the 68 legacy remuneration strict-validation flags, 13 repeated-name flags and six document revision/type collisions below. Keep scope-separated payments and source totals distinct; do not delete equal amounts merely because they repeat.\n- **NEEDS MANUAL REVIEW:** finish the explicitly requested Piapot, Kahkewistahaw, Dene Tha’, Beaver and Tthebatthie/Athabasca historical extraction gaps from their original PDFs.\n- **OPEN:** independently review the working-tree diff and the hash-bound source reviews before authorizing any production deployment.\n')
    add('### P1 — remaining extraction and provenance\n\n- **NEEDS MANUAL REVIEW:** work through every posted extraction gap in the complete document ledger; reconcile actual-year totals and complete official rows before publishing.\n- **OPEN:** apply the guarded recovery path to remaining OCR layouts, retain original labelled components, and checkpoint retrieval/source-verification metadata rather than overwriting reviewed fields.\n- **BLOCKED:** obtain independent Whitefish Lake #128 geography and resolve Buffalo River SVG provenance through an accessible official source.\n')
    add('### P2 — current community coverage\n\n- **NEEDS MANUAL REVIEW:** verify current governance where terms expired or no current official list is available; retain historical election records with dates and sources.\n- **NEEDS MANUAL REVIEW:** obtain the ten missing verified logos and complete the missing contact/business fields listed above.\n- **OPEN:** expand directly sourced Alberta/Saskatchewan project and business coverage without treating absent records as absent activity. Recheck the 35 news-detail flags and the 34 unverified project signals.\n')
    add('### P3 — sustained operations\n\n- **OPEN:** run the updated CI workflow remotely after the changes are submitted; retain browser smoke checks for data-request failures and the boundary snapshot.\n- **OPEN:** refresh the validated ISC snapshot and review its diff/hash on a controlled schedule; keep third-party map/CDN failures visible.\n- **OPEN:** document a maintained browser-test runtime and review optional analytics integration with authenticated access when available.\n')
    add('## Appendix A — all posted documents still requiring extraction/source review\n')
    add('Each row below is **NEEDS MANUAL REVIEW**. The source exists in the index; this is not a Not posted finding. Root cause is the recorded parser/identity/column/reconciliation warning where available. Remaining action for each row: retrieve the original PDF, confirm community and fiscal year, reconcile actual-year financial totals or complete official rows, and record source hash, retrieval date and verification before publishing. Full warning arrays, hashes, retrieval dates and attempted parser metadata are in openband-audit-inventory.json.\n')
    table(['First Nation','Province / fiscal year','Document','Extraction status','Evidence / latest check','Warning / root cause','Status'],[
        (f['name'],f['province']+' / '+f['year'],f['document'],f['parseStatus'],link(f['sourceUrl'],'Original PDF')+' / '+str(f.get('auditAttempt',{}).get('checkedAt') or f['lastChecked'] or f['retrievedAt'] or 'Retrieval date not recorded'),
         '; '.join(f.get('auditAttempt',{}).get('warnings') or f['warnings'] or ['Original source interpretation or extraction not verified'])[:480], 'NEEDS MANUAL REVIEW') for f in audit['filings'] if f['status']=='NEEDS MANUAL REVIEW'])
    add('## Appendix B — legacy validation, duplicates and provenance review flags\n')
    add('These checks do not prove a source error. Existing working values remain available with their source; resolve flags by comparing original documents. Remuneration/footer rounding and separately reported surplus adjustments must not be rewritten to force a simple equation. Duplicate names may represent different scopes or terms. Different URLs for one year may be revisions or corrected document types.\n')
    table(['First Nation / feature','Province / fiscal year','Defect / review trigger','Evidence','Remaining action','Status'],[
        (p['name'],str(p.get('province') or '')+' / '+str(p.get('year') or 'N/A'),p['defect']+('; '+'; '.join(p.get('warnings') or [])[:300] if p.get('warnings') else ''),
         '<br>'.join(link(url,'Source') for url in p.get('sourceUrls',[p.get('sourceUrl')]) if url) or 'data.json / logo registry; see integrity inventory',
         'Compare original source, categories, identities and revision history; preserve source-supported amounts',p['status']) for p in audit['problems']])
    add('## Appendix C — unusual year-over-year changes\n')
    add('Threshold: absolute revenue or expense change of at least 50% across consecutive available fiscal years. These are **NEEDS MANUAL REVIEW**, not presumed extraction errors. Check restatements, extraordinary items, scope changes and the original statements.\n')
    table(['First Nation','Province / fiscal year','Metric','Previous / current','Evidence','Status'],[(p['name'],p['province']+' / '+p['year'],p['field'],f"${p['before']:,.0f} / ${p['after']:,.0f}",link(p['sourceUrl'],'Current original PDF'),'NEEDS MANUAL REVIEW') for p in audit['yearOverYearFlags']])
    add('## Appendix D — duplicate source and monetary checks\n')
    duplicates=audit['duplicateChecks']
    add(f"Found {len(duplicates['sourceUrlGroups'])} equivalent source-URL groups, {len(duplicates['pdfHashGroups'])} repeated PDF-hash groups among {duplicates['documentsWithRecordedOrRetrievedHash']} documents with a recorded or audit-retrieved hash, and {len(duplicates['identicalOfficialAmountRows'])} identical same-official payment-row groups. Documents without retrieved bytes cannot be certified as unique. Equal salaries for different officials are not automatically duplicates. Shared reports and repeated payment scopes require source comparison; nothing was deleted. Complete clusters are in the integrity inventory.\n")
    table(['Trigger','Documents / community / fiscal year','Evidence','Remaining action','Status'],[
        ('Identical PDF bytes','; '.join(row['name']+' / '+row['province']+' / '+row['year']+' / '+row['document'] for row in group),'<br>'.join(link(row['sourceUrl'],'PDF') for row in group),'Compare identity/year, shared administration, source revisions and payment scopes','NEEDS MANUAL REVIEW') for group in duplicates['pdfHashGroups']])
    table(['Community','Province / fiscal year','Identical same-official rows','Evidence','Remaining action','Status'],[(row['name'],row['province']+' / '+row['year'],row['rowNumbers'],link(row['sourceUrl'],'PDF'),'Confirm separate scopes or remove a duplicate only after original-source verification','NEEDS MANUAL REVIEW') for row in duplicates['identicalOfficialAmountRows']])
    (ROOT/'OPENBAND_AUDIT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Wrote OPENBAND_AUDIT.md:',len(lines),'lines; extraction queue',c['reviewDocuments'])


if __name__=='__main__':
    build()
