"""Refresh official listing evidence without changing indexed financial data."""
from concurrent.futures import ThreadPoolExecutor
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


def review(band):
    bid=band.get('iscBandNumber',band['id'])
    url=page_url('FederalFundingMain',bid)
    row={'bandId':str(band['id']),'name':band['name'],'province':band['province'],'sourceUrl':url,'checkedAt':now()}
    try:
        source=parse_filings(download(url,refresh=True),bid)
        indexed={listing_identity(f['href']) for f in band.get('filings',[]) if f.get('href')}
        row.update(status='VERIFIED FIXED',postedDocuments=len(source),
                   newDocuments=[f for f in source if listing_identity(f['href']) not in indexed],
                   years=sorted({f['year'] for f in source}),sourceFilings=source)
    except Exception as error:
        row.update(status='BLOCKED',error=f'{type(error).__name__}: {error}')
    return row


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-new',action='store_true',help='Append only source-listed documents absent from the index')
    args=parser.parse_args()
    selected={388,409,365,378,362,385,381,386,387,379,392,366,367}
    bands=[b for b in read('data.json')['bands'] if not b.get('sharedIscIdentity')
           and (b['province']=='AB' or b['id'] in selected)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(review,bands))
    write('audit-disclosure-sources.json',{'checkedAt':now(),'results':results})
    if args.write_new:
        data=read('data.json'); indexed={str(b['id']):b for b in data['bands']}
        for result in results:
            for filing in result.get('newDocuments',[]):
                filing.update(parse_status='pending_manual_review',manual_review_required=True,
                              verificationStatus='source_listed_pending_extraction')
                indexed[result['bandId']]['filings'].append(filing)
        data['generated']=now()
        write('data.json',data)
    print('Listings checked:',len(results),'errors:',sum(r['status']=='BLOCKED' for r in results),
          'new documents:',sum(len(r.get('newDocuments',[])) for r in results))
