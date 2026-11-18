"""Phase 2-only BC merges with preflight, backups, atomic replacement and rollback."""
import copy,hashlib,os,tempfile,shutil
from pathlib import Path
from contextlib import contextmanager
from tools.bc_sources import ROOT,CACHE,read,atomic_write,now
KEYS={'data.json':('bands','id'),'map-data.json':('communities','id'),'member-counts.json':('bands',None),'contacts-data.json':('contacts','nation_id'),'first-nation-logos.json':('logos','nation_id')}
IMMUTABLE=['capital-data.json','elections-data.json','history-data.json','community-enterprise.json']
def digest(v):
 import json
 return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def preserved(root,values=None):
 values=values or {};data=values.get('data.json') or read(root/'data.json');ids={str(b['id']) for b in data['bands'] if b['province']!='BC'};out={'protectedIds':sorted(ids),'records':{},'files':{}}
 for name,(key,idkey) in KEYS.items():
  v=values.get(name) or read(root/name);rows=v[key]
  selected={str(k):v for k,v in rows.items() if str(k) in ids} if idkey is None else [r for r in rows if str(r[idkey]) in ids]
  out['records'][name]=digest(selected)
 if (root/'public/reserve-boundaries.geojson').exists():out['records']['boundaries']=digest([f for f in (values.get('public/reserve-boundaries.geojson') or read(root/'public/reserve-boundaries.geojson'))['features'] if f['properties'].get('CPC_CODE')!='BC'])
 for name in IMMUTABLE:
  if (root/name).exists():out['files'][name]=hashlib.sha256((root/name).read_bytes()).hexdigest()
 report=values.get('first-nation-logo-report.json') or read(root/'first-nation-logo-report.json');out['records']['first-nation-logo-report.json']=digest([r for r in report if str(r['nation_id']) in ids])
 geometry=values.get('public/reserve-boundaries.geojson') or read(root/'public/reserve-boundaries.geojson');out['protectedGeometry']=digest([f for f in geometry['features'] if f['properties'].get('CPC_CODE')!='BC'])
 return out

def validate(nations,existing):
 ids=[str(n['id']) for n in nations];numbers=[n['iscBandNumber'] for n in nations if n.get('iscBandNumber') is not None]
 if len(ids)!=len(set(ids)) or len(numbers)!=len(set(numbers)):raise ValueError('Duplicate BC identity')
 oldids={str(b['id']):b for b in existing['bands']};oldnumbers={b.get('iscBandNumber'):b for b in existing['bands'] if b.get('province')!='BC' and b.get('iscBandNumber')}
 for n in nations:
  if n.get('province')!='BC' or n.get('filings')!=[]:raise ValueError('BC Phase 2 records must have empty filing arrays')
  if n.get('verificationStatus') not in ('verified_isc_identity','verified_government_identity') or not n.get('sources') or not n.get('verifiedAt'):raise ValueError('Unverified BC government')
  if n.get('iscBandNumber') is not None and (type(n['iscBandNumber']) is not int or n['iscBandNumber'] in oldnumbers):raise ValueError('Protected ISC number collision')
  if str(n['id']) in oldids and oldids[str(n['id'])].get('province')!='BC':raise ValueError('Protected application ID collision')
  if n.get('population') and (not n['population'].get('sourcePeriod') or not n['population'].get('sourceUrl')):raise ValueError('Population without period/source')

def merge_records(existing,incoming,accept_reviewed=False):
 """Never overwrite a previously verified BC field with a conflicting candidate."""
 old={str(b['id']):b for b in existing['bands']};conflicts=[]
 for n in incoming:
  prior=old.get(str(n['id']))
  if prior and prior.get('filings'):raise ValueError('Phase 2 cannot replace an existing BC financial record')
  if prior and prior!=n and accept_reviewed:
   merged={**prior,**copy.deepcopy(n)};merged['sources']=list({(s['field'],s['url']):s for s in prior.get('sources',[])+n.get('sources',[])}.values());prior.clear();prior.update(merged);continue
  if prior and prior!=n:
   conflicts.append({'id':n['id'],'reason':'Existing BC record differs; explicit field/source review required before replacement'})
   continue
  if not prior:existing['bands'].append(copy.deepcopy(n))
 existing['band_count']=len(existing['bands']);return conflicts

@contextmanager
def writer_lock(root=ROOT):
 path=root/'.openband-ocr/bc-phase2/writer.lock';path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('a+b') as f:
  if os.name=='nt':
   import msvcrt
   f.seek(0);f.write(b'0');f.flush();f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
  else:
   import fcntl
   fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  try:yield
  finally:
   if os.name=='nt':f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
   else:fcntl.flock(f,fcntl.LOCK_UN)

def transaction(root,values,baseline):
 if preserved(root,values)!=baseline:raise ValueError('Protected provincial data would change')
 backup=root/'.openband-ocr/bc-phase2/backups';backup.mkdir(parents=True,exist_ok=True);prepared={};original={};written=[]
 import json
 try:
  for name,value in values.items():
   path=root/name;original[name]=path.read_bytes();payload=(json.dumps(value,ensure_ascii=False,indent=None if name.endswith('.geojson') else 2,separators=(',',':') if name.endswith('.geojson') else None)+'\n').encode()
   if original[name]==payload:continue
   saved=backup/(hashlib.sha256(original[name]).hexdigest()+'.json');saved.write_bytes(original[name])
   with tempfile.NamedTemporaryFile('wb',prefix='.bc-phase2-',dir=path.parent,delete=False) as f:f.write(payload);f.flush();os.fsync(f.fileno());prepared[name]=Path(f.name)
  atomic_write(backup/'transaction.json',{'state':'prepared','files':list(prepared),'startedAt':now()})
  for name,tmp in prepared.items():os.replace(tmp,root/name);written.append(name)
  if preserved(root)!=baseline:raise ValueError('Post-write preservation mismatch')
  atomic_write(backup/'transaction.json',{'state':'committed','files':written,'completedAt':now()})
 except Exception:
  for name in reversed(written):
   with tempfile.NamedTemporaryFile('wb',dir=(root/name).parent,delete=False) as f:f.write(original[name]);restore=f.name
   os.replace(restore,root/name)
  raise
 finally:
  for p in prepared.values():
   if p.exists():p.unlink()

def build(accept_reviewed=False):
 from tools.build_map_data import LOCATION_URL,boundary_ids
 nations=read(ROOT/'british-columbia-nations.json')['nations'];values={n:read(ROOT/n) for n in [*KEYS,'first-nation-logo-report.json']}
 validate(nations,values['data.json']);baseline_path=CACHE/'protected-baseline.json'
 with writer_lock():
  baseline=read(baseline_path) if baseline_path.exists() else preserved(ROOT)
  if preserved(ROOT)!=baseline:raise ValueError('Protected datasets changed since baseline')
  if not baseline_path.exists():atomic_write(baseline_path,baseline)
  conflicts=merge_records(values['data.json'],nations,accept_reviewed)
  if conflicts:atomic_write(CACHE/'merge-conflicts.json',conflicts);raise ValueError('BC field conflicts require review')
  maps=values['map-data.json'];members=values['member-counts.json'];contacts=values['contacts-data.json'];logos=values['first-nation-logos.json']
  geo_source=CACHE/'bc-boundaries-source.json';geo=None
  if geo_source.exists() or geo_source.with_suffix('.json.gz').exists():
   from tools.build_reserve_boundaries import validated_display_features
   source=read(geo_source);report={'repairs':[],'blocked':[]};added=validated_display_features(source,report)
   current=read(ROOT/'public/reserve-boundaries.geojson');old=[f for f in current['features'] if f['properties'].get('CPC_CODE')!='BC'];combined=old+added
   parcel_ids=[str(f['properties']['ADMIN_LAND_ID']) for f in combined]
   if len(parcel_ids)!=len(set(parcel_ids)):raise ValueError('Parcel identifier collision')
   geo={**current,'features':combined,'sourceUrls':list(dict.fromkeys(current.get('sourceUrls',[current['sourceUrl']])+[s['url'] for s in source['sources']]))};values['public/reserve-boundaries.geojson']=geo
   atomic_write(CACHE/'boundary-validation.json',{**report,'verifiedBCParcels':len(added),'sourceUrls':[s['url'] for s in source['sources']]})
  for n in nations:
   bid=str(n['id']);loc=n.get('location');pop=n.get('population');contact={'office_phone':None,'website_url':n.get('website'),'mailing_address':None,**(n.get('contact') or {})}
   if pop:members['bands'][bid]={**pop,'name':n['name'],'sourceName':'Indigenous Services Canada','sourceYear':pop['sourcePeriod'],'lastChecked':pop['retrievedAt'][:10],'notes':pop['definition']}
   if contact and not any(str(c['nation_id'])==bid for c in contacts['contacts']):contacts['contacts'].append({'nation_id':n['id'],'nation_name':n['name'],**contact,'office_email':None,'source_url':next((s['url'] for s in n['sources'] if s['field']=='profile'),next(s['url'] for s in n['sources'] if s['field']=='identity')),'last_verified':n['verifiedAt'][:10]})
   existing_contact=next((c for c in contacts['contacts'] if str(c['nation_id'])==bid),None)
   if existing_contact:
    for field in ['office_phone','mailing_address']:existing_contact[field]=contact.get(field)
   if existing_contact and not existing_contact.get('website_url') and n.get('website'):
    existing_contact['website_url']=n['website'];existing_contact.setdefault('field_sources',{})['website_url']=n.get('websiteSourceUrl') or existing_contact['source_url']
   if not any(str(c['nation_id'])==bid for c in logos['logos']):logos['logos'].append({'nation_id':n['id'],'nation_name':n['name'],'slug':__import__('tools.build_site',fromlist=['slugify']).slugify(n['name']),'logo_url':None,'logo_source':None,'logo_asset_source':None,'logo_verified':False,'logo_status':'logo_unverified','verification_note':'Official logo not yet source/asset verified; display OpenBand initials.'})
   if not loc:
    if not any(str(c['id'])==bid for c in maps['missingLocations']):maps['missingLocations'].append({'id':n['id'],'name':n['name'],'reason':'No verified coordinates for this government'})
    continue
   if not(-140<=loc['longitude']<=-114 and 48<=loc['latitude']<=61):raise ValueError('Unexpected BC coordinate range')
   maps['missingLocations']=[c for c in maps['missingLocations'] if str(c['id'])!=bid]
   verified_locations=n.get('locations') or [loc]
   for point in verified_locations:
    if not point.get('sourceUrl') or not point.get('retrievedAt') or not(-140<=point['longitude']<=-114 and 48<=point['latitude']<=61):raise ValueError('Unverified additional community location')
   previous_location=next((c for c in maps['communities'] if str(c['id'])==bid),None)
   if previous_location:previous_location['locations']=copy.deepcopy(verified_locations);continue
   row={'id':n['id'],'name':n['name'],'province':'BC','latitude':loc['latitude'],'longitude':loc['longitude'],'locations':copy.deepcopy(verified_locations),'locationSourceUrl':loc['sourceUrl'],'locationCheckedAt':loc['retrievedAt'],'treaty':n.get('treaty'),'tribalCouncil':n.get('tribalCouncil'),'reserveOwnerNames':[n['officialName']]}
   if geo and n.get('reserves'):
    row['reserveOwnerNames']=[n['officialName']];row['reserveLandIds']=boundary_ids(n,row,[f for f in geo['features'] if f['properties'].get('CPC_CODE')=='BC']);row['reserveBoundarySourceUrl']=source['sources'][0]['url'];row['reserveBoundaryCheckedAt']=n['verifiedAt']
   maps['communities'].append(row)
  for logo in logos['logos']:
   if str(logo['nation_id']) in {str(n['id']) for n in nations}:logo.setdefault('logo_source',None);logo.setdefault('logo_asset_source',None)
  approvals=read(CACHE/'approved-logos.json') if (CACHE/'approved-logos.json').exists() else {}
  for logo in logos['logos']:
   approval=approvals.get(str(logo['nation_id']))
   if approval:
    if not approval['review']['visually_verified'] or approval['review']['nation_name']!=logo['nation_name']:raise ValueError('Unreviewed/wrong-government logo')
    asset=ROOT/approval['record']['logo_url'].lstrip('/')
    if hashlib.sha256(asset.read_bytes()).hexdigest()!=approval['record']['sha256']:raise ValueError('Reviewed logo hash mismatch')
    logo.update(approval['record'])
  report=values['first-nation-logo-report.json'];existing_report_ids={str(r['nation_id']) for r in report}
  report.extend({**r,'website_url':next((n.get('website') for n in nations if str(n['id'])==str(r['nation_id'])),None)} for r in logos['logos'] if str(r['nation_id']) not in existing_report_ids)
  for row in report:
   approval=approvals.get(str(row['nation_id']))
   if approval:row.update(approval['record'])
  logos['verifiedCount']=sum(bool(r['logo_verified']) for r in logos['logos']);logos['unverifiedCount']=len(logos['logos'])-logos['verifiedCount']
  for c in contacts['contacts']:
   if str(c['nation_id']) in {str(n['id']) for n in nations}:c.setdefault('field_sources',{k:c['source_url'] if c.get(k) else None for k in ['office_phone','office_email','website_url','mailing_address']})
  maps['communityCount']=len(maps['communities']);contacts['recordCount']=len(contacts['contacts']);logos['recordCount']=len(logos['logos']);logos['verifiedCount']=sum(bool(r['logo_verified']) for r in logos['logos']);logos['unverifiedCount']=len(logos['logos'])-logos['verifiedCount']
  for logo in logos['logos']:
   if str(logo['nation_id']) in {str(n['id']) for n in nations}:logo.setdefault('logo_source',None);logo.setdefault('logo_asset_source',None)
  approvals=read(CACHE/'approved-logos.json') if (CACHE/'approved-logos.json').exists() else {}
  for logo in logos['logos']:
   approval=approvals.get(str(logo['nation_id']))
   if approval:
    if not approval['review']['visually_verified'] or approval['review']['nation_name']!=logo['nation_name']:raise ValueError('Unreviewed/wrong-government logo')
    asset=ROOT/approval['record']['logo_url'].lstrip('/')
    if hashlib.sha256(asset.read_bytes()).hexdigest()!=approval['record']['sha256']:raise ValueError('Reviewed logo hash mismatch')
    logo.update(approval['record'])
  report=values['first-nation-logo-report.json'];existing_report_ids={str(r['nation_id']) for r in report}
  report.extend({**r,'website_url':next((n.get('website') for n in nations if str(n['id'])==str(r['nation_id'])),None)} for r in logos['logos'] if str(r['nation_id']) not in existing_report_ids)
  for row in report:
   approval=approvals.get(str(row['nation_id']))
   if approval:row.update(approval['record'])
  logos['verifiedCount']=sum(bool(r['logo_verified']) for r in logos['logos']);logos['unverifiedCount']=len(logos['logos'])-logos['verifiedCount']
  for c in contacts['contacts']:
   if str(c['nation_id']) in {str(n['id']) for n in nations}:c.setdefault('field_sources',{k:c['source_url'] if c.get(k) else None for k in ['office_phone','office_email','website_url','mailing_address']})
  maps['communityCount']=len(maps['communities']);contacts['recordCount']=len(contacts['contacts']);contacts['emailCount']=sum(bool(c.get('office_email')) for c in contacts['contacts']);contacts['phoneCount']=sum(bool(c.get('office_phone')) for c in contacts['contacts']);contacts['websiteCount']=sum(bool(c.get('website_url')) for c in contacts['contacts']);contacts['mailingAddressCount']=sum(bool(c.get('mailing_address')) for c in contacts['contacts']);logos['recordCount']=len(logos['logos'])
  transaction(ROOT,values,baseline)
 print('Integrated',len(nations),'BC profiles; protected provincial records unchanged')
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--accept-reviewed-update',action='store_true');args=parser.parse_args();build(args.accept_reviewed_update)
