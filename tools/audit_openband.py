"""Read-only cross-province integrity inventory for OPENBAND_AUDIT.md.

Does not certify uninspected PDFs or infer missing records from failed sources.
"""
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, unquote
from lxml import html
from tools.build_site import slugify
from tools.ingest_alberta import canonical_url
from tools.parser_quality import validate_people
from tools.review_disclosures import listing_identity

ROOT=Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT/name).read_text(encoding='utf-8'))


def inventory():
    data,capital,map_data=read('data.json'),read('capital-data.json'),read('map-data.json')
    map_rows={str(row['id']):row for row in map_data['communities']}
    contacts={str(row['nation_id']):row for row in read('contacts-data.json')['contacts']}
    logos={str(row['nation_id']):row for row in read('first-nation-logos.json')['logos']}
    enterprise=read('community-enterprise.json')
    elections=read('elections-data.json')['records']
    filings,problems,profiles,changes,duplicate_amounts=[],[],[],[],[]
    today=datetime.now(timezone.utc).date().isoformat()
    attempts={}
    for path in ROOT.glob('audit-*-results.json'):
        for attempt in json.loads(path.read_text(encoding='utf-8')).get('outcomes',[]):
            url=attempt.get('sourceUrl')
            if url and (url not in attempts or str(attempt.get('checkedAt') or '')>str(attempts[url].get('checkedAt') or '')):
                attempts[url]=attempt
    for band in data['bands']:
        bid=str(band['id']); seen=defaultdict(list)
        for filing in band.get('filings',[]):
            if not filing.get('posted'): continue
            row={'bandId':bid,'name':band['name'],'province':band['province'],'year':filing['year'],
                 'document':filing['docType'],'sourceUrl':filing.get('href'),'parseStatus':filing.get('parse_status'),
                 'retrievedAt':filing.get('retrievedAt'),'lastChecked':filing.get('lastChecked'),
                 'verificationStatus':filing.get('verificationStatus'),'sha256':filing.get('sha256'),
                 'people':len(filing.get('people') or []),'warnings':filing.get('warnings',[])}
            attempt=attempts.get(filing.get('href'),{})
            row['auditAttempt']={key:attempt.get(key) for key in ('checkedAt','sha256','parserStatus','warnings','documentChecks')}
            row['sourceVerificationStatus']=filing.get('sourceVerificationStatus')
            if 'audited' in filing['docType'].lower():
                summary=capital.get('bands',{}).get(bid,{}).get('years',{}).get(filing['year'],{})
                same_source=bool(summary.get('sourceUrl') and filing.get('href') and listing_identity(summary['sourceUrl'])==listing_identity(filing['href']))
                same_hash=bool(summary.get('sha256') and summary.get('sha256')==filing.get('sha256'))
                row['publishableSummary']=bool(summary.get('publishable') and summary.get('parseStatus')=='parsed' and (same_source or same_hash))
                row['status']='VERIFIED FIXED' if row['publishableSummary'] else 'NEEDS MANUAL REVIEW'
                if not row['publishableSummary']: row['warnings']=summary.get('warnings',row['warnings'])
            else:
                row['status']='VERIFIED FIXED' if row['people'] and not filing.get('manual_review_required') else 'NEEDS MANUAL REVIEW'
                if filing.get('parse_status')=='not_applicable_wrong_document' and not filing.get('people'):
                    row['status']='VERIFIED FIXED'
                    row['extractionDisposition']='Known wrong source document is correctly excluded'
            if filing.get('href'):
                seen[(filing['year'],filing['docType'])].append(filing['href'])
                query={k.upper():v[0] for k,v in parse_qs(urlsplit(filing['href']).query).items()}
                expected=str(band.get('iscBandNumber',band['id']))
                if query.get('BAND_NUMBER_FF',expected)!=expected or query.get('FY',filing['year'])!=filing['year']:
                    problems.append(dict(row,defect='Document URL community or fiscal year mismatch',status='NEEDS MANUAL REVIEW'))
            if not re.fullmatch(r'20\d{2}-20\d{2}',filing['year']) or int(filing['year'][-4:])!=int(filing['year'][:4])+1:
                problems.append(dict(row,defect='Invalid fiscal-year label',status='OPEN'))
            if row['people']:
                validation=validate_people(filing['people'],source_total=filing.get('sourceTotal'),strict=True)
                if validation['manual_review_required']:
                    problems.append(dict(row,defect='Legacy remuneration fails current strict validation',warnings=validation['warnings'],status='NEEDS MANUAL REVIEW'))
                names=Counter(str(p.get('name','')).casefold() for p in filing['people'])
                if any(count>1 for count in names.values()):
                    problems.append(dict(row,defect='Repeated official name; may be distinct payment scopes',status='NEEDS MANUAL REVIEW'))
                amounts=defaultdict(list)
                for index,person in enumerate(filing['people'],1):
                    key=(str(person.get('name','')).casefold(),person.get('months'),*(person.get(k) for k in ('remuneration','travel','expenses','creditCard','otherPayments','total')))
                    amounts[key].append(index)
                for indexes in amounts.values():
                    if len(indexes)>1:
                        duplicate_amounts.append(dict(name=band['name'],province=band['province'],year=filing['year'],sourceUrl=filing.get('href'),rowNumbers=indexes,status='NEEDS MANUAL REVIEW'))
            filings.append(row)
        for (year,doc),urls in seen.items():
            if len(urls)>1:
                problems.append({'name':band['name'],'province':band['province'],'bandId':bid,'year':year,
                    'document':doc,'sourceUrl':urls[0],'sourceUrls':urls,'defect':'Multiple documents with same type and year; retain revisions pending comparison','status':'NEEDS MANUAL REVIEW'})
        last=None
        for year,summary in sorted(capital.get('bands',{}).get(bid,{}).get('years',{}).items()):
            if not summary.get('publishable') or summary.get('parseStatus')!='parsed': continue
            if not summary.get('sourceUrl'):
                problems.append({'name':band['name'],'province':band['province'],'year':year,'defect':'Financial summary lacks source URL','status':'OPEN'})
            query={k.upper():v[0] for k,v in parse_qs(urlsplit(summary.get('sourceUrl','')).query).items()}
            if query.get('FY',year)!=year or summary.get('fiscalYear',year)!=year:
                problems.append({'name':band['name'],'province':band['province'],'year':year,'sourceUrl':summary.get('sourceUrl'),'defect':'Financial summary year mismatch','status':'NEEDS MANUAL REVIEW'})
            values=[summary.get(k) for k in ('totalRevenue','totalExpenses','annualSurplusDeficit')]
            if all(isinstance(v,(float,int)) and math.isfinite(v) for v in values):
                adjustments=sum(item.get('amount',0) or 0 for item in summary.get('surplusAdjustments',[]) if isinstance(item.get('amount',0),(int,float)))
                if abs(values[0]-values[1]+adjustments-values[2])>max(10,abs(values[0])*.01):
                    problems.append({'name':band['name'],'province':band['province'],'year':year,'sourceUrl':summary.get('sourceUrl'),'defect':'Headline operations equation needs source accounting review','status':'NEEDS MANUAL REVIEW'})
            if last and int(year[:4])-int(last[0][:4])==1:
                for field in ('totalRevenue','totalExpenses'):
                    before,after=last[1].get(field),summary.get(field)
                    if isinstance(before,(int,float)) and isinstance(after,(int,float)) and before>0 and abs(after-before)/before>=.5:
                        changes.append({'name':band['name'],'province':band['province'],'year':year,'field':field,
                                        'before':before,'after':after,'sourceUrl':summary.get('sourceUrl'),'status':'NEEDS MANUAL REVIEW'})
            last=year,summary
        contact=contacts.get(bid,{})
        logo=logos.get(bid,{})
        if logo.get('logo_verified'):
            asset=ROOT/logo['logo_url'].lstrip('/')
            digest=logo.get('sha256') or logo.get('logo_sha256')
            if not asset.is_file() or digest and hashlib.sha256(asset.read_bytes()).hexdigest()!=digest:
                problems.append({'name':band['name'],'province':band['province'],'defect':'Logo missing or hash mismatch','status':'OPEN'})
        rows=[row for row in filings if row['bandId']==bid]
        officials=band.get('leadership',{}).get('officials',[])
        election_rows=[row for row in elections if str(row.get('firstNationId'))==bid and row.get('elected') and row.get('sourceUrl')]
        latest_election=max(election_rows,key=lambda row:str(row.get('electionDate') or ''),default={})
        enterprise_profile=next((row for row in enterprise['nationProfiles'] if str(row['bandId'])==bid),{})
        business_ids={row['businessId'] for row in enterprise['ownershipInterests'] if row.get('ownerId')==enterprise_profile.get('primaryOrganizationId')}
        business_ids.update(row['id'] for row in enterprise['businesses'] if bid in {str(i) for i in row.get('owningNationIds',[])})
        def expired(record):
            match=re.fullmatch(r'(\d{2})/(\d{2})/(\d{4})',record.get('expiryDate') or '')
            return bool(match and f'{match[3]}-{match[1]}-{match[2]}'<today)
        profiles.append({'bandId':bid,'name':band['name'],'province':band['province'],
                         'filings':len(rows),'reviewDocuments':sum(r['status']=='NEEDS MANUAL REVIEW' for r in rows),
                         'logoVerified':bool(logo.get('logo_verified')),'logoSource':logo.get('logo_source'),
                         'mapPoint':bid in map_rows,'boundaryIds':map_rows.get(bid,{}).get('reserveLandIds',[]),
                         'reserveAreaSource':map_rows.get(bid,{}).get('reserveLandSourceUrl'),
                         'missingContacts':[k for k in ('office_phone','office_email','website_url','mailing_address') if not contact.get(k)],
                         'contactSource':contact.get('source_url'), 'leadershipSource':band.get('leadership',{}).get('sourceUrl'),
                         'leadershipCheckedAt':band.get('leadership',{}).get('retrievedAt'),
                         'leadershipOfficials':len(officials),'expiredLeadershipTerms':sum(expired(record) for record in officials),
                         'contactCheckedAt':contact.get('last_verified'),'treaty':band.get('treaty') or map_rows.get(bid,{}).get('treaty'),
                         'latestElectionDate':latest_election.get('electionDate'),'electionSource':latest_election.get('sourceUrl'),
                         'businessCount':len(business_ids)})
    broken=[]
    for page in [ROOT/'index.html',*(ROOT/'first-nations').glob('*/index.html'),ROOT/'alberta/index.html',ROOT/'saskatchewan/index.html',ROOT/'browse/index.html',ROOT/'news/index.html']:
        doc=html.fromstring(page.read_text(encoding='utf-8'))
        for value in doc.xpath('//@href | //@src'):
            if not value.startswith('/') or value.startswith('//'): continue
            target=ROOT/unquote(urlsplit(value).path).lstrip('/')
            if target.is_dir(): target=target/'index.html'
            if not target.exists():broken.append({'page':str(page.relative_to(ROOT)),'target':value,'status':'OPEN'})
    news=read('news-data.json')['articles']; projects=read('projects-data.json'); elections=read('elections-data.json')['records']
    content={'newsCount':len(news),'newsMissingSource':sum(not item.get('url') for item in news),
             'newsMissingPublicationDate':sum(not item.get('publishedAt') for item in news),
             'newsFutureDates':sum(str(item.get('publishedAt') or '')[:10]>today for item in news),
             'newsDetailsNotVerified':sum(not item.get('detailVerified') for item in news),
             'projectCount':len(projects['projects']),'projectMissingSources':sum(not item.get('sources') for item in projects['projects']),
             'unverifiedProjectSignals':len(projects.get('unverifiedProjects',[])),
             'electionRecords':len(elections),'electionMissingSources':sum(not item.get('sourceUrl') for item in elections),
             'nationsWithoutGovernanceOfficials':sum(not p['leadershipOfficials'] for p in profiles),
             'nationsWithExpiredGovernanceTerms':sum(bool(p['expiredLeadershipTerms']) for p in profiles),
             'nationsWithoutIndexedBusinesses':sum(not p['businessCount'] for p in profiles)}
    urls,hashes=defaultdict(list),defaultdict(list)
    for row in filings:
        if row['sourceUrl']: urls[listing_identity(row['sourceUrl'])].append(row)
        digest=row['sha256'] or row.get('auditAttempt',{}).get('sha256')
        if digest: hashes[digest].append(row)
    duplicates={'sourceUrlGroups':[rows for rows in urls.values() if len(rows)>1],
                'pdfHashGroups':[rows for rows in hashes.values() if len(rows)>1],
                'documentsWithRecordedOrRetrievedHash':sum(len(rows) for rows in hashes.values()),
                'identicalOfficialAmountRows':duplicate_amounts}
    result={'generatedAt':datetime.now(timezone.utc).isoformat(),'scope':'All indexed AB/SK records; strict automated checks are review flags, not proof of source errors',
            'counts':{'profiles':len(profiles),'provinces':dict(Counter(p['province'] for p in profiles)),
                      'postedDocuments':len(filings),'reviewDocuments':sum(f['status']=='NEEDS MANUAL REVIEW' for f in filings),
                      'unverifiedLogos':sum(not p['logoVerified'] for p in profiles),'missingMapPoints':sum(not p['mapPoint'] for p in profiles),
                      'brokenInternalLinks':len(broken),'financialReviewFlags':len(problems),'yearOverYearFlags':len(changes)},
            'contentChecks':content,'duplicateChecks':duplicates,'profiles':profiles,'filings':filings,'problems':problems,'yearOverYearFlags':changes,'brokenInternalLinks':broken}
    (ROOT/'openband-audit-inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result['counts'],indent=2))
    return result


if __name__=='__main__':
    inventory()
