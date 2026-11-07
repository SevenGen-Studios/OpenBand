"""Refresh official listing evidence without changing indexed financial data."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import argparse
from tools.ingest_alberta import read, write, download, page_url, parse_filings, canonical_url, now
from urllib.parse import urlsplit, parse_qs


def listing_identity(url):
    parts=urlsplit(url)
    if parts.hostname in {'services.sac-isc.gc.ca','fnp-ppn.aadnc-aandc.gc.ca'}:
        query=tuple(sorted((key.casefold(),tuple(' '.join(v.casefold().split()) for v in values))
                           for key,values in parse_qs(parts.query).items()))
        return parts.path.casefold(),query
    return canonical_url(url)


def reconcile_listing(band, source_filings, years=None):
    """Promote empty availability placeholders; never replace parsed values."""
    changed=[]
    for source in source_filings:
        if years and source.get('year') not in years:
            continue
        if not source.get('posted') or not source.get('href'):
            continue
        parts=urlsplit(source['href'])
        if parts.scheme!='https' or parts.hostname not in {'services.sac-isc.gc.ca','fnp-ppn.aadnc-aandc.gc.ca'}:
            raise ValueError('Expected an original public ISC disclosure URL')
        query={k.upper():v for k,v in parse_qs(parts.query).items()}
        if query.get('BAND_NUMBER_FF',[None])[0]!=str(band.get('iscBandNumber')) or query.get('FY',[None])[0]!=source.get('year'):
            raise ValueError('Source filing identity/year does not match the target Nation')
        if query.get('DOC',[''])[0].casefold().strip()!=source.get('docType','').casefold().strip():
            raise ValueError('Source document type does not match the listing')
        matches=[f for f in band.get('filings',[]) if f.get('year')==source['year'] and f.get('docType','').casefold().strip()==source['docType'].casefold().strip()]
        if any(f.get('people') or (f.get('posted') and f.get('href')) for f in matches):
            continue  # Revisions and existing values require separate evidence review.
        proposed=deepcopy(source)
        proposed.update(parse_status='pending_manual_review',manual_review_required=True,
                        verificationStatus='source_listed_pending_extraction',people=[],
                        warnings=['Official ISC listing confirms the document is posted; figures await source verification.'])
        if matches:
            # Keep a before image, including the stale availability classification.
            proposed['previousAvailability']={k:matches[0].get(k) for k in ('posted','href','date','parse_status')}
            matches[0].update(proposed)
            for duplicate in matches[1:]:
                band['filings'].remove(duplicate)
        else:
            band.setdefault('filings',[]).append(proposed)
        changed.append(proposed)
    return changed

def review(band):
    bid=band.get('iscBandNumber',band['id'])
    url=page_url('FederalFundingMain',bid)
    row={'bandId':str(band['id']),'name':band['name'],'province':band['province'],'sourceUrl':url,'checkedAt':now()}
    try:
        from tools.filing_review.network import PublicHTTP
        payload,_=PublicHTTP().get(url)
        source=parse_filings(payload,bid)
        indexed={listing_identity(f['href']) for f in band.get('filings',[]) if f.get('href')}
        row.update(status='VERIFIED FIXED',postedDocuments=len(source),
                   newDocuments=[f for f in source if listing_identity(f['href']) not in indexed],
                   years=sorted({f['year'] for f in source}),sourceFilings=source)
    except Exception as error:
        row.update(status='BLOCKED',error=f'{type(error).__name__}: {error}')
    return row


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-new',action='store_true',help='Update empty placeholders or add source-listed documents without replacing parsed values')
    parser.add_argument('--band',type=int,action='append',help='Review exact OpenBand profile IDs, including Saskatchewan')
    parser.add_argument('--year',action='append',help='Reconcile only the selected fiscal year')
    parser.add_argument('--report',default='audit-disclosure-sources.json')
    args=parser.parse_args()
    selected={388,409,365,378,362,385,381,386,387,379,392,366,367}
    bands=[b for b in read('data.json')['bands'] if not b.get('sharedIscIdentity')
           and (b['id'] in args.band if args.band else b['province']=='AB' or b['id'] in selected)]
    with ThreadPoolExecutor(max_workers=1) as pool:
        results=list(pool.map(review,bands))
    write(args.report,{'checkedAt':now(),'results':results})
    if args.write_new:
        data=read('data.json'); indexed={str(b['id']):b for b in data['bands']}
        for result in results:
            reconcile_listing(indexed[result['bandId']],result.get('sourceFilings',[]),set(args.year) if args.year else None)
        data['generated']=now()
        write('data.json',data)
    print('Listings checked:',len(results),'errors:',sum(r['status']=='BLOCKED' for r in results),
          'new documents:',sum(len(r.get('newDocuments',[])) for r in results))
