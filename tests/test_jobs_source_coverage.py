import json,tempfile,unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch
from tools.jobs_collector import collect,JobCardCollector,career_card_candidates,source_check_metadata,community_coverage_status,source_coverage
TODAY=date(2026,10,11)
CARD='<div class="fl-post-grid-post"><meta itemprop="mainEntityOfPage" content="Assistant Controller" itemid="https://example.org/careers/controller/"><meta itemprop="datePublished" content="2026-09-14"><div class="company_name">Nation Business</div><h3>Assistant Controller</h3><a href="/careers/controller/">View opportunity »</a></div>'
class SourceCoverageTests(unittest.TestCase):
 def test_card_titles_are_not_generic_link_labels(self):
  p=JobCardCollector();p.feed(CARD);self.assertEqual(p.cards,[{'title':'Assistant Controller','url':'https://example.org/careers/controller/','postedDate':'2026-09-14','employer':'Nation Business'}])
 def test_only_recent_verified_cards_with_live_forms_publish(self):
  source={'id':'source','url':'https://example.org/careers/','name':'Nation Careers','communityIds':['1'],'verifiedOfficialSource':True,'publishCurrentCards':True}
  detail={'detailText':'Assistant Controller Apply Now','acceptingApplications':True,'status':'Pending verification'}
  with patch('tools.jobs_collector.inspect_candidate_page',return_value=(detail,[])):
   rows,_=career_card_candidates(CARD,source,TODAY);self.assertEqual(rows[0]['status'],'Date unavailable')
   rows,_=career_card_candidates(CARD.replace('2026-09-14','2024-09-14'),source,TODAY);self.assertEqual(rows[0]['status'],'Pending verification')
   rows,_=career_card_candidates(CARD,{**source,'verifiedOfficialSource':False},TODAY);self.assertEqual(rows[0]['status'],'Pending verification')
   rows,_=career_card_candidates(CARD.replace('example.org/careers/controller','evil.example/careers/controller'),source,TODAY);self.assertEqual(rows,[])
  with patch('tools.jobs_collector.inspect_candidate_page',return_value=({**detail,'status':'Closed'},[])):
   self.assertEqual(career_card_candidates(CARD,source,TODAY)[0][0]['status'],'Closed')
  with patch('tools.jobs_collector.inspect_candidate_page',return_value=({**detail,'acceptingApplications':False},[])):
   self.assertEqual(career_card_candidates(CARD,source,TODAY)[0][0]['status'],'Pending verification')
 def test_configured_is_not_checked_and_outages_are_visible(self):
  source={'id':'s','url':'https://example.org/jobs'}
  meta=source_check_metadata(source,{},TODAY);self.assertEqual(meta['checkStatus'],'not_checked')
  self.assertEqual(community_coverage_status([meta],False),'sources_not_checked')
  self.assertEqual(source_check_metadata(source,{'s':{'url':source['url'],'status':'checked','lastChecked':'2026-08-01'}},TODAY)['checkStatus'],'stale')
  meta=source_check_metadata(source,{'s':{'url':source['url'],'status':'unavailable','lastAttempted':'2026-10-11','lastChecked':'2026-10-10'}},TODAY)
  self.assertEqual(meta['lastChecked'],'2026-10-10');self.assertEqual(community_coverage_status([meta],False),'sources_unavailable')
 def test_partial_scan_preserves_checks_and_offline_never_invents_checks(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);sources=[{'id':'s','name':'Source','url':'https://example.org/jobs','communityIds':['1']}]
   (root/'data.json').write_text(json.dumps({'bands':[{'id':1,'name':'Nation'}]}))
   (root/'jobs-source-registry.json').write_text(json.dumps({'generated':'2026-10-10T12:00:00Z','sourceRuns':[{'sourceId':'s','url':sources[0]['url'],'status':'checked'}]}))
   with patch('tools.jobs_collector.configured_sources',return_value=sources):
    data,report=collect(root,TODAY,offline=True)
    self.assertEqual(data['communityCoverage'][0]['lastChecked'],'2026-10-10');self.assertEqual(report['sourcesChecked'],0)
    with patch('tools.jobs_collector.fetch_source',return_value=([],['Unavailable'],'',[])):
     data,report=collect(root,TODAY)
    self.assertEqual(data['communityCoverage'][0]['status'],'sources_unavailable');self.assertEqual(data['communityCoverage'][0]['lastChecked'],'2026-10-10')
    self.assertEqual(report['sourcesSuccessfullyChecked'],0);self.assertEqual(len(report['_sourceRegistry']['sourceRunHistory']),2)
 def test_provincial_source_does_not_claim_other_province(self):
  self.assertEqual(source_coverage({'coversAllTrackedCommunities':True,'province':'SK'},{'1','2'},{'1':'SK','2':'AB'}),{'1'})
