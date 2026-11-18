"""Extract and cache BC A-Z profile evidence; this is not identity guessing."""
import html as stdhtml,re
from urllib.parse import urljoin,parse_qs,urlsplit
from lxml import html
from tools.bc_sources import *

def content(payload):
 doc=html.fromstring(payload.decode('utf-8-sig'));scripts=doc.xpath('//script[@id="__NEXT_DATA__"]')
 if not scripts:return doc
 data=json.loads(scripts[0].text);parts=[]
 def walk(x):
  if isinstance(x,dict):
   if 'value' in x and isinstance(x['value'],str) and len(x['value'])>150 and ('&lt;p' in x['value'] or '<p' in x['value'] or '&lt;table' in x['value']):parts.append(stdhtml.unescape(x['value']))
   for k,v in x.items():
    if k not in ('navigation','breadcrumbs'):walk(v)
  elif isinstance(x,list):
   for v in x:walk(v)
 walk(data['props']['pageProps']['data']['results'][0]['components'])
 return html.fromstring('<div>'+''.join(parts)+'</div>')

def build(refresh=False):
 out=CACHE/'province-evidence.json';saved=read(out) if out.exists() else {};rows=read(CACHE/'provincial-candidates.json')
 for i,r in enumerate(rows,1):
  url=r['url']
  if not url.startswith(PROVINCE+'/') or (url in saved and not refresh):continue
  try:
   p,m=fetch(url,refresh);d=content(p);text=' '.join(d.text_content().split());ids=[];links=[]
   for a in d.xpath('//a[@href]'):
    u=urljoin(url,a.get('href'));label=' '.join(a.text_content().split());links.append({'label':label,'url':u})
    if label.lower() in ('profile','first nation profile','inac profile'):
     q={k.lower():v for k,v in parse_qs(urlsplit(u).query).items()}
     if 'band_number' in q:ids.extend(int(x) for x in q['band_number'] if x.isdigit())
   saved[url]={'name':r['name'],'source':m,'text':text,'links':links,'iscBandNumbers':sorted(set(ids))};atomic_write(out,saved);print(f'{i}/{len(rows)} {r["name"]}: ISC {sorted(set(ids))}',flush=True)
  except Exception as e:saved[url]={'name':r['name'],'source':{'url':url},'error':str(e)};atomic_write(out,saved);print(r['name'],str(e),flush=True)
 return saved
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--refresh',action='store_true');a=p.parse_args();build(a.refresh)
