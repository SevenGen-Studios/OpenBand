"""Revalidate public update records and produce a reproducible Phase 1 coverage audit.

No network requests. The scan reports retain actual per-source outcomes; absence of
an article is never translated into a claim of no community activity.
"""
import argparse
import gzip
import json
from pathlib import Path
from urllib.parse import urlsplit
from tools import news_discovery as news, events_discovery as events
from tools.community_updates import association_allowed, quality_metrics, track_changes, merge_update_reviews, content_fingerprint
ROOT=news.ROOT
RESEARCH=ROOT/'research/community-intelligence/2026-11-02'


def baseline(name):
    with gzip.open(RESEARCH/'before'/(name+'.gz'),'rt') as handle:return json.load(handle)


def source_runs(kind,current):
    original=news.load_json(RESEARCH/f'{kind}-full-scan.json',{})
    rows={}
    for row in [*original.get('sourceRuns',[]),*current.get('sourceRuns',[])]:
        key=(str(row.get('bandId')),news.canonical_url(row.get('url') or row.get('sourceUrl')))
        rows[key]=row
    return list(rows.values())


def audit(revalidate=False):
    data=news.load_json(news.DATA_PATH,{})
    output=news.load_json(news.NEWS_PATH,{})
    registry=news.ensure_registry(data,output,news.load_json(news.REGISTRY_PATH,{}))
    communities={str(r['bandId']):r for r in registry['communities']}
    now=news.iso_now();today=news.utc_now().date()
    old_news=json.loads(json.dumps(output.get('articles',[])))
    news_review=news.load_json(news.REVIEW_PATH,{}).get('items',[])
    news_report=news.load_json(news.REPORT_PATH,{})
    event_output=news.load_json(events.EVENTS_PATH,{})
    old_events=json.loads(json.dumps(event_output.get('events',[])))
    event_review=news.load_json(events.REVIEW_PATH,{}).get('items',[])
    event_report=news.load_json(events.REPORT_PATH,{})
    if revalidate:
        retained,removed=news.prune_invalid_generated_articles(old_news,today)
        for row in removed:news_review.append({**row,'status':'historical_record_held','originalRecord':next((r for r in old_news if r.get('url')==row.get('url') and str(r.get('bandId'))==str(row.get('bandId'))),None)})
        rows=[]
        for row in retained:
            community=communities.get(str(row.get('bandId')))
            if not community:
                news_review.append({'status':'identity_review','reason':'Record has no current community identifier','originalRecord':row});continue
            host=(urlsplit(row.get('url','')).hostname or '').removeprefix('www.')
            source=next((s for s in community['sources'] if (urlsplit(s.get('url','')).hostname or '').removeprefix('www.')==host),None)
            if source and source.get('requiresCommunityMention') and not association_allowed(community,source,row.get('title'),row.get('summary','')):
                news_review.append({'bandId':row['bandId'],'url':row.get('url'),'status':'identity_review','reason':'Shared publisher record does not explicitly establish this community association','originalRecord':row});continue
            if source and source.get('requiresCommunityMention'):
                row['sourceType']=source['type'];row['associationScope']='explicit-community-mention';row['communityConfidence']=news.source_confidence(source)
            if row.get('extractionMethod') and row.get('categorySource')!='manual':row['category']=news.classify_category(row.get('title'),row.get('summary',''))
            rows.append(row)
        output['articles']=news.merge_articles([],rows)[0]
        news_changes=track_changes(old_news,output['articles'],now)
        output['communitySources']=news.registry_for_frontend(registry)
        output['generated']=now
        for row in old_events:
            if row.get('categorySource')!='manual':row['category']=events.event_category(row.get('title'),row.get('description',''))
            if not row.get('endDate') and row.get('extractionMethod') not in {'json-ld','icalendar'}:
                ranges=events.explicit_written_ranges(f"{row.get('title','')} {row.get('description','')}")
                matched=next((r for r in ranges if r[0]==row.get('startDate')),None)
                if matched:row['endDate']=matched[1]
            if not events.is_publishable_event(row,today):event_review.append({'bandId':row.get('bandId'),'sourceUrl':row.get('sourceUrl'),'status':'historical_record_held','reason':'Record failed explicit event-date/permalink validation','originalRecord':row})
        event_output['events']=events.merge_events(old_events,[],today)
        event_changes=track_changes(news.load_json(events.EVENTS_PATH,{}).get('events',[]),event_output['events'],now,'events')
        event_output['generated']=now
        news_review=merge_update_reviews([],news_review,now);event_review=merge_update_reviews([],event_review,now)
        news.write_json(news.NEWS_PATH,output);news.write_json(news.REGISTRY_PATH,registry)
        news.write_json(events.EVENTS_PATH,event_output)
        news.write_json(news.REVIEW_PATH,{'schemaVersion':2,'generated':now,'items':news_review})
        news.write_json(events.REVIEW_PATH,{'schemaVersion':2,'generated':now,'items':event_review})
    else:news_changes=[];event_changes=[]
    news_runs=source_runs('news',news_report);event_runs=source_runs('events',event_report)
    nq=quality_metrics(registry,output['articles'],news_runs,news_review,today)
    eq=quality_metrics(registry,event_output['events'],event_runs,event_review,today,'events')
    scope={'communityIds':list(communities),'communitiesScanned':len(communities),'fullScan':True,'method':'Bounded all-community source sweep followed by targeted live checks and offline record revalidation; full selection does not imply complete site extraction.'}
    news_report.update(generated=now,articlesAfter=len(output['articles']),quality=nq,sourceRuns=news_runs,scanScope=scope,latestValidationChanges=news_changes,manualReviewCount=len(news_review))
    event_report.update(generated=now,after=len(event_output['events']),quality=eq,sourceRuns=event_runs,scanScope=scope,latestValidationChanges=event_changes,reviewCount=len(event_review))
    news.write_json(news.REPORT_PATH,news_report);news.write_json(events.REPORT_PATH,event_report)
    before_news=baseline('news-data.json')['articles'];before_events=baseline('events-data.json')['events']
    def per_province(records,key='provinceTerritory'):return {p:sum(r.get(key)==p for r in records) for p in ('SK','AB','MB')}
    original_ids={str(r['id']) for r in before_news}
    result={'generated':now,'before':{'newsCommunitiesRegistered':len(baseline('news-sources.json')['communities']),'eventsCommunitiesRegistered':len(baseline('events-sources.json')['communities']),'newsArticles':len(before_news),'events':len(before_events),'newsByProvince':per_province(before_news),'eventsByProvince':per_province(before_events)},
            'after':{'communitiesRegistered':len(communities),'newsArticles':len(output['articles']),'events':len(event_output['events']),'newsByProvince':per_province(output['articles']),'eventsByProvince':per_province(event_output['events']),'newNewsRecordsRetained':sum(str(r['id']) not in original_ids for r in output['articles']),'previousNewsRecordsHeld':sum(str(r['id']) not in {str(a['id']) for a in output['articles']} for r in before_news),'newsDuplicatesSuppressedInMeasurements':news.load_json(RESEARCH/'news-full-scan.json',{}).get('duplicatesSuppressed',0)+news_report.get('duplicatesSuppressed',0),'eventDuplicatesSuppressedInMeasurement':event_report.get('duplicatesSuppressed',0)},
            'newsQuality':nq,'eventQuality':eq,'newsReviewRecords':len(news_review),'eventReviewRecords':len(event_review),
            'limitations':['The before figures describe the previously stored data, including records now held for quality review; a higher raw count is not proof of better coverage.',
                           'Only bounded pages/details were fetched. PDF/image OCR is available but was disabled in the live sweep; missing event years remain review-only.',
                           'No authorized Meta token was present for these scans. No Facebook posts were fetched or authentication bypassed.',
                           'JavaScript-only, TLS, robots, restricted, parked and unreachable sources remain explicit gaps.',
                           'RSS comments are excluded. Shared publishers require explicit community relevance. Publication dates are independent from event dates.',
                           'Stable IDs, revisions and content fingerprints support future notification design, but comprehensive personalized coverage is not ready; source gaps and manual review must be addressed first.']}
    news.write_json(ROOT/'community-intelligence-phase1-report.json',result)
    lines=['# Community news and events — Phase 1','',f'Generated {now}. All measurements use actual source scans and stored records.','',
           '| Measure | Before | After |','|---|---:|---:|',f"| Registered communities, news | {result['before']['newsCommunitiesRegistered']} | {len(communities)} |",f"| Registered communities, events | {result['before']['eventsCommunitiesRegistered']} | {len(communities)} |",f"| Published news records | {len(before_news)} | {len(output['articles'])} |",f"| Current/recent event records | {len(before_events)} | {len(event_output['events'])} |",'',
           '| Province | Tracked | Reachable news sources: communities | News in 30 / 90 days: communities | Upcoming events: communities |','|---|---:|---:|---:|---:|']
    for p in ('SK','AB','MB'):
        n=nq['byProvince'][p];e=eq['byProvince'][p]
        lines.append(f"| {p} | {n['communitiesTracked']} | {n['communitiesWithWorkingSourcesThisRun']} | {n['communitiesWithNewsLast30Days']} / {n['communitiesWithNewsLast90Days']} | {e['communitiesWithUpcomingEvents']} |")
    lines+=['','Reachable sources are not a promise of recent community-specific content. Publication and event date failures are held for review; source outages do not delete valid historical articles.','',f"News scan statuses: `{json.dumps(nq['scanStatusCounts'],sort_keys=True)}`.",f"Event scan statuses: `{json.dumps(eq['scanStatusCounts'],sort_keys=True)}`.",'','## Limitations and readiness','']+['- '+v for v in result['limitations']]
    (ROOT/'community-intelligence-phase1-report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(result['after'],indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--revalidate',action='store_true');args=p.parse_args();audit(args.revalidate)
