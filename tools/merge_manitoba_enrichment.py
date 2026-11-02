"""Synchronize verified Manitoba profile sidecars; keep unreviewed logos blank."""
import hashlib
from tools.ingest_manitoba import ROOT,configure,safe_write
from tools import ingest_alberta as engine
from tools.collect_first_nation_logos import unverified_record

def merge():
    configure();data=engine.read(ROOT/'data.json');bands=[b for b in data['bands'] if b.get('province')=='MB']
    from collections import defaultdict
    from urllib.parse import urlsplit
    from lxml import html
    from tools.refresh_manitoba_roster import AMC_SOURCE
    def host(url):return (urlsplit(url or '').hostname or '').lower().removeprefix('www.')
    profile_hosts=defaultdict(list);amc_hosts=defaultdict(set)
    for band in bands:
        if band.get('website'):profile_hosts[host(band['website'])].append(band)
    amc=html.fromstring((ROOT/'tools/manitoba-source-cache/amc.html').read_text())
    for link in amc.xpath('//a[@href]'):
        name=' '.join(link.text_content().split());domain=host(link.get('href'))
        if name and domain:amc_hosts[domain].add((name,link.get('href')))
    for domain,rows in profile_hosts.items():
        if len(rows)!=1 or len(amc_hosts[domain])!=1:continue
        name,url=next(iter(amc_hosts[domain]));band=rows[0]
        if name==band['name'] or len(name)<4:continue
        band['aliases']=sorted(set(band.get('aliases',[])+[name])-{band['name']})
        evidence={'alias':name,'method':'Unique exact website hostname shared by the band-number-verified ISC profile and AMC listing','urls':[engine.page_url('FNMain',band['iscBandNumber']),AMC_SOURCE],'linkedWebsite':url}
        band['aliasEvidence']=[e for e in band.get('aliasEvidence',[]) if e['alias']!=name]+[evidence]
        source={'field':'alias','url':AMC_SOURCE}
        band['sources']=list({(r['field'],r['url']):r for r in band.get('sources',[])+[source]}.values())
    registry=engine.read(ROOT/'manitoba-nations.json');by_id={str(b['id']):b for b in bands}
    for seed in registry['nations']:
        band=by_id[str(seed['id'])]
        for field in ('officialName','aliases','aliasEvidence','population','tribalCouncil','mainReserve','reserves','website','contact','sources','sourceErrors'):
            if field in band:seed[field]=band[field]
    safe_write(ROOT/'manitoba-nations.json',registry)
    engine.integrate_profiles(data,bands)
    logos=engine.read(ROOT/'first-nation-logos.json');report=engine.read(ROOT/'first-nation-logo-report.json')
    known={str(r['nation_id']) for r in logos['logos']}
    for band in bands:
        if str(band['id']) not in known:
            logo=unverified_record(band,band.get('website'),'ISC-listed Nation website','No Manitoba logo has been visually source-verified. OpenBand placeholder only.')
            logos['logos'].append(logo);report.append({'nation_id':band['id'],'nation_name':band['name'],'status':logo['logo_status'],'source':logo['logo_source'],'reason':logo['verification_note']})
        logo=next(r for r in logos['logos'] if str(r['nation_id'])==str(band['id']))
        for key in ('logo_url','logo_source','logo_asset_source','logo_verified','logo_status'):band[key]=logo[key]
        for filing in band.get('filings',[]):
            filing['nationId']=band['id']
            if filing.get('href') and not filing.get('sha256'):
                cached=engine.CACHE/hashlib.sha256(engine.canonical_url(filing['href']).encode()).hexdigest()
                if cached.exists():
                    payload=cached.read_bytes()
                    if payload.lstrip().startswith(b'%PDF-'):
                        filing.update(sha256=hashlib.sha256(payload).hexdigest(),byteSize=len(payload),pdfCacheVerifiedAt=engine.now(),retrievalEvidence='Cached original PDF; extraction did not finish')
    logos.update(recordCount=len(logos['logos']),verifiedCount=sum(bool(r['logo_verified']) for r in logos['logos']))
    logos['unverifiedCount']=logos['recordCount']-logos['verifiedCount']
    maps=engine.read(ROOT/'map-data.json');maps['communityCount']=len(maps['communities'])
    contacts=engine.read(ROOT/'contacts-data.json');contacts['recordCount']=len(contacts['contacts'])
    for contact in contacts['contacts']:
        if str(contact['nation_id']) not in {str(b['id']) for b in bands}:continue
        contact['field_sources']={key:contact['source_url'] if contact.get(key) else None for key in ('office_phone','office_email','website_url','mailing_address')}
    for key,field in [('emailCount','office_email'),('phoneCount','office_phone'),('websiteCount','website_url'),('mailingAddressCount','mailing_address')]:contacts[key]=sum(bool(r.get(field)) for r in contacts['contacts'])
    enterprise=engine.read(ROOT/'community-enterprise.json')
    covered={str(row['bandId']) for row in enterprise.get('coverage',[])}
    for band in bands:
        if str(band['id']) not in covered:enterprise['coverage'].append({'bandId':band['id'],'directOrganizationStatus':'not yet verified','tribalCouncil':band.get('tribalCouncil'),'collectiveOrganizationIds':[],'lastChecked':None,'note':'Manitoba enterprise ownership has not yet been researched; missing listings do not mean no economic activity.'})
    safe_write(ROOT/'community-enterprise.json',enterprise)
    members=engine.read(ROOT/'member-counts.json')
    # Existing membership schema uses explicit registered counts, not on-reserve substitutes.
    for band in bands:
        population=members['bands'].get(str(band['id']))
        if population:population.update(sourceYear=population.get('sourcePeriod'),notes='Total registered population; on-own-reserve count is separate.')
    for name,value in [('data.json',data),('first-nation-logos.json',logos),('first-nation-logo-report.json',report),('map-data.json',maps),('contacts-data.json',contacts),('member-counts.json',members)]:safe_write(ROOT/name,value)
if __name__=='__main__':merge()
