"""Resume non-financial ISC profile enrichment; never requests filing pages."""
import argparse,copy,re
from lxml import html
from tools.bc_sources import ROOT,CACHE,fetch,read,atomic_write
from tools.ingest_alberta import page_url,verify_page,field
from tools.contact_scraper import parse_isc_profile
from tools.member_count_scraper import parse_population_page
PAGES={'profile':'FNMain','population':'FNRegPopulation','reserves':'FNReserves','leadership':'FNGovernance'}

def enrich(seed,refresh=False):
 band=copy.deepcopy(seed);band['sourceErrors']=[]
 for kind,page in PAGES.items():
  url=page_url(page,seed['iscBandNumber'])
  try:
   payload,meta=fetch(url,refresh);text=verify_page(payload,seed['iscBandNumber']);doc=html.fromstring(payload.decode('utf-8-sig'))
   band['sources'].append({'field':kind,**meta})
   if kind=='profile':
    contact=parse_isc_profile(payload,url)
    if contact.get('office_phone') and not re.fullmatch(r'\(\d{3}\) \d{3}-\d{4}',contact['office_phone']):contact['office_phone']=None
    official=field(doc,'lblName') or contact.get('official_name')
    if official:band['officialName']=official;band['aliases']=sorted(set(band.get('aliases',[])+[official])-{band['name']})
    band['contact']=contact;band['website']=contact.get('website_url');council=doc.xpath('//*[@id="plcMain_hlTCName"]');band['tribalCouncil']=' '.join(council[0].text_content().split()) if council else None
   elif kind=='population':
    pop=parse_population_page(payload.decode('utf-8-sig'))
    if pop.get('bandNumber')!=seed['iscBandNumber'] or not pop.get('sourcePeriod'):raise ValueError('Population identity/reference period unavailable')
    rows=[[' '.join(c.text_content().split()) for c in tr.xpath('./td')] for tr in doc.xpath('//tr')]
    def total(label):
     values=[int(r[1].replace(',','')) for r in rows if len(r)==2 and re.fullmatch(label,r[0],re.I) and re.fullmatch(r'[\d,]+',r[1])]
     return sum(values) if len(values)==2 else None
    band['population']={**pop,'onOwnReserve':total(r'Registered (?:Males|Females) On Own Reserve'),'offReserve':total(r'Registered (?:Males|Females) Off Reserve'),'definition':'ISC registered population; not total citizenship or residents of a self-governing Nation','sourceUrl':url,'retrievedAt':meta['retrievedAt']}
   elif kind=='reserves':
    band['reserves']=[dict(zip(['number','name','location','hectares'],c)) for tr in doc.xpath('//tr') if len(c:= [' '.join(x.text_content().split()) for x in tr.xpath('./td')])==4 and c[0].isdigit()]
   elif kind=='leadership':
    officials=[]
    for tr in doc.xpath('//tr'):
     c=[' '.join(x.text_content().split()) for x in tr.xpath('./td')]
     if len(c)==5 and c[0].lower() in ('chief','councillor','councilor'):officials.append(dict(zip(['position','surname','givenName','appointmentDate','expiryDate'],c)))
    selection=re.search(r'(?:Election System|Selection System|Electoral System)\s+(.+?)(?:Council|Chief|Office|$)',text)
    band['leadership']={'sourceUrl':url,'retrievedAt':meta['retrievedAt'],'officials':officials,'classification':'ISC-listed appointments; current only when a verified term includes today'}
  except Exception as e:band['sourceErrors'].append({'kind':kind,'url':url,'error':str(e)})
 band['filings']=[];band['financialIndexStatus']='not_indexed_phase2'
 return band

def build(refresh=False,limit=0):
 out=CACHE/'enrichment.json';saved=read(out) if out.exists() else {'schemaVersion':1,'nations':[]};byid={str(b['id']):b for b in saved['nations']};seeds=read(CACHE/'isc-seeds.json')['nations']
 if limit:seeds=seeds[:limit]
 for i,seed in enumerate(seeds,1):
  if str(seed['id']) in byid and not refresh:continue
  band=enrich(seed,refresh);byid[str(band['id'])]=band;atomic_write(out,{'schemaVersion':1,'nations':list(byid.values())});print(f'{i}/{len(seeds)} {band["id"]} {band["name"]}: {len(band["sourceErrors"])} source gaps',flush=True)
 if not limit:enrich_cross_border(refresh)
 return byid
def enrich_cross_border(refresh=False):
 path=CACHE/'additional-enrichment.json'
 if path.exists() and not refresh:return read(path)
 from tools.bc_provincial_evidence import content
 from urllib.parse import parse_qs,urlsplit
 extra=[]
 for bid,name,key in [(501,'Taku River Tlingit','taku-river-tlingit'),(504,'Dease River','dease-river-first-nation')]:
  r=next(r for r in read(CACHE/'provincial-candidates.json') if key in r['url']);page,source=fetch(r['url'],refresh);doc=content(page)
  linked=[]
  for u in doc.xpath('//a/@href'):
   q={k.lower():v for k,v in parse_qs(urlsplit(u).query).items()}
   linked.extend(int(v) for v in q.get('band_number',[]) if v.isdigit())
  if bid not in linked:raise ValueError('BC-to-ISC cross-border identity requires review')
  page,identity=fetch(page_url('FNMain',bid),refresh);verify_page(page,bid)
  seed={'id':bid,'iscBandNumber':bid,'name':name,'officialName':name,'aliases':[],'province':'BC','filings':[],'verificationStatus':'verified_isc_identity','verifiedAt':identity['retrievedAt'],'sources':[{'field':'identity',**identity},{'field':'province',**source}],'identityNote':'BC-located government served by ISC Yukon Region; original ISC identifier preserved.'}
  extra.append(enrich(seed,refresh))
 result={'nations':extra};atomic_write(path,result);return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--refresh',action='store_true');p.add_argument('--limit',type=int,default=0);a=p.parse_args();build(a.refresh,a.limit)
