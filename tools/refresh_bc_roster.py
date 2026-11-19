"""Reconcile official BC identities and preserve organizations/authority conflicts separately."""
import copy,re,json
from urllib.parse import parse_qs,urlsplit
from lxml import html
from tools.bc_sources import *
from tools.ingest_alberta import normalized_name,verify_page
HISTORIC='https://geo.sac-isc.gc.ca/Collection_de_cartes-Map_room/eng/1611593372816.html'

def norm(s):return re.sub(r'\b(first|nation|nations|indian|band|tribe|tribes)\b','',normalized_name(s)).replace(' ','')
def payload(meta):
 p=CACHE/meta['cacheFile']
 if p.exists():return p.read_bytes()
 import gzip
 return gzip.decompress(p.with_suffix(p.suffix+'.gz').read_bytes())
def source_record(field,meta):return {'field':field,**meta}
def build():
 enriched=read(CACHE/'enrichment.json')['nations'];seeds=read(CACHE/'isc-seeds.json')['nations']
 if {b['id'] for b in enriched}!={b['id'] for b in seeds}:raise ValueError('ISC enrichment is incomplete; resume it first')
 nations=copy.deepcopy(enriched+read(CACHE/'additional-enrichment.json')['nations']);byid={b['id']:b for b in nations};evidence=read(CACHE/'province-evidence.json');candidates=read(CACHE/'provincial-candidates.json');queue=[];dispositions=[]
 locations=read(CACHE/'locations.json')
 if locations.get('exceededTransferLimit'):raise ValueError('Incomplete location source')
 points={int(f['properties']['BAND_NUMBER']):f for f in locations['features']};lm=read(CACHE/'locations-source.json')
 hp,hm=fetch(HISTORIC);ht=html.fromstring(hp.decode('utf-8-sig'));historic={norm(c[0]):c[1] for tr in ht.xpath('//tr') if len(c:=[' '.join(x.text_content().split()) for x in tr.xpath('./td')])==2}
 for b in nations:
  b['entityType']='isc_band_or_village_government';b['rosterScope']='bc_community_governments';b['treaty']=None;b['treatyVerificationStatus']='not_verified';b['treatyAgreements']=[];b['treatyNegotiation']=None;b['logo_verified']=False;b['logo_url']=None;b['logo_source']=None;b['logo_asset_source']=None;b['logo_status']='logo_unverified'
  point=points.get(b['id'])
  if point:
   if point['properties']['BAND_NAME']!=b['name']:b['aliases']=sorted(set(b['aliases']+[point['properties']['BAND_NAME']]))
   lon,lat=point['geometry']['coordinates'];b['location']={'longitude':lon,'latitude':lat,'sourceUrl':lm['url'],'retrievedAt':lm['retrievedAt'],'locationType':'ISC representative First Nation point; not a surveyed administrative office'};b['sources'].append(source_record('location',lm))
  gov=next((s for s in b['sources'] if s['field']=='leadership'),None)
  if gov:
   raw=payload(gov);verify_page(raw,b['iscBandNumber']);d=html.fromstring(raw.decode('utf-8-sig'));officials=[]
   for tr in d.xpath('//tr'):
    c=[' '.join(x.text_content().split()) for x in tr.xpath('./td')]
    if len(c)==5 and c[0] and c[1] and c[2] and re.fullmatch(r'\d{2}/\d{2}/\d{4}',c[3]) and re.fullmatch(r'\d{2}/\d{2}/\d{4}',c[4]):officials.append(dict(zip(['position','surname','givenName','appointmentDate','expiryDate'],c)))
   b['leadership']['officials']=officials;x=d.xpath('//*[@id="plcMain_txtElection"]');b['governanceSystem']=' '.join(x[0].text_content().split()) if x else None
  hist=historic.get(norm(b['name']))
  if hist and ('Douglas Treaties' in hist or 'Treaty #8' in hist):
   label='Douglas Treaties' if 'Douglas' in hist else 'Treaty 8';b['treaty']=label;b['treatyVerificationStatus']='verified_historic_treaty';b['treatyAgreements'].append({'kind':'historic_treaty','label':label,'status':'in_effect','sourceUrl':HISTORIC,'verifiedAt':hm['retrievedAt']});b['sources'].append(source_record('historicTreaty',hm))
  if b.get('governanceSystem') and 'self' in b['governanceSystem'].lower():b['treatyAgreements'].append({'kind':'self_government','label':b['governanceSystem'],'status':'ISC-listed governance system; not a treaty classification','sourceUrl':gov['url'],'verifiedAt':gov['retrievedAt']})
 for r in candidates:
  e=evidence.get(r['url']);ids=e.get('iscBandNumbers',[]) if e else []
  # The provincial source labels Tla'amin's link 'Profile8'. Preserve its numeric query evidence.
  if e and not ids:
   for a in e.get('links',[]):
    if a['label'].lower().startswith('profile'):
     q={k.lower():v for k,v in parse_qs(urlsplit(a['url']).query).items()}
     ids.extend(int(v) for v in q.get('band_number',[]) if v.isdigit())
  d={**r,'iscBandNumbers':sorted(set(ids))};text=e.get('text','') if e else ''
  if 'hereditary' in r['name'].lower():d['disposition']='authority_review';queue.append({**d,'reason':'Hereditary authority links to band identifier; do not conflate distinct governing authorities.'})
  elif 'lower-post-first-nation-daylu-dena-council' in r['url']:d['disposition']='separate_community_administration'
  elif len(set(ids))==1 and ids[0] in byid:
   b=byid[ids[0]];d['disposition']='verified_identity_link';d['publishedId']=b['id'];b['aliases']=sorted(set(b['aliases']+[r['name']])-{b['name']});b['sources'].append(source_record('provincialProfile',e['source']));b.setdefault('regionalAffiliations',[]).append({'name':r['memberOf'],'sourceUrl':r['url']}) if r['memberOf'] else None
   b.setdefault('geographicRegions',[]).append({'name':r['region'],'sourceUrl':r['url']})
   if 'came into effect' in text and any(w in text for w in ['Nisga','Maa-nulth',"Tla'amin",'Tsawwassen']):
    label="Nisga'a Final Agreement" if 'Nisga' in text else 'Maa-nulth First Nations Final Agreement' if 'Maa-nulth' in text else "Tla'amin Final Agreement" if "Tla'amin" in text else 'Tsawwassen Final Agreement'
    a={'kind':'modern_treaty','label':label,'status':'in_effect','sourceUrl':r['url'],'verifiedAt':e['source']['retrievedAt']}
    if a not in b['treatyAgreements']:b['treatyAgreements'].append(a)
    b['treaty']=label;b['treatyVerificationStatus']='verified_modern_treaty'
    if historic.get(norm(b['name']))=='not signatory to a treaty':queue.append({'id':b['id'],'sourceUrls':[HISTORIC,r['url']],'reason':'Historic map labels not-signatory without modern treaty distinction. Current dated in-effect treaty evidence is retained separately.','resolution':'Use explicit provincial final-agreement evidence; never propagate map non-signatory label.'})
   stage=re.search(r'Treaty [Ss]tage\s+(.{0,140}?)(?=Completed agreements|Forestry|Other agreements|Location:|Information|Tumbler Ridge)',text)
   if stage:b['treatyNegotiation']={'statusText':stage[1].strip(),'sourceUrl':r['url'],'verifiedAt':e['source']['retrievedAt'],'note':'Negotiation participation is not a completed treaty.'}
  elif ids and all(i not in byid for i in ids):d['disposition']='outside_bc_primary_community_scope'
  elif 'Yukon' in r['region'] or 'Northwest Territories' in r['region']:d['disposition']='outside_bc_primary_community_scope'
  elif any('TC_NUMBER=' in a['url'].upper() for a in (e or {}).get('links',[])) or 'Members:' in text:d['disposition']='regional_or_treaty_organization'
  else:d['disposition']='identity_review';queue.append({**d,'reason':'Separate identity/governing authority needs source-backed reconciliation; no profile or band number invented.'})
  dispositions.append(d)
 # These source-derived stable identifiers are application IDs, never ISC band numbers.
 extras=[('bc-fnpo-9637',"Nisga'a Lisims Government",'nisga-a-lisims-government','treaty_nation_government',[671,677,678,679]),('bc-haida-nation-council-of','Council of the Haida Nation','haida-nation-council-of','national_government',[669,670]),('bc-lower-post-first-nation-daylu-dena-council','Daylu Dena Council','lower-post-first-nation-daylu-dena-council','community_administration',[])]
 for bid,name,key,kind,related in extras:
  u=next(u for u in evidence if key in u);e=evidence[u];r=next(r for r in candidates if r['url']==u);external=next((a['url'] for a in e['links'] if a['label'] in [name,"Nisga'a Lisims Government"]),None)
  b={'id':bid,'iscBandNumber':None,'name':name,'officialName':name,'aliases':[r['name']] if r['name']!=name else [],'province':'BC','entityType':kind,'rosterScope':'bc_community_governments','verificationStatus':'verified_government_identity','verifiedAt':e['source']['retrievedAt'],'sources':[source_record('identity',e['source']),source_record('profile',e['source'])],'website':external,'filings':[],'financialIndexStatus':'not_indexed_phase2','treaty':None,'treatyVerificationStatus':'not_verified','treatyAgreements':[],'relatedNationIds':related,'logo_verified':False,'logo_url':None,'identityNote':'Distinct '+kind.replace('_',' ')+'. Do not sum or copy constituent governments’ population, leadership, reserves, or financial records.'}
  if 'nisga' in key:b['treaty']="Nisga'a Final Agreement";b['treatyVerificationStatus']='verified_modern_treaty';b['treatyAgreements']=[{'kind':'modern_treaty','label':b['treaty'],'status':'in_effect','sourceUrl':u,'verifiedAt':b['verifiedAt']}]
  if 'lower-post' in key:b['relatedIscBandNumbers']=[502];b['identityNote']='Lower Post community administration within Liard First Nation (ISC 502). No separate ISC band number is assigned; Liard registered population and leadership are not copied.'
  nations.append(b)
  for d in dispositions:
   if d['url']==u:d['disposition']='verified_separate_government';d['publishedId']=bid
  queue=[q for q in queue if q.get('url')!=u]
 # Reconcile the BCAFN map as a cross-check, not as a replacement identity roster.
 features=next(iter(read(CACHE/'bcafn-embedded.json')['leaflet'].values()))['features']
 reviewed=read(CACHE/'reviewed-bcafn-mappings.json')
 alias_evidence=read(CACHE/'bcafn-alias-evidence.json')
 current={str(b['id']):b for b in nations}
 for mapping in reviewed:
  b=current[str(mapping['id'])];e=alias_evidence[mapping['sourceUrl']]
  if mapping.get('sourceSha256')!=e['source']['sha256']:raise ValueError('Reviewed BCAFN alias evidence changed; re-review source before updating')
  b['aliases']=sorted(set(b['aliases']+[mapping['alias']])-{b['name']});b['sources'].append(source_record('regionalName',e['source']))
  if mapping.get('conflict'):queue.append({'id':b['id'],'sourceUrl':mapping['sourceUrl'],'reason':mapping['conflict'],'resolution':'Do not import the erroneous BC Website link; retain independent ISC identity and source-backed name.'})
 known={norm(a):b['id'] for b in nations for a in [b['name'],b['officialName']]+b['aliases']}
 bcafn=[]
 for f in features:
  fragment=html.fromstring(f['popup']['value']);url='https://www.bcafn.ca'+fragment.xpath('//a/@href')[0]
  if '/node/' in url:bcafn.append({'name':f['title'],'sourceUrl':url,'disposition':'region_navigation_point'});continue
  bid=known.get(norm(f['title']));bcafn.append({'name':f['title'],'sourceUrl':url,'publishedId':bid,'disposition':'reconciled_name' if bid is not None else 'identity_review'})
  if bid is None:queue.append({'name':f['title'],'sourceUrl':url,'reason':'BCAFN name not reconciled to a published identity'})
  elif f['title']=='Daylu Dena Council':
   b=current[str(bid)];b['location']={'longitude':f['lon'],'latitude':f['lat'],'sourceUrl':BCAFN,'retrievedAt':fetch(BCAFN)[1]['retrievedAt'],'locationType':'BCAFN representative community point; not a surveyed administrative office'};b['sources'].append(source_record('location',fetch(BCAFN)[1]))
 # West Moberly's provincial page is temporarily body-empty; ISC and historic treaty records verify its identity independently.
 for q in queue:
  if q.get('name')=='West Moberly First Nations':q['resolution']='Published using ISC identity/profile and historic treaty evidence; provincial body unavailable.'
 queue=list({json.dumps(q,sort_keys=True):q for q in queue}.values())
 # Import only explicit Website fields from government directory pages; retain disagreements.
 from tools.bc_provincial_evidence import content
 for b in nations:
  source=next((s for s in b['sources'] if s['field']=='provincialProfile'),None) or (next((s for s in b['sources'] if s['field']=='identity'),None) if not b.get('iscBandNumber') else None)
  if not source:continue
  document=content(payload(source));links=[]
  for paragraph in document.xpath('//p'):
   if re.match(r'web\s*site\s*:', ' '.join(paragraph.text_content().split()),re.I):links.extend(paragraph.xpath('.//a[@href]'))
  if not links:continue
  website=links[0].get('href')
  if not website.startswith(('https://','http://')):continue
  b['websiteCandidates']=[{'url':website,'sourceUrl':source['url'],'verifiedAt':source['retrievedAt']}]
  if not b.get('website'):
   b['website']=website;b['websiteSourceUrl']=source['url'];b.setdefault('contact',{})['website_url']=website;b['sources'].append(source_record('website',source))
  elif urlsplit(b['website']).netloc.lower().removeprefix('www.')!=urlsplit(website).netloc.lower().removeprefix('www.'):
   queue.append({'id':b['id'],'field':'website','candidates':[{'url':b['website'],'source':'ISC profile'},{'url':website,'sourceUrl':source['url']}],'reason':'Official directories list different website domains. Retain existing source-listed website and both candidates for review.'})
 # The Legislature lists five additional ancestral Douglas Treaty associations absent from the older ISC map.
 legislature='https://www.leg.bc.ca/learn/discover-your-legislature/1850-douglas-treaties'
 for bid in [647,649,631,624,724]:
  b=current[str(bid)];b['treatyReviewStatus']='Ancestral Douglas Treaty association requires scope reconciliation'
  queue.append({'id':bid,'field':'historicTreaty','sourceUrls':[HISTORIC,legislature],'reason':'Legislature lists ancestral Douglas Treaty association while the older ISC map labels this government non-signatory; no treaty assignment inferred from this disagreement.'})
 # Preserve the declared 199+2 identity denominator separately from overlapping governance levels.
 for b in nations:
  b.setdefault('logo_source',None);b.setdefault('logo_asset_source',None);b.setdefault('logo_status','logo_unverified')
  if b.get('location'):b['locations']=[copy.deepcopy(b['location'])]
  if b.get('contact'):
   phone=b['contact'].get('office_phone')
   if phone and not re.fullmatch(r'\(\d{3}\) \d{3}-\d{4}',phone):b['contact']['office_phone']=None
   if b['contact'].get('mailing_address') in ('Phone','Postal code','Fax','Address'):b['contact']['mailing_address']=None
  b['sources']=list({(s['field'],s['url']):s for s in b['sources']}.values())
  approvals=read(CACHE/'approved-logos.json') if (CACHE/'approved-logos.json').exists() else {}
  approval=approvals.get(str(b['id']))
  if approval:
   if not approval['review']['visually_verified'] or approval['review']['nation_name']!=b['name']:raise ValueError('Logo identity/review mismatch')
   asset=ROOT/approval['record']['logo_url'].lstrip('/')
   if hashlib.sha256(asset.read_bytes()).hexdigest()!=approval['record']['sha256']:raise ValueError('Approved logo asset changed')
   for key in ['logo_url','logo_source','logo_asset_source','logo_verified','logo_status']:b[key]=approval['record'][key]
   b['sources'].append(source_record('logo',approval['review']['source_page']))
  b['aliases']=sorted(set(b.get('aliases',[]))-{b['name']});b['regionalAffiliations']=list({x['name']:x for x in b.get('regionalAffiliations',[])}.values());b['geographicRegions']=list({x['name']:x for x in b.get('geographicRegions',[])}.values())
 result={'schemaVersion':1,'verifiedAt':max(b['verifiedAt'] for b in nations),'scope':'201 ISC-identified BC band/village governments (199 BC search results plus Dease River and Taku River Tlingit served by Yukon Region), plus three distinct national/community administrations. Governance levels overlap; this is not a count of non-overlapping Nations or populations. Regional/hereditary authority candidates remain separately reviewable.','iscIdentityCount':len([b for b in nations if b.get('iscBandNumber') is not None]),'publishedGovernmentProfileCount':len(nations),'rosterReconciliationComplete':False,'nations':sorted(nations,key=lambda b:b['name']),'sourceReferences':[ROSTER,PROVINCE,BCAFN,'https://bctreaty.ca/'],'reconciliation':dispositions,'manualReviewQueue':queue,'bcafnReconciliation':bcafn}
 from tools.merge_bc_enrichment import validate
 validate(result['nations'],read(ROOT/'data.json'))
 atomic_write(ROOT/'british-columbia-nations.json',result);atomic_write(CACHE/'manual-review-queue.json',queue);print('Publication-ready',len(nations),'profiles; ISC identities',201,'review items',len(queue))
 return result
if __name__=='__main__':build()
