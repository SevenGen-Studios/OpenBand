from __future__ import annotations
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_YEARS = [f'{y}-{y+1}' for y in range(2021, 2026)]
ROOT = Path(__file__).resolve().parents[2]

def now():
    return datetime.now(timezone.utc).isoformat()

def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)

def key(*parts):
    return hashlib.sha256(dump(parts).encode()).hexdigest()

def read(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default

class Store:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.pdfs = self.directory / 'pdfs'
        self.pdfs.mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.directory / 'review.sqlite', timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS slots(id TEXT PRIMARY KEY, band_id TEXT, year TEXT, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS candidates(id TEXT PRIMARY KEY, slot_id TEXT NOT NULL, url TEXT NOT NULL,
          source TEXT NOT NULL, sha256 TEXT, state TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
          next_try REAL NOT NULL DEFAULT 0, lease REAL NOT NULL DEFAULT 0, payload TEXT NOT NULL DEFAULT '{}',
          UNIQUE(slot_id,url));
        CREATE INDEX IF NOT EXISTS document_hash ON candidates(sha256);
        CREATE TABLE IF NOT EXISTS searches(id INTEGER PRIMARY KEY, slot_id TEXT, url TEXT, status TEXT,
          detail TEXT, checked_at TEXT);
        CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, candidate_id TEXT, action TEXT,
          actor TEXT, at TEXT, previous TEXT, replacement TEXT, evidence TEXT);
        CREATE TRIGGER IF NOT EXISTS history_no_update BEFORE UPDATE ON history BEGIN SELECT RAISE(ABORT,'immutable history'); END;
        CREATE TRIGGER IF NOT EXISTS history_no_delete BEFORE DELETE ON history BEGIN SELECT RAISE(ABORT,'immutable history'); END;
        CREATE TABLE IF NOT EXISTS settings(name TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, state TEXT, payload TEXT, updated_at TEXT);
        ''')
        self.db.commit()

    def event(self, cid, action, actor, previous, replacement, evidence):
        self.db.execute('INSERT INTO history(candidate_id,action,actor,at,previous,replacement,evidence) VALUES(?,?,?,?,?,?,?)',
                        (cid, action, actor, now(), dump(previous), dump(replacement), dump(evidence)))

    def candidate(self, sid, url, source):
        cid = key(sid, url)
        self.db.execute('INSERT OR IGNORE INTO candidates(id,slot_id,url,source) VALUES(?,?,?,?)', (cid,sid,url,source))
        self.db.commit()
        return cid

    def search(self, sid, url, status, detail):
        self.db.execute('INSERT INTO searches(slot_id,url,status,detail,checked_at) VALUES(?,?,?,?,?)',
                        (sid,url,status,str(detail)[:4000],now()))
        self.db.commit()

    def save_candidate(self, cid, payload, state='done', sha=None):
        self.db.execute('UPDATE candidates SET payload=?,state=?,sha256=COALESCE(?,sha256),lease=0 WHERE id=?',
                        (dump(payload),state,sha,cid))
        self.db.commit()

    def rows(self, table):
        if table not in {'slots','candidates','searches','history','jobs'}:
            raise ValueError('Invalid table')
        return [dict(r) for r in self.db.execute(f'SELECT * FROM {table}')]

    def inventory(self, root=ROOT, years=None):
        import re
        years = years or DEFAULT_YEARS
        if not years or len(years)>20 or any(not re.fullmatch(r'20\d{2}-20\d{2}',y) or int(y[-4:])!=int(y[:4])+1 for y in years):
            raise ValueError('Expected consecutive fiscal-year pairs, at most 20')
        data = read(Path(root)/'data.json')
        capital = read(Path(root)/'capital-data.json', {})
        identities = {}
        for filename in ('saskatchewan-nations.json','alberta-nations.json','manitoba-nations.json'):
            roster=read(Path(root)/filename, [])
            if isinstance(roster,dict): roster=roster.get('nations',roster.get('bands',[]))
            if isinstance(roster,list):
                for item in roster:
                    if isinstance(item,dict): identities[str(item.get('id',item.get('bandNumber','')))]=item
        local_hashes={}
        for base in (Path(root)/'research',self.pdfs):
            if base.exists():
                for pdf in base.rglob('*.pdf'):
                    if pdf.stat().st_size<=40_000_000:
                        local_hashes[hashlib.sha256(pdf.read_bytes()).hexdigest()]=str(pdf)
        manifest_sources={}
        manifest=read(Path(root)/'tests/fixtures/bandy-sk/manifest.json',{})
        for doc in manifest.get('documents',[]):
            if doc.get('sourceUrl') and doc.get('sha256') in local_hashes:manifest_sources[doc['sourceUrl']]=doc['sha256']
        for band in data['bands']:
            bid = str(band['id'])
            extra=identities.get(bid,{})
            aliases=[v for v in (extra.get('officialName'),extra.get('name')) if isinstance(v,str) and v!=band['name']]
            for obj in (band,extra):
                for field in ('aliases','alternativeNames','historicalNames','formerNames','alternateNames'):
                    values=obj.get(field,[])
                    aliases.extend([values] if isinstance(values,str) else [v for v in values if isinstance(v,str)] if isinstance(values,list) else [])
            for year in years:
                sid=key(bid,year)
                filings=[f for f in band.get('filings',[]) if f.get('year')==year and 'audited' in f.get('docType','').lower() and 'remuneration' not in f.get('docType','').lower()]
                summary=capital.get('bands',{}).get(bid,{}).get('years',{}).get(year,{})
                comparative=bool(summary.get('comparative') or summary.get('extractionBasis')=='comparative' or summary.get('sourceFiscalYear',year)!=year)
                indexed=any(f.get('href') and f.get('posted') is not False for f in filings)
                valid=bool(indexed and any(summary.get(k) is not None for k in ('totalRevenue','totalExpenses','annualSurplusDeficit')) and summary.get('parseStatus')=='parsed' and summary.get('publishable') is not False and summary.get('sourceUrl') and not comparative)
                has_values=any(summary.get(k) is not None for k in ('totalRevenue','totalExpenses','annualSurplusDeficit'))
                gaps=[]
                if not indexed: gaps.append('missing_filing')
                if not any(f.get('href') for f in filings): gaps.append('missing_pdf_link')
                if not has_values: gaps.append('missing_financial_data')
                elif not valid: gaps.append('incomplete_extraction')
                if comparative: gaps.append('comparative_only')
                local=next((f.get('localPdf') or f.get('pdfPath') for f in filings if f.get('localPdf') or f.get('pdfPath')),None)
                hashes=[f.get('sha256') or f.get('sourceDocumentSha256') or manifest_sources.get(f.get('href')) for f in filings]+[summary.get('sha256')]
                matched=next((local_hashes[h] for h in hashes if h in local_hashes),None)
                stored=bool((local and (Path(root)/local).is_file()) or matched)
                if not stored: gaps.append('original_pdf_not_stored')
                if any(f.get('linkStatus') in ('broken','404','410') for f in filings): gaps.append('broken_document_link')
                payload=dict(name=band['name'],bandNumber=band.get('iscBandNumber'),bandId=bid,province=band.get('province','Unknown'),
                    aliases=sorted(set(aliases)),fiscalYear=year,indexed=indexed,existingValid=valid,
                    existingSummary=summary,existingFilings=filings,gaps=gaps,pdfStored=stored,pdfStoragePath=local or matched,
                    website=band.get('website') or extra.get('website') or extra.get('websiteUrl'),
                    identityUnconfirmed=not bool(band.get('iscBandNumber')) or bool(band.get('sharedIscIdentity')))
                self.db.execute('INSERT INTO slots VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (sid,bid,year,dump(payload)))
                for filing in filings:
                    if filing.get('href') and (gaps or not valid): self.candidate(sid,filing['href'],filing.get('sourceListingUrl') or filing['href'])
        self.db.execute("INSERT INTO settings VALUES('active_years',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",(dump(years),))
        self.db.commit()
        return self.report(years)

    def active_years(self):
        row=self.db.execute("SELECT value FROM settings WHERE name='active_years'").fetchone()
        return json.loads(row[0]) if row else DEFAULT_YEARS

    def report(self, years=None):
        years=years or self.active_years()
        slots=self.rows('slots')
        if years: slots=[s for s in slots if s['year'] in years]
        ids={s['id'] for s in slots}
        candidates=[c for c in self.rows('candidates') if c['slot_id'] in ids]
        by_slot={}
        for c in candidates: by_slot.setdefault(c['slot_id'],[]).append(c)
        counts=dict(totalFirstNationsReviewed=len({s['band_id'] for s in slots}),totalExpectedSlots=len(slots),filingsAlreadyIndexed=0,
            existingValidRecords=0,missingFilingsDiscoveredPublicly=0,newlyVerifiedDocuments=0,awaitingManualReview=0,
            notPubliclyLocated=0,ocrExtractionFailures=0,duplicateDocumentsDetected=0,searchPending=0)
        output=[]
        for slot in slots:
            p=json.loads(slot['payload']); docs=by_slot.get(slot['id'],[])
            accepted=[c for c in docs if json.loads(c['payload']).get('documentValid') and c['state']!='rejected']
            approved=[c for c in accepted if c['state'] in ('approved','imported')]
            if any('HTTP 404' in json.loads(c['payload']).get('message','') or 'HTTP 410' in json.loads(c['payload']).get('message','') for c in docs):p['gaps'].append('broken_document_link')
            if any(c['sha256'] and (self.pdfs/(c['sha256']+'.pdf')).is_file() for c in accepted):
                p['pdfStored']=True;p['gaps']=[g for g in p['gaps'] if g!='original_pdf_not_stored']
            searched=self.db.execute("SELECT 1 FROM searches WHERE slot_id=? AND status='search_complete'",(slot['id'],)).fetchone()
            status='Verified' if approved else 'Review Required' if any(json.loads(c['payload']).get('records') for c in accepted) else 'Document Found — Extraction Pending' if accepted else 'Review Required' if p['indexed'] else 'Search Pending' if any(c['state'] in ('queued','processing','failed') for c in docs) else 'Not Publicly Located' if searched else 'Search Pending'
            counts['filingsAlreadyIndexed']+=p['indexed'];counts['existingValidRecords']+=p['existingValid']
            counts['missingFilingsDiscoveredPublicly']+=bool(accepted and not p['existingValid'])
            counts['newlyVerifiedDocuments']+=len(approved)
            counts['awaitingManualReview']+=sum(c['state']=='done' and bool(json.loads(c['payload']).get('documentValid')) for c in docs)
            counts['notPubliclyLocated']+=status=='Not Publicly Located'
            counts['searchPending']+=status=='Search Pending'
            counts['ocrExtractionFailures']+=sum(bool(json.loads(c['payload']).get('ocrFailure')) for c in docs)
            counts['duplicateDocumentsDetected']+=sum(bool(json.loads(c['payload']).get('duplicateOf')) for c in docs)
            summaries=[]
            for c in docs:
                cp=json.loads(c['payload'])
                cp={k:v for k,v in cp.items() if k not in ('pages','records','secondaryRecords','resolutions','unlocatedObservations')}
                summaries.append(dict(c,payload=cp))
            output.append(dict(id=slot['id'],**p,status=status,candidates=summaries))
        return dict(generatedAt=now(),years=sorted({s['year'] for s in slots}),counts=counts,slots=output,
            notice='A public filing not located is not evidence that a Nation failed to prepare or submit an audit.')
