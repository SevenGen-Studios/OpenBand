"""Search source-listed BC government sites for logo candidates; no automatic approvals."""
import argparse,json
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.parse import urlsplit,urlunsplit
from urllib.error import HTTPError
from urllib.robotparser import RobotFileParser
from tools.bc_sources import *
from tools.collect_first_nation_logos import LogoHTMLParser,candidate_score,official_site_matches

def search(band):
 result={'id':band['id'],'name':band['name'],'website':band.get('website'),'logo_verified':False,'status':'no_verified_website','candidates':[]}
 if not band.get('website'):return result
 site=band['website'];parts=urlsplit(site);robots=urlunsplit((parts.scheme,parts.netloc,'/robots.txt','',''));parser=RobotFileParser()
 try:
  p,m=fetch(robots,timeout=8);parser.parse(p.decode('utf-8',errors='replace').splitlines())
  if not parser.can_fetch('OpenBand',site):return {**result,'status':'robots_restricted','source':m}
 except HTTPError as e:
  if e.code not in (404,410):return {**result,'status':'robots_inaccessible','error':str(e)}
 except Exception as e:return {**result,'status':'robots_inaccessible','error':str(e)}
 try:
  payload,meta=fetch(site,timeout=10);doc=LogoHTMLParser(meta['finalUrl']);doc.feed(payload.decode('utf-8',errors='replace'));seen={}
  for c in doc.candidates:
   score=candidate_score(c,band['name'])
   if score>=35 and not c['url'].startswith('data:'):seen[c['url']]={**c,'score':score}
  result.update(status='candidates_await_visual_review' if seen else 'no_attributable_candidate',source=meta,identityTextMatches=official_site_matches(doc,band['name']),candidates=sorted(seen.values(),key=lambda c:c['score'],reverse=True)[:8])
 except Exception as e:result.update(status='site_inaccessible',error=str(e))
 return result

def build(workers=3):
 path=CACHE/'logo-searches.json';saved=read(path) if path.exists() else {};nations=read(ROOT/'british-columbia-nations.json')['nations'];todo=[b for b in nations if str(b['id'])not in saved or (saved[str(b['id'])].get('status')=='no_verified_website' and b.get('website'))]
 with ThreadPoolExecutor(max_workers=workers) as pool:
  futures={pool.submit(search,b):b for b in todo}
  for future in as_completed(futures):
   b=futures[future];saved[str(b['id'])]=future.result();atomic_write(path,saved);print(len(saved),b['name'],saved[str(b['id'])]['status'],flush=True)
 return saved
if __name__=='__main__':build()
