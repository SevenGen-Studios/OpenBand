"""Shared source safety, identity, freshness and change tracking for public updates."""
from __future__ import annotations
import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import date, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit


def fold(value):
    text=unicodedata.normalize('NFKD',str(value or '')).lower().replace('&',' and ')
    return ' '.join(re.sub(r'[^a-z0-9]+',' ',''.join(c for c in text if not unicodedata.combining(c))).split())


def named_community(community, text):
    haystack=' '+fold(text)+' '
    names=[community.get('communityName'),*(community.get('aliases') or [])]
    return any(len(term:=fold(name))>=8 and ' '+term+' ' in haystack for name in names if name)


def association_allowed(community,source,title,context=''):
    if not source.get('requiresCommunityMention'):return True
    if named_community(community,title):return True
    matches={fold(name) for name in source.get('associationCommunityNames',[]) if len(fold(name))>=8 and ' '+fold(name)+' ' in ' '+fold(context)+' '}
    own={fold(name) for name in [community.get('communityName'),*(community.get('aliases') or [])] if name}
    return named_community(community,context) and not (matches-own)


def calendar_url(url):
    parts=urlsplit(url or '')
    return bool(re.search(r'/(?:events?|calendar)(?:[./-]|$)',parts.path,re.I) or re.search(r'(?:^|&)(?:eventid|event_id|tribe_events)=',parts.query,re.I))


class SourcePage(HTMLParser):
    def __init__(self,url):
        super().__init__(convert_charrefs=True);self.url=url;self.links=[];self.title=[];self.headings=[];self.text=[];self.capture=None;self.ignore=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('script','style','noscript'):self.ignore+=1
        if tag in ('title','h1'):self.capture=tag
        if tag=='link' and 'alternate' in a.get('rel','').lower() and any(v in a.get('type','').lower() for v in ('rss','atom','calendar')) and a.get('href'):
            target=urljoin(self.url,a['href'])
            if not re.search(r'comments?|reply', a.get('title','')+' '+urlsplit(target).path+' '+urlsplit(target).query,re.I):self.links.append(target)
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript'):self.ignore=max(0,self.ignore-1)
        if self.capture==tag:self.capture=None
    def handle_data(self,value):
        if self.ignore:return
        value=' '.join(value.split())
        if not value:return
        self.text.append(value)
        if self.capture=='title':self.title.append(value)
        if self.capture=='h1':self.headings.append(value)


def page_diagnostic(markup,url,community,source):
    p=SourcePage(url);p.feed(markup)
    identity=' '.join(p.title+p.headings+p.text[:35])
    if re.search(r'just a moment|attention required|access denied|checking your browser|enable javascript and cookies', ' '.join(p.title+p.headings),re.I):return 'access_restricted'
    if re.search(r'\b(?:casino|togel|slot gacor|sdy lotto|domain for sale|buy this domain)\b', ' '.join(p.title),re.I):
        return 'unrelated_or_parked_domain'
    if len(' '.join(p.text))<180 and re.search(r'<(?:div[^>]+id=["\'](?:root|app)|script[^>]+type=["\']module)',markup,re.I):
        return 'javascript_required'
    if source.get('status')=='candidate' and not source.get('requiresCommunityMention') and not named_community(community,identity):
        return 'source_identity_unconfirmed'
    return None


def feed_links(markup,url):
    p=SourcePage(url);p.feed(markup);host=(urlsplit(url).hostname or '').removeprefix('www.')
    return list(dict.fromkeys(u for u in p.links if urlsplit(u).scheme=='https' and (urlsplit(u).hostname or '').removeprefix('www.')==host))[:3]


def error_status(error):
    text=f'{type(error).__name__}: {error}'.lower()
    if 'certificate' in text or 'ssl' in text:return 'tls_error'
    if any(w in text for w in ('nodename','name or service not known','name resolution')):return 'dns_error'
    if 'robots' in text:return 'robots_blocked' if 'disallows' in text else 'robots_unavailable'
    if '401' in text or '403' in text:return 'access_restricted'
    if '404' in text or '410' in text:return 'not_found'
    if 'timed out' in text or 'timeout' in text:return 'timeout'
    return 'fetch_failed'


# Fields that affect what a follower would see; scan timestamps never trigger changes.
def content_fingerprint(item,kind='news'):
    fields=('title','publishedAt','summary','category','url') if kind=='news' else ('title','startDate','endDate','startTime','endTime','timeZone','location','description','category','sourceUrl','eventStatus')
    return hashlib.sha256(json.dumps({k:item.get(k) for k in fields},sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def track_changes(before,after,now,kind='news'):
    old={str(r.get('id')):r for r in before};changes=[]
    for row in after:
        key=str(row.get('id'));previous=old.get(key);fp=content_fingerprint(row,kind)
        row['contentFingerprint']=fp
        row['firstDiscoveredAt']=(previous or {}).get('firstDiscoveredAt') or (previous or {}).get('discoveredAt') or row.get('discoveredAt') or now
        row['lastCheckedAt']=now
        row['revision']=int((previous or {}).get('revision') or 1)
        changed=bool(previous) and content_fingerprint(previous,kind)!=fp
        if changed:row['revision']+=1
        row['updatedAt']=now if changed or not previous else previous.get('updatedAt') or row['firstDiscoveredAt']
        if changed or not previous:changes.append({'id':row['id'],'bandId':row.get('bandId'),'change':'updated' if changed else 'new','revision':row['revision'],'contentFingerprint':fp})
    return changes


def quality_metrics(registry,records,runs,reviews,today,kind='news'):
    today=today if isinstance(today,date) else date.fromisoformat(str(today)[:10]);rows=[]
    for community in registry.get('communities',[]):
        key=str(community['bandId']);items=[r for r in records if str(r.get('bandId'))==key]
        attempts=[r for r in runs if str(r.get('bandId'))==key]
        successful=[r for r in attempts if r.get('status') in ('ok','checked','partial') and r.get('pagesChecked',0)>0]
        pending=[r for r in reviews if str(r.get('bandId'))==key and r.get('status')!='extracted']
        dates=[str(r.get('publishedAt') or '') for r in items]
        upcoming=[r for r in items if str(r.get('endDate') or r.get('startDate') or '')>=today.isoformat() and r.get('eventStatus')!='cancelled']
        row={'bandId':community['bandId'],'communityName':community['communityName'],'provinceTerritory':community.get('provinceTerritory'),
             'workingSourcesThisRun':len(successful),'sourceAttemptsThisRun':len(attempts),'resultCount':len(items),'resultsLast30Days':sum((today-timedelta(days=30)).isoformat()<=d<=today.isoformat() for d in dates),
             'resultsLast90Days':sum((today-timedelta(days=90)).isoformat()<=d<=today.isoformat() for d in dates),'upcomingEvents':len(upcoming) if kind=='events' else 0,
             'manualReviewCount':len(pending),'needsSourceResearch':not any(s.get('monitor',True) and s.get('adapter') in {'html','rss','facebook'} and s.get('status') in {'candidate','verified','baseline'} for s in community.get('sources',[])),
             'discoveryState':'not_scanned' if not attempts else 'source_failure' if not successful else 'published_results' if items else 'checked_no_valid_dated_result'}
        rows.append(row)
    def summarize(rs):return {'communitiesTracked':len(rs),'communitiesWithWorkingSourcesThisRun':sum(r['workingSourcesThisRun']>0 for r in rs),'communitiesWithNewsLast30Days':sum(r['resultsLast30Days']>0 for r in rs),'communitiesWithNewsLast90Days':sum(r['resultsLast90Days']>0 for r in rs),'communitiesWithUpcomingEvents':sum(r['upcomingEvents']>0 for r in rs),'communitiesNeedingSourceResearch':sum(r['needsSourceResearch'] or r['discoveryState']=='source_failure' for r in rs)}
    return {'byProvince':{p:summarize([r for r in rows if r['provinceTerritory']==p]) for p in ('SK','AB','MB')},'communities':rows,
            'scanStatusCounts':dict(Counter(r.get('status','unknown') for r in runs)),
            'parserRejectionReasons':dict(Counter(str(r.get('reviewReason') or r.get('reason') or r.get('status') or 'Unspecified')[:180] for r in reviews if r.get('status')!='extracted')),
            'sourcesRequiringAuthentication':sum(r.get('status') in ('authorized_api_required','access_restricted') for r in runs),
            'note':'Working-source counts describe successful pages in this run, not merely registered websites. Empty results are not evidence that no community activity occurred.'}


def icalendar_records(payload):
    """Read explicit VEVENT values only; recurrence requires review, never guessed dates."""
    text=payload.decode('utf-8-sig',errors='replace') if isinstance(payload,bytes) else payload
    text=re.sub(r'\r?\n[ \t]','',text);items=[];rejected=[];current=None
    for line in text.splitlines():
        if line.strip()=='BEGIN:VEVENT':current={};continue
        if line.strip()=='END:VEVENT':
            if current:
                if 'RRULE' in current or 'RECURRENCE-ID' in current:rejected.append({'reason':'Recurring calendar event needs explicit occurrence expansion','uid':current.get('UID',{}).get('value')})
                else:items.append(current)
            current=None;continue
        if current is None or ':' not in line:continue
        key,value=line.split(':',1);pieces=key.split(';');name=pieces[0].upper()
        params=dict(p.split('=',1) for p in pieces[1:] if '=' in p)
        current[name]={'value':value.replace('\\n','\n').replace('\\,',',').replace('\\;', ';').replace('\\\\','\\'),'params':params}
    return items,rejected


def merge_update_reviews(previous,current,now):
    """Keep review history without duplicating the same finding on every scan."""
    result={}
    for row in [*(previous or []),*(current or [])]:
        original=row.get('originalRecord') or {};url=row.get('url') or row.get('sourceUrl') or original.get('url') or original.get('sourceUrl') or row.get('sourceName')
        key=(str(row.get('bandId') or original.get('bandId')),str(url),str(row.get('status')),str(row.get('reviewReason') or row.get('reason')))
        old=result.get(key,{})
        result[key]={**old,**row,'firstSeenAt':old.get('firstSeenAt') or row.get('firstSeenAt') or row.get('discoveredAt') or now,
                     'lastSeenAt':now if row in (current or []) else row.get('lastSeenAt') or now}
    return list(result.values())
