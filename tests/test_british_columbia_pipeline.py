import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools import bc_sources
from tools.bc_sources import ROOT,CACHE,read,atomic_write
from tools.merge_bc_enrichment import validate,preserved,merge_records,transaction,KEYS,IMMUTABLE
from tools.bc_profile import current_officials
from datetime import date

class BritishColumbiaPipeline(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.roster=read(ROOT/'british-columbia-nations.json');cls.data=read(ROOT/'data.json');cls.bc=[b for b in cls.data['bands'] if b.get('province')=='BC']
 def test_roster_scope_and_original_identifiers(self):
  self.assertEqual(len(self.bc),204);self.assertEqual(sum(b.get('iscBandNumber')is not None for b in self.bc),201)
  self.assertEqual({b['id'] for b in self.bc}, {b['id'] for b in self.roster['nations']});self.assertFalse(self.roster['rosterReconciliationComplete'])
  self.assertTrue(all(b['id']==b['iscBandNumber'] for b in self.bc if b.get('iscBandNumber')))
  self.assertEqual({b['id'] for b in self.bc if b.get('iscBandNumber')is None},{'bc-fnpo-9637','bc-haida-nation-council-of','bc-lower-post-first-nation-daylu-dena-council'})
  validate(self.roster['nations'],{'bands':[b for b in self.data['bands'] if b.get('province')!='BC']})
 def test_no_financial_collection_or_copied_totals(self):
  self.assertTrue(all(b['filings']==[] for b in self.roster['nations']))
  self.assertTrue(all(f.get('approval') for b in self.bc for f in b['filings']));self.assertTrue(all('population'not in b for b in self.bc if b.get('iscBandNumber')is None))
  with self.assertRaises(ValueError):bc_sources.fetch('https://services.sac-isc.gc.ca/fnp/main/Search/FederalFundingMain.aspx?BAND_NUMBER=604')
 def test_dated_population_and_source_coverage(self):
  for b in self.bc:
   for source in b['sources']:self.assertTrue(source['url'].startswith(('https://','http://')))
   if b.get('population'):
    p=b['population'];self.assertEqual(p['bandNumber'],b['iscBandNumber']);self.assertRegex(p['sourcePeriod'],r'\w+ 20\d\d');self.assertIn('registered population',p['definition'])
 def test_treaty_and_governance_distinctions(self):
  rows={b['id']:b for b in self.bc};self.assertEqual(rows[547]['treaty'],'Treaty 8');self.assertEqual(rows[640]['treaty'],'Douglas Treaties');self.assertIn('Maa-nulth',rows[663]['treaty']);self.assertIsNone(rows[624]['treaty']);self.assertTrue(rows[624]['treatyReviewStatus']);self.assertIsNone(rows[601]['treaty']);self.assertIn('Self-Government',rows[601]['governanceSystem']);self.assertTrue(all(b['treatyVerificationStatus']!='non_signatory' for b in self.bc))
 def test_exact_titles_and_current_term_filter(self):
  b=next(b for b in self.bc if b['id']==604);self.assertTrue(any(p['position']=='Chief Councillor' for p in current_officials(b,date(2026,11,17))))
  self.assertEqual(current_officials({'leadership':{'officials':[{'appointmentDate':'99/01/2026','expiryDate':'12/31/2026'}]}},date(2026,11,17)),[])
 def test_map_identity_partition_and_real_boundaries(self):
  ids={str(b['id']) for b in self.bc};maps=read(ROOT/'map-data.json');located={str(r['id']) for r in maps['communities'] if str(r['id'])in ids};missing={str(r['id']) for r in maps['missingLocations'] if str(r['id'])in ids}
  self.assertEqual(located|missing,ids);self.assertFalse(located&missing);self.assertEqual(len(located),202)
  geometry=read(ROOT/'public/reserve-boundaries.geojson');parcels={str(f['properties']['ADMIN_LAND_ID']) for f in geometry['features'] if f['properties'].get('CPC_CODE')=='BC'};self.assertEqual(len(parcels),1602)
  for r in maps['communities']:
   if str(r['id'])in ids:self.assertTrue(set(r.get('reserveLandIds',[]))<=parcels);self.assertTrue(-140<r['longitude']<-114);self.assertTrue(48<r['latitude']<61)
 def test_all_three_existing_provinces_preserved(self):
  current=preserved(ROOT);baseline=read(CACHE/'protected-baseline.json');current['files'].pop('capital-data.json');baseline['files'].pop('capital-data.json');self.assertEqual(current,baseline)
  from tools.ingest_bc import protect
  protect()
 def test_duplicate_and_cross_province_merges_rejected(self):
  with self.assertRaises(ValueError):validate(self.bc+[self.bc[0]],self.data)
  collision=copy.deepcopy(self.bc[0]);collision['id']=self.data['bands'][0]['id']
  with self.assertRaises(ValueError):validate([collision],self.data)
 def test_repeat_merge_and_unreviewed_changes(self):
  data={'bands':copy.deepcopy(self.roster['nations'])};before=copy.deepcopy(data);self.assertEqual(merge_records(data,copy.deepcopy(self.roster['nations'])),[]);self.assertEqual(data['bands'],before['bands'])
  candidate=copy.deepcopy(self.roster['nations'][0]);candidate['name']='Unreviewed change';self.assertTrue(merge_records(data,[candidate]));self.assertEqual(data['bands'][0],before['bands'][0])
 def test_atomic_preflight_and_rollback(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'public').mkdir();values={'data.json':{'bands':[{'id':1,'province':'SK','filings':[]}],'band_count':1},'map-data.json':{'communities':[{'id':1}]},'member-counts.json':{'bands':{'1':{'registeredMembers':10}}},'contacts-data.json':{'contacts':[{'nation_id':1}]},'first-nation-logos.json':{'logos':[{'nation_id':1}]},'first-nation-logo-report.json':[{'nation_id':1}],'public/reserve-boundaries.geojson':{'features':[]}}
   for name,value in values.items():atomic_write(root/name,value)
   for name in IMMUTABLE:atomic_write(root/name,{})
   baseline=preserved(root);bad=copy.deepcopy(values);bad['data.json']['bands'][0]['province']='BC'
   with self.assertRaises(ValueError):transaction(root,bad,baseline)
   updated=copy.deepcopy(values);updated['data.json']['bands'].append({'id':604,'province':'BC','filings':[]});updated['map-data.json']['communities'].append({'id':604})
   original={name:(root/name).read_bytes() for name in updated};real_replace=__import__('os').replace;attempt=[0]
   def fail_once(src,dst):
    if Path(dst) in (root/'data.json',root/'map-data.json'):
     attempt[0]+=1
     if attempt[0]==2:raise OSError('Simulated interrupted transaction')
    return real_replace(src,dst)
   with patch('tools.merge_bc_enrichment.os.replace',side_effect=fail_once):
    with self.assertRaises(OSError):transaction(root,updated,baseline)
   self.assertEqual(original,{name:(root/name).read_bytes() for name in updated})

if __name__=='__main__':unittest.main()
