import gzip
import json
import unittest
from copy import deepcopy
from datetime import date
from pathlib import Path
from tools.apply_community_enrichment import validate
from tools.news_discovery import article_metadata_with_api, wordpress_publication_date, prune_invalid_generated_articles

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'research/community-intelligence/wider-2026-11-27'

class WiderCoverageTests(unittest.TestCase):
    def test_batch_validates_and_news_survives_collection(self):
        roster={str(b['id']) for b in json.loads((ROOT/'data.json').read_text())['bands']}
        for entry in json.loads((FOLDER/'reviewed-enrichment.json').read_text())['records']:
            validate(entry,roster,{},ROOT,date(2026,11,27))
            if entry['kind']=='news':
                retained,removed=prune_invalid_generated_articles([entry['record']],date(2026,11,27))
                self.assertEqual(retained,[entry['record']]);self.assertFalse(removed)

    def test_public_api_preserves_publication_not_modification(self):
        urls=json.loads((FOLDER/'source-urls.json').read_text())
        payload=json.loads(gzip.decompress((FOLDER/'scn-election-api.html.gz').read_bytes()))
        article,api=urls['scn-election'],urls['scn-election-api']
        self.assertEqual(wordpress_publication_date(payload,article,api),'2026-11-03')
        for changed in [dict(payload,status='draft'),dict(payload,id=999),dict(payload,link=urls['scn-q3']),dict(payload,date_gmt=None,date=None)]:
            self.assertIsNone(wordpress_publication_date(changed,article,api))
        self.assertIsNone(wordpress_publication_date(payload,article,api.replace('scn314.com','example.test')))
        self.assertIsNone(wordpress_publication_date(payload,article,api+'?context=edit'))

    def test_collector_uses_only_advertised_same_origin_post(self):
        urls=json.loads((FOLDER/'source-urls.json').read_text())
        markup=gzip.decompress((FOLDER/'scn-election.html.gz').read_bytes()).decode()
        payload=gzip.decompress((FOLDER/'scn-election-api.html.gz').read_bytes())
        class Fetch:
            calls=[]
            def get(self,url):
                self.calls.append(url)
                return payload,url,'application/json'
        fetch=Fetch();result=article_metadata_with_api(fetch,markup,urls['scn-election'])
        self.assertEqual(result['published'],'2026-11-03')
        self.assertEqual(fetch.calls,[urls['scn-election-api']])
        foreign=markup.replace(urls['scn-election-api'],urls['scn-election-api'].replace('scn314.com','example.test'))
        fetch.calls=[];result=article_metadata_with_api(fetch,foreign,urls['scn-election'])
        self.assertFalse(fetch.calls);self.assertIsNone(result['published'])

    def test_review_rejects_modified_date_and_missing_api_proof(self):
        roster={str(b['id']) for b in json.loads((ROOT/'data.json').read_text())['bands']}
        entry=next(e for e in json.loads((FOLDER/'reviewed-enrichment.json').read_text())['records'] if e['record']['id'].startswith('scn-election-'))
        changed=deepcopy(entry);changed['record']['publishedAt']='2026-11-11'
        with self.assertRaises(ValueError):validate(changed,roster,{},ROOT,date(2026,11,27))
        changed=deepcopy(entry);changed.pop('publicationEvidenceUrl')
        with self.assertRaises(ValueError):validate(changed,roster,{},ROOT,date(2026,11,27))

    def test_assessment_completion_is_not_building_completion(self):
        records=json.loads((FOLDER/'reviewed-enrichment.json').read_text())['records']
        lodge=next(e['record'] for e in records if e['record']['id']=='dakota-lodge-288-reviewed')
        self.assertEqual(lodge['status'],'Planned')
        self.assertIn('not construction',lodge['description'])
