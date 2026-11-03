#!/usr/bin/env python3
"""Discover source-backed First Nation community events by province.

Only events that pass the public publish gate are written to the permanent site dataset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

try:
    from news_discovery import (
        Fetcher,
        canonical_url,
        clean_text,
        ensure_registry,
        iso_now,
        load_json,
        normalized_text,
        parse_date_text,
        slugify,
        source_confidence,
        source_is_monitorable,
        write_json,
        extract_feed_candidates,
        employment_item,
    )
except ImportError:  # Imported as tools.events_discovery in tests.
    from tools.news_discovery import (
        Fetcher,
        canonical_url,
        clean_text,
        ensure_registry,
        iso_now,
        load_json,
        normalized_text,
        parse_date_text,
        slugify,
        source_confidence,
        source_is_monitorable,
        write_json,
        extract_feed_candidates,
        employment_item,
    )


try:
    from community_history import merge_review_history
except ImportError:
    from tools.community_history import merge_review_history

try:
    from community_updates import association_allowed, feed_links, page_diagnostic, error_status, quality_metrics, track_changes, icalendar_records, merge_update_reviews
except ImportError:
    from tools.community_updates import association_allowed, feed_links, page_diagnostic, error_status, quality_metrics, track_changes, icalendar_records, merge_update_reviews
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data.json"
NEWS_PATH = ROOT / "news-data.json"
NEWS_REGISTRY_PATH = ROOT / "news-sources.json"
EVENTS_PATH = ROOT / "events-data.json"
REGISTRY_PATH = ROOT / "events-sources.json"
REVIEW_PATH = ROOT / "events-review-queue.json"
REPORT_PATH = ROOT / "events-coverage-report.json"

EVENT_WINDOW_PAST_DAYS = 30
EVENT_WINDOW_FUTURE_DAYS = 400
SHARED_EVENT_INDEXES = [
    {
        "name": "Meadow Lake Tribal Council regional events",
        "type": "Tribal Council Tourism",
        "url": "https://meadowlakeregion.ca/events",
        "official": True,
        "associationConfidence": 0.96,
    },
    {
        "name": "Saskatchewan Pow Wow Calendar",
        "type": "Regional Event Index",
        "url": "https://calendar.powwows.com/events/categories/pow-wows-in-saskatchewan/",
        "discoveryUrls": [
            "https://calendar.powwows.com/events/categories/pow-wows-in-saskatchewan/?pno=2",
        ],
        "associationConfidence": 0.9,
        "provinceTerritory": "SK",
    },
    {
        "name": "Alberta Powwow Calendar",
        "type": "Regional Event Index",
        "url": "https://calendar.powwows.com/events/categories/pow-wows-in-alberta/",
        "associationConfidence": 0.9,
        "provinceTerritory": "AB",
    },
    {"name":"Manitoba Powwow Calendar","type":"Regional Event Index","url":"https://calendar.powwows.com/events/categories/pow-wows-in-manitoba/","associationConfidence":0.9,"provinceTerritory":"MB"},
    {
        "name": "Windspeaker Powwow Calendar",
        "type": "Indigenous Media Event Index",
        "url": "https://support.windspeaker.com/powwows",
        "associationConfidence": 0.9,
    },
    {
        "name": "Office of the Treaty Commissioner events",
        "type": "Treaty Organization",
        "url": "https://otc.ca/events/list/",
        "associationConfidence": 0.94,
    },
]
SHARED_COMMUNITY_ALIASES = {
    344: ["Onion Lake First Nations"],
    353: ["Lac La Ronge First Nation", "LLRIB"],
    363: ["Ochapowace Nation"],
    364: ["Zagime Anishinabek", "Sakimay First Nation"],
    365: ["White Bear First Nation"],
    369: ["Beardy's & Okemasis Cree Nation", "Beardy's and Okemasis Cree Nation"],
    376: ["Yellow Quill Cree Nation"],
    378: ["Carry the Kettle First Nation", "Ceg-A-Kin Nakoda Nation"],
    380: ["Nekaneet First Nation"],
    392: ["Muskowekwan Cree Nation"],
    397: ["Ministikwan Cree Nation"],
    408: ["Oceanman Nakoda Nation", "Ocean Man Nakoda Nation"],
    409: ["Pheasant Rump Nakota First Nation"],
}
EVENT_WORDS = re.compile(
    r"\b(pow[ -]?wow|wacipi|round dance|treaty day|feast|gathering|ceremony|"
    r"celebration|community (?:meeting|event|clean[ -]?up)|annual general meeting|agm|"
    r"open house|workshop|training|conference|forum|fair|clinic|screening|"
    r"tournament|relay race|races|rodeo|bingo|fundraiser|market|festival|parade|camp|youth day|"
    r"family day|language class|culture camp|land-based|sports day|information session|"
    r"election day|vote|meeting|event|leadership program|lawmakers assembly)\b",
    re.I,
)
NON_EVENT_WORDS = re.compile(
    r"\b(job posting|job opportunity|employment opportunity|opportunities|office closures?|distribution form|application form|requests? for proposals?|rpf|rfp|tender|"
    r"financial statements?|audit|remuneration|happy birthday|contest winner)\b",
    re.I,
)
GENERIC_TITLES = {
    "read more", "learn more", "details", "view", "click here", "events",
    "calendar", "news", "announcements", "community events", "event details",
}
FOLLOW_LINK_WORDS = re.compile(
    r"\b(event|calendar|pow[ -]?wow|wacipi|notice|announcement|community|news)\b",
    re.I,
)
MONTH_RE = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?"
    r"(?:\s*(?:-|–|to)\s*(?:\1\s+)?(\d{1,2})(?:st|nd|rd|th)?)?(?:,?\s*(20\d{2}))?\b",
    re.I,
)
TIME_RE = re.compile(
    r"\b(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?))\b",
    re.I,
)
LOCATION_RE = re.compile(
    r"\b(?:location|where|venue)\s*[:\-]\s*([^|•\n]{3,100})",
    re.I,
)
MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def event_category(value: str, context: str = "") -> str:
    text = normalized_text(value)
    rules = [
        (r"\b(emergency|evacuation|wildfire)\b", "Emergency Information"),
        (r"\b(voter|referendum|ballot|nomination|election)\b", "Governance & Meetings"),
        (r"\b(halloween|homecoming|community celebration|gathering|knitting|crafts)\b", "Community Event"),
        (r"pow ?wow|wacipi|round dance|feast|ceremony|culture|language|land based", "Culture & Language"),
        (r"treaty day", "Treaty Days"),
        (r"health|clinic|screening|wellness|healing", "Health & Wellness"),
        (r"youth|family|children|kids|camp", "Youth & Family"),
        (r"tournament|sports|hockey|softball|rodeo|golf", "Recreation & Sports"),
        (r"training|workshop|class|education|conference|forum", "Education & Training"),
        (r"election|vote|annual general meeting|agm|community meeting|council", "Governance & Meetings"),
        (r"emergency|evacuation|wildfire", "Emergency Information"),
    ]
    for local in (text, normalized_text(context)):
        for pattern, category in rules:
            if re.search(pattern, local):return category
    return "Community Event"


def infer_yearless_date(month: int, day: int, today: date) -> date | None:
    candidates = []
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            pass
    viable = [
        value for value in candidates
        if today - timedelta(days=EVENT_WINDOW_PAST_DAYS) <= value <= today + timedelta(days=EVENT_WINDOW_FUTURE_DAYS)
    ]
    return min(viable, key=lambda value: (value < today, abs((value - today).days))) if viable else None


def event_text_content(value):
    text=clean_text(value)
    if re.match(r'^insert_link\b',text):
        text=re.sub(r'^insert_link\s+','',text)
        text=re.split(r'\s+today\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)',text,maxsplit=1,flags=re.I)[0]
    return text


def explicit_written_ranges(value):
    month=r'(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
    pattern=re.compile(month+r'\s+(\d{1,2})(?:,?\s+(20\d{2}))?\s*(?:-|–|—|to)\s*'+month+r'\s+(\d{1,2}),?\s+(20\d{2})',re.I)
    rows=[]
    for match in pattern.finditer(clean_text(value)):
        m1,d1,y1,m2,d2,y2=match.groups();m1=MONTHS[m1[:3].lower()];m2=MONTHS[m2[:3].lower()]
        try:
            end=date(int(y2),m2,int(d2));start=date(int(y1) if y1 else int(y2)-(m1>m2),m1,int(d1))
            if end>=start:rows.append((start.isoformat(),end.isoformat()))
        except ValueError:continue
    return rows


def event_dates(value: str, today: date | None = None) -> list[tuple[str, str | None]]:
    """Return unique event date ranges found in text, including yearless flyers."""
    today = today or utc_today()
    rows = explicit_written_ranges(value)
    seen = set(rows)
    for match in MONTH_RE.finditer(clean_text(value)):
        month_name, start_day, end_day, year = match.groups()
        month = MONTHS[month_name[:3].lower()]
        try:
            start = date(int(year), month, int(start_day)) if year else infer_yearless_date(month, int(start_day), today)
            end = date(start.year, month, int(end_day)) if start and end_day else None
        except ValueError:
            continue
        if not start:
            continue
        key = (start.isoformat(), end.isoformat() if end else None)
        if key not in seen:
            seen.add(key)
            rows.append(key)
    for token in re.findall(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b", clean_text(value)):
        parsed, _ = parse_date_text(token)
        if parsed and (parsed, None) not in seen:
            seen.add((parsed, None))
            rows.append((parsed, None))
    return rows


def explicit_event_dates(value: str) -> list[tuple[str, str | None]]:
    """Return source dates that state a year, excluding publication timestamps."""
    text = event_text_content(value)
    rows = explicit_written_ranges(text)
    seen = set(rows)
    for match in MONTH_RE.finditer(text):
        month_name, start_day, end_day, year = match.groups()
        if not year:
            continue
        prefix = text[max(0, match.start() - 24):match.start()]
        if re.search(r"\b(?:posted|published|updated)\s*(?:on)?\s*$", prefix, re.I):
            continue
        month = MONTHS[month_name[:3].lower()]
        try:
            start = date(int(year), month, int(start_day))
            end = date(start.year, month, int(end_day)) if end_day else None
        except ValueError:
            continue
        key = (start.isoformat(), end.isoformat() if end else None)
        if key not in seen:
            seen.add(key)
            rows.append(key)
    year_before_month = re.compile(
        r"\b(20\d{2})\s*(?:[-–—,:]|\s)\s*"
        r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
        r"Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?\b",
        re.I,
    )
    for match in year_before_month.finditer(text):
        year, month_name, day = match.groups()
        try:
            parsed = date(int(year), MONTHS[month_name[:3].lower()], int(day)).isoformat()
        except ValueError:
            continue
        if (parsed, None) not in seen:
            seen.add((parsed, None))
            rows.append((parsed, None))
    for match in re.finditer(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b", text):
        prefix=text[max(0,match.start()-24):match.start()]
        if re.search(r'\b(?:posted|published|updated)\s*(?:on)?\s*[:\-]?\s*$',prefix,re.I):continue
        parsed, _ = parse_date_text(match.group())
        if parsed and (parsed, None) not in seen:
            seen.add((parsed, None))
            rows.append((parsed, None))
    return rows


def choose_event_date(title: str, context: str, today: date | None = None):
    title=event_text_content(title);context=event_text_content(context)
    today = today or utc_today()
    minimum = today - timedelta(days=EVENT_WINDOW_PAST_DAYS)
    maximum = today + timedelta(days=EVENT_WINDOW_FUTURE_DAYS)

    def first_viable(rows):
        return next((row for row in rows if minimum <= date.fromisoformat(row[0]) <= maximum), None)

    title_explicit = explicit_event_dates(title)
    context_explicit = explicit_event_dates(context)
    if title_explicit:
        return first_viable(title_explicit) or (None, None)
    if context_explicit:
        title_yearless=[m for m in MONTH_RE.finditer(clean_text(title)) if not m.group(4)]
        if title_yearless:
            target={f"{MONTHS[m.group(1)[:3].lower()]:02d}-{int(m.group(2)):02d}" for m in title_yearless}
            matching=[r for r in context_explicit if r[0][5:] in target]
            return first_viable(matching) or (None,None)
        return first_viable(context_explicit) or (None, None)

    selected = first_viable(event_dates(title, today)) or first_viable(event_dates(context, today))
    return selected or (None, None)


def event_status(start: str, end: str | None, today: date | None = None) -> str:
    today = today or utc_today()
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end) if end else start_date
    if start_date <= today <= end_date:
        return "Ongoing"
    if start_date > today:
        return "Upcoming"
    return "Recently held"


def event_time(value: str) -> str | None:
    match = TIME_RE.search(clean_text(value))
    return clean_text(match.group(1)).upper().replace(".", "") if match else None


def event_location(value: str) -> str | None:
    match = LOCATION_RE.search(str(value or ""))
    if not match:
        return None
    location = clean_text(match.group(1))
    location = re.split(r"\b(?:date|time|contact|admission)\s*[:\-]", location, maxsplit=1, flags=re.I)[0]
    location = re.split(r"\b(?:event details|read more|learn more|register)\b", location, maxsplit=1, flags=re.I)[0]
    return location[:100].rstrip(" ,.;-") or None


def is_event_text(title: str, context: str = "") -> bool:
    text = clean_text(f"{title} {context}")
    if employment_item(title) and not re.search(r"\b(?:job|career) fair\b",title,re.I):return False
    return bool(EVENT_WORDS.search(text)) and not bool(NON_EVENT_WORDS.search(text))


def event_id(community: dict, start: str, title: str) -> str:
    digest = hashlib.sha1(
        f"{community.get('bandId')}|{start}|{normalized_text(title)}".encode("utf-8")
    ).hexdigest()[:10]
    return f"{slugify(community.get('communityName'))}-{start}-{digest}"


def event_title(title: str, context: str) -> str:
    title = clean_text(title)
    title=re.sub(r'^(?:insert_link|link|today)\s+','',title)
    title=re.split(r'\s+today\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)',title,maxsplit=1,flags=re.I)[0]
    if normalized_text(title) not in GENERIC_TITLES and 6 <= len(title) <= 150:
        return title
    context = clean_text(context)
    context = re.split(r"\b(?:date|when|time|where|location)\s*[:\-]", context, maxsplit=1, flags=re.I)[0]
    return context[:145].rstrip(" ,.;:-") or "Community event"


def normalized_event(community: dict, source: dict, *, title: str, context: str, url: str, start: str, end: str | None = None, image: str | None = None, method: str = "html") -> dict:
    title = event_title(title, context)
    confidence = min(1.0, source_confidence(source) + (0.02 if method == "json-ld" else 0))
    item = {
        "id": event_id(community, start, title),
        "communityName": community["communityName"],
        "communityAliases": community.get("aliases") or [],
        "bandId": community["bandId"],
        "provinceTerritory": community.get("provinceTerritory", "SK"),
        "title": title,
        "category": event_category(title, context),
        "startDate": start,
        "status": event_status(start, end),
        "description": clean_text(context)[:420],
        "sourceUrl": canonical_url(url),
        "sourceName": source.get("name") or community["communityName"],
        "sourceType": source.get("type") or "Community Website",
        "extractionMethod": method,
        "confidence": round(confidence, 2),
        "discoveredAt": iso_now(),
    }
    if end:
        item["endDate"] = end
    time_value = event_time(context)
    location = event_location(context)
    if time_value:
        item["startTime"] = time_value
    if location:
        item["location"] = location
    if image and str(image).startswith("http"):
        item["image"] = canonical_url(image)
    return item


class EventPageParser(HTMLParser):
    BLOCKS = {"article", "li", "section"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.stack = []
        self.anchors = []
        self.images = []
        self.active_anchor = None
        self.page_title = ""
        self.in_title = False
        self.json_scripts = []
        self.in_json = False
        self.json_parts = []
        self.ignored_depth = 0
        self.headings = []
        self.heading_offsets = []
        self.heading_parts = None
        self.heading_start = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'h1':
            self.heading_parts = []
            self.heading_start = len(self.parts)
        classes = " ".join(attrs.get("class", "").split()).lower()
        block = tag in self.BLOCKS or (tag == "div" and any(word in classes for word in ("event", "calendar", "notice", "card", "post")))
        node = {"tag": tag, "block": block, "start": len(self.parts), "anchors": [], "images": []}
        self.stack.append(node)
        if tag == "title":
            self.in_title = True
        if tag == "script" and "ld+json" in attrs.get("type", "").lower():
            self.in_json = True
            self.json_parts = []
        elif tag in {"script", "style", "svg", "noscript"}:
            self.ignored_depth += 1
        if tag == "a" and attrs.get("href"):
            self.active_anchor = {"href": attrs["href"], "start": len(self.parts), "end": None, "context": None, "image": None}
            self.anchors.append(self.active_anchor)
            for parent in reversed(self.stack[:-1]):
                if parent["block"]:
                    parent["anchors"].append(len(self.anchors) - 1)
                    break
        if tag == "img" and (attrs.get("src") or attrs.get("data-src")):
            image = {"src": attrs.get("src") or attrs.get("data-src"), "alt": clean_text(attrs.get("alt")), "context": None}
            self.images.append(image)
            for parent in reversed(self.stack[:-1]):
                if parent["block"]:
                    parent["images"].append(len(self.images) - 1)
                    break

    def handle_data(self, data):
        if self.in_json:
            self.json_parts.append(data)
            return
        if self.ignored_depth:
            return
        value = clean_text(data)
        if value:
            self.parts.append(value)
            if self.heading_parts is not None:
                self.heading_parts.append(value)
            if self.in_title:
                self.page_title = clean_text(f"{self.page_title} {value}")

    def handle_endtag(self, tag):
        if tag == 'h1' and self.heading_parts is not None:
            self.headings.append(clean_text(' '.join(self.heading_parts)))
            self.heading_offsets.append(self.heading_start)
            self.heading_parts = None
        if tag == "title":
            self.in_title = False
        if tag == "script" and self.in_json:
            self.json_scripts.append("".join(self.json_parts))
            self.in_json = False
        elif tag in {"script", "style", "svg", "noscript"} and self.ignored_depth:
            self.ignored_depth -= 1
        if tag == "a" and self.active_anchor:
            self.active_anchor["end"] = len(self.parts)
            self.active_anchor = None
        index = next((i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i]["tag"] == tag), None)
        if index is None:
            return
        closing = self.stack[index:]
        self.stack = self.stack[:index]
        for node in closing:
            if not node["block"]:
                continue
            context = clean_text(" ".join(self.parts[node["start"]:]))
            for anchor_index in node["anchors"]:
                if self.anchors[anchor_index]["context"] is None:
                    self.anchors[anchor_index]["context"] = context
            for image_index in node["images"]:
                if self.images[image_index]["context"] is None:
                    self.images[image_index]["context"] = context

    def anchor_rows(self):
        rows = []
        for anchor in self.anchors:
            end = anchor["end"] if anchor["end"] is not None else anchor["start"]
            rows.append({**anchor, "title": clean_text(" ".join(self.parts[anchor["start"]:end])), "context": anchor["context"] or ""})
        return rows

    @property
    def page_text(self):
        return clean_text(" ".join(self.parts))


def jsonld_objects(value):
    if isinstance(value, list):
        for item in value:
            yield from jsonld_objects(item)
    elif isinstance(value, dict):
        if "@graph" in value:
            yield from jsonld_objects(value["@graph"])
        yield value


def structured_event_fields(item, source):
    fields={}
    for key,target in [('startDate','startTime'),('endDate','endTime')]:
        raw=str(item.get(key) or '')
        match=re.search(r'T(\d{2}:\d{2})(?::\d{2})?(Z|[+-]\d{2}:?\d{2})?',raw)
        if match:
            fields[target]=match.group(1)
            if match.group(2):fields[target+'Offset']=match.group(2)
    if item.get('datePublished'):
        published,_=parse_date_text(item['datePublished'])
        if published:fields.update(publishedAt=published,publicationDateSource='json-ld:datePublished')
    location=item.get('location') or {}
    if isinstance(location,list):location=location[0] if location else {}
    if isinstance(location,dict):
        address=location.get('address') or {}
        if isinstance(address,dict):address=', '.join(str(address[k]) for k in ('streetAddress','addressLocality','addressRegion','postalCode') if address.get(k))
        fields['location']=', '.join(str(v) for v in (location.get('name'),address) if v)[:250]
    elif isinstance(location,str):fields['location']=clean_text(location)[:250]
    status=str(item.get('eventStatus') or '')
    if 'Cancelled' in status:fields['eventStatus']='cancelled'
    elif 'Postponed' in status:fields['eventStatus']='postponed'
    if item.get('@id'):fields['sourceUid']=str(item['@id'])
    return {k:v for k,v in fields.items() if v}


def extract_jsonld_events(parser: EventPageParser, page_url: str, community: dict, source: dict) -> list[dict]:
    rows=[]
    for script in parser.json_scripts:
        try:payload=json.loads(script)
        except json.JSONDecodeError:continue
        for item in jsonld_objects(payload):
            types=item.get('@type') or [];types=[types] if isinstance(types,str) else types
            if not any(str(t).lower()=='event' for t in types):continue
            start,_=parse_date_text(item.get('startDate'));end,_=parse_date_text(item.get('endDate'))
            title=clean_text(item.get('name'));context=clean_text(item.get('description',''))
            if not start or not title or not association_allowed(community,source,title,context):continue
            image=item.get('image');image=image[0] if isinstance(image,list) and image else image
            if isinstance(image,dict):image=image.get('url')
            row=normalized_event(community,source,title=title,context=context,url=urllib.parse.urljoin(page_url,item.get('url') or page_url),start=start,end=end,image=image,method='json-ld')
            row.update(structured_event_fields(item,source));row['dateSource']='json-ld:startDate';rows.append(row)
    return rows


def extract_ical_events(payload,page_url,community,source):
    objects,rejected=icalendar_records(payload);rows=[]
    def field(obj,key):return obj.get(key,{}).get('value','')
    for obj in objects:
        raw=field(obj,'DTSTART');match=re.fullmatch(r'(20\d{2})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(?:\d{2})?(Z)?)?',raw)
        if not match:rejected.append({'reason':'Calendar event lacks a valid explicit DTSTART','url':page_url});continue
        try:start=date(*map(int,match.group(1,2,3))).isoformat()
        except ValueError:continue
        title=field(obj,'SUMMARY');context=field(obj,'DESCRIPTION');end=None;raw_end=field(obj,'DTEND')
        end_match=re.match(r'^(20\d{2})(\d{2})(\d{2})',raw_end)
        if end_match:
            try:
                value=date(*map(int,end_match.groups()))
                if len(raw_end)==8:value-=timedelta(days=1)
                end=value.isoformat()
            except ValueError:pass
        if not title or not association_allowed(community,source,title,context):continue
        row=normalized_event(community,source,title=title,context=context,url=field(obj,'URL') or page_url,start=start,end=end,method='icalendar')
        row['sourceUid']=field(obj,'UID') or row['id'];row['dateSource']='icalendar:DTSTART'
        if match.group(4):row['startTime']=f'{match.group(4)}:{match.group(5)}'
        tz=obj.get('DTSTART',{}).get('params',{}).get('TZID')
        if tz:row['timeZone']=tz
        if match.group(6):row['startTimeOffset']='Z'
        if field(obj,'LOCATION'):row['location']=clean_text(field(obj,'LOCATION'))[:250]
        if field(obj,'STATUS').upper()=='CANCELLED':row['eventStatus']='cancelled'
        rows.append(row)
    return rows,rejected


class EventerDetailsParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.fields={}; self.capture=None; self.depth=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs); classes=a.get('class','').split()
        if self.capture and tag not in {'br','img','hr','input','meta','link','source','wbr'}: self.depth+=1
        elif tag=='h1' or any(k in classes for k in ('eventer-event-date','eventer-event-time','eventer-event-venue')):
            self.capture='title' if tag=='h1' else next(k for k in classes if k in ('eventer-event-date','eventer-event-time','eventer-event-venue'))
            self.depth=1
    def handle_data(self,text):
        if self.capture: self.fields.setdefault(self.capture,[]).append(text)
    def handle_endtag(self,tag):
        if self.capture:
            self.depth-=1
            if not self.depth:self.capture=None


def extract_eventer_detail(markup,page_url,community,source):
    occurrence=re.search(r'/eventer/[^/]+/edate/(20\d{2}-\d{2}-\d{2})/?$',urllib.parse.urlsplit(page_url).path)
    if not occurrence:return None
    p=EventerDetailsParser();p.feed(markup)
    values={k:clean_text(' '.join(v)) for k,v in p.fields.items()}
    title=values.get('title',''); written=values.get('eventer-event-date') or values.get('eventer-event-time','')
    dates=[d for pair in explicit_event_dates(written) for d in pair if d]
    if not title or occurrence.group(1) not in dates or not association_allowed(community,source,title,values.get('eventer-event-venue','')):return None
    context='Date: '+written+'. '+values.get('eventer-event-time','')
    row=normalized_event(community,source,title=title,context=context,url=page_url,start=occurrence.group(1),end=max(dates) if dates else None,method='eventer')
    if values.get('eventer-event-venue'):row['location']=values['eventer-event-venue']
    clocks=re.findall(r'\b(\d{1,2}:\d{2})\s*(AM|PM)\b',values.get('eventer-event-time',''),re.I)
    if 'all day' in context.lower() or (len(clocks)==2 and clocks[0]==('12:00','AM') and clocks[1]==('11:59','PM')):
        row['allDay']=True;row.pop('startTime',None)
    if len(clocks)==2 and not ('12:00','AM')==clocks[0]:
        def clock(pair):return datetime.strptime(' '.join(pair).upper(),'%I:%M %p').strftime('%H:%M')
        row['startTime']=clock(clocks[0]);row['endTime']=clock(clocks[1])
    if re.search(r'bead|poppy',title,re.I):row['category']='Culture & Language'
    if re.search(r'\bcancell?ed\b',title,re.I):row['eventStatus']='cancelled'
    elif re.search(r'\bpostponed\b',title,re.I):row['eventStatus']='postponed'
    return row


def extract_html_events(html: str, page_url: str, community: dict, source: dict, today: date | None = None):
    eventer=extract_eventer_detail(html,page_url,community,source)
    if eventer:return [eventer],[],[]
    parser = EventPageParser()
    parser.feed(html)
    events = extract_jsonld_events(parser, page_url, community, source)
    follow = []
    media = []
    seen = {item["sourceUrl"] for item in events}
    dated_detail = re.search(r'/events?/(20\d{2}-\d{2}-\d{2})(?:[-/]|$)', urllib.parse.urlsplit(page_url).path)
    if dated_detail and not events:
        title, offset = next(((heading, offset) for heading, offset in zip(parser.headings, parser.heading_offsets) if heading.lower() not in GENERIC_TITLES), ('', 0))
        context = re.split(r'\bPrevious(?:\s+Previous)?\b', clean_text(' '.join(parser.parts[offset:])), maxsplit=1)[0]
        dates = {start for start, _ in event_dates(context, today)}
        if title and dated_detail.group(1) in dates and is_event_text(title, context):
            item = normalized_event(community, source, title=title, context=context, url=page_url, start=dated_detail.group(1), method='html-calendar-detail')
            events.append(item)
            seen.add(item['sourceUrl'])
    for row in parser.anchor_rows():
        url = canonical_url(urllib.parse.urljoin(page_url, row["href"]))
        combined = clean_text(f"{row['title']} {row['context']}")
        dated_event_link = re.search(r'/(?:events?/|eventer/[^/]+/edate/)20\d{2}-\d{2}-\d{2}', urllib.parse.urlsplit(url).path)
        if (FOLLOW_LINK_WORDS.search(combined) or dated_event_link or urllib.parse.urlsplit(url).path.lower().endswith(".ics")) and url.startswith("http"):
            follow.append(url)
        if dated_detail or normalized_text(row['title']) in GENERIC_TITLES or re.match(r'^(?:back to all|previous|next)\b', row['title'], re.I):
            continue
        if re.search(r"\.(?:pdf|png|jpe?g)(?:$|\?)", url, re.I) and is_event_text(row["title"], row["context"]):
            media.append(url)
        if not association_allowed(community,source,row["title"],row["context"]):continue
        if not is_event_text(row["title"], row["context"]):
            continue
        start, end = choose_event_date(row["title"], row["context"], today)
        if not start or url in seen:
            continue
        events.append(normalized_event(community, source, title=row["title"], context=row["context"], url=url, start=start, end=end, method="html"))
        seen.add(url)
    for image in parser.images:
        combined = clean_text(f"{image['alt']} {image['context'] or ''}")
        if is_event_text(image["alt"], combined):
            media.append(canonical_url(urllib.parse.urljoin(page_url, image["src"])))
    if not events and association_allowed(community,source,parser.page_title,parser.page_text) and is_event_text(parser.page_title, parser.page_text):
        start, end = choose_event_date(parser.page_title, parser.page_text, today)
        if start and canonical_url(page_url) not in seen:
            events.append(normalized_event(community, source, title=parser.page_title, context=parser.page_text, url=page_url, start=start, end=end, method="html-page"))
    def calendar_priority(url):
        match = re.search(r'/events?/(20\d{2}-\d{2}-\d{2})', urllib.parse.urlsplit(url).path)
        return match.group(1) if match else ''
    return events, sorted(dict.fromkeys(follow), key=calendar_priority, reverse=True), list(dict.fromkeys(media))


def shared_aliases_for_community(community: dict) -> list[str]:
    """Return configured shared-calendar aliases without assuming IDs are numeric.

    Alberta has one intentionally synthetic profile ID for the separately
    administered Whitefish Lake #128 government. Shared event sources should
    still be scanned for that profile instead of crashing while coercing the
    ID to ``int``.
    """
    try:
        band_id = int(community.get("bandId"))
    except (TypeError, ValueError):
        return []
    return SHARED_COMMUNITY_ALIASES.get(band_id, [])


def match_shared_community(communities: list[dict], value: str) -> dict | None:
    """Return one explicitly named community; ambiguous matches are rejected."""
    haystack = f" {normalized_text(value)} "
    matches = []
    for community in communities:
        names = [
            community.get("communityName"),
            *(community.get("aliases") or []),
            *shared_aliases_for_community(community),
        ]
        if any(
            len(term := normalized_text(name)) >= 8 and f" {term} " in haystack
            for name in names if name
        ):
            matches.append(community)
    return matches[0] if len(matches) == 1 else None


def concise_shared_event_title(title: str, community: dict) -> str:
    """Trim shared-calendar card boilerplate while preserving the source event name."""
    value = clean_text(title)
    names = [
        community.get("communityName"),
        *(community.get("aliases") or []),
        *shared_aliases_for_community(community),
    ]
    positions = []
    for name in names:
        if not name:
            continue
        match = re.search(re.escape(clean_text(name)), value, re.I)
        if match:
            positions.append(match.start())
    if positions:
        value = value[min(positions):]
    value = re.split(r"\bEvent Details\b", value, maxsplit=1, flags=re.I)[0]
    year_match = re.search(r"^(.+?\b20\d{2}\b)", value)
    if year_match and EVENT_WORDS.search(year_match.group(1)):
        value = year_match.group(1)
    return clean_text(value)[:150]


def extract_shared_index_events(
    html: str,
    page_url: str,
    communities: list[dict],
    source: dict,
    today: date | None = None,
) -> list[dict]:
    """Extract events only when a shared index explicitly names one community."""
    parser = EventPageParser()
    parser.feed(html)
    events = []
    seen = set()

    for script in parser.json_scripts:
        try:
            payload = json.loads(script)
        except json.JSONDecodeError:
            continue
        for item in jsonld_objects(payload):
            types = item.get("@type") or []
            types = [types] if isinstance(types, str) else types
            if not any(str(value).lower() == "event" for value in types):
                continue
            title = clean_text(item.get("name"))
            context = clean_text(f"{item.get('description', '')} {item.get('startDate', '')}")
            community = match_shared_community(communities, f"{title} {context}")
            start, _ = parse_date_text(item.get("startDate"))
            end, _ = parse_date_text(item.get("endDate"))
            url = canonical_url(urllib.parse.urljoin(page_url, item.get("url") or page_url))
            if not community or not start or not is_event_text(title, context) or url in seen:
                continue
            events.append(normalized_event(
                community, source, title=title, context=context, url=url,
                start=start, end=end, image=item.get("image"), method="json-ld",
            ))
            seen.add(url)

    for row in parser.anchor_rows():
        title = clean_text(row["title"])
        context = clean_text(row["context"])
        community = match_shared_community(communities, title) or match_shared_community(
            communities, f"{title} {context}"
        )
        if not community or not is_event_text(title, context):
            continue
        start, end = choose_event_date(title, context, today)
        url = canonical_url(urllib.parse.urljoin(page_url, row["href"]))
        if not start or not url.startswith("http") or url in seen:
            continue
        events.append(normalized_event(
            community, source, title=concise_shared_event_title(title, community),
            context=context, url=url, start=start, end=end, method="shared-index",
        ))
        seen.add(url)
    return events


def extract_media_text(body: bytes, content_type: str, suffix: str) -> tuple[str, str]:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / f"source{suffix}"
        source.write_bytes(body)
        if "pdf" in content_type or suffix.lower() == ".pdf":
            result = subprocess.run(["pdftotext", "-f", "1", "-l", "3", "-layout", str(source), "-"], capture_output=True, text=True, timeout=35, check=False)
            if len(clean_text(result.stdout)) >= 35:
                return result.stdout, "pdftotext"
            prefix = Path(directory) / "page"
            subprocess.run(["pdftoppm", "-f", "1", "-l", "2", "-png", "-r", "170", str(source), str(prefix)], capture_output=True, timeout=45, check=False)
            pages = []
            for image in sorted(Path(directory).glob("page-*.png")):
                ocr = subprocess.run(["tesseract", str(image), "stdout", "--psm", "6"], capture_output=True, text=True, timeout=35, check=False)
                pages.append(ocr.stdout)
            return "\n".join(pages), "ocr-pdf"
        result = subprocess.run(["tesseract", str(source), "stdout", "--psm", "6"], capture_output=True, text=True, timeout=35, check=False)
        return result.stdout, "ocr-image"


def extract_media_event(fetcher: Fetcher, url: str, community: dict, source: dict, today: date | None = None):
    body, final_url, content_type = fetcher.get(url)
    suffix = Path(urllib.parse.urlsplit(final_url).path).suffix or (".pdf" if "pdf" in content_type else ".png")
    text, method = extract_media_text(body, content_type, suffix)
    if not is_event_text(text) or len(clean_text(text)) < 20:
        return None
    start, end = choose_event_date(text[:220], text, today)
    if not start:
        return None
    title = next((line for line in text.splitlines() if is_event_text(line) and 6 <= len(clean_text(line)) <= 150), "Community event notice")
    return normalized_event(community, source, title=title, context=text, url=final_url, start=start, end=end, method=method)


def discover_meta_events(fetcher: Fetcher, community: dict, source: dict, token: str | None, today: date | None = None):
    page_id = source.get("metaPageId") or source.get("pageHandle")
    if not token or not page_id:
        return []
    version = os.getenv("META_API_VERSION", "v23.0")
    query = urllib.parse.urlencode({"fields": "message,created_time,permalink_url,full_picture", "limit": "50"})
    body, _, _ = fetcher.get(
        f"https://graph.facebook.com/{version}/{page_id}/posts?{query}",
        headers={"Authorization": f"Bearer {token}"},
        respect_robots=False,
    )
    rows = []
    for post in json.loads(body.decode("utf-8")).get("data", []):
        message = clean_text(post.get("message"))
        if not is_event_text(message) or not post.get("permalink_url"):
            continue
        start, end = choose_event_date(message[:180], message, today)
        if not start:
            continue
        title = re.split(r"(?<=[.!?])\s+", message, maxsplit=1)[0][:145]
        rows.append(normalized_event(community, source, title=title, context=message, url=post["permalink_url"], start=start, end=end, image=post.get("full_picture"), method="meta-api"))
    return rows


def source_registry(data: dict, news: dict, events_registry: dict) -> dict:
    news_registry = load_json(NEWS_REGISTRY_PATH, {"schemaVersion": 1, "communities": []})
    merged = ensure_registry(data, news, news_registry)
    event_rows = {str(row.get("bandId")): row for row in events_registry.get("communities", [])}
    for community in merged.get("communities", []):
        override = event_rows.get(str(community["bandId"]), {})
        if override.get("sources"):
            known = {canonical_url(source.get("url")):source for source in community.get("sources", [])}
            for source in override["sources"]:
                if canonical_url(source.get("url")) not in known:
                    community.setdefault("sources", []).append(source)
                else:
                    preserved={k:v for k,v in known[canonical_url(source.get('url'))].items() if k in {'requiresCommunityMention','associationCommunityNames'}}
                    known[canonical_url(source.get('url'))].update(source)
                    known[canonical_url(source.get('url'))].update(preserved)
    return {
        "schemaVersion": 1,
        "generated": iso_now(),
        "notes": "Event discovery sources are derived from the verified News registry. Add event-specific calendars here when found.",
        "communities": merged.get("communities", []),
    }


def event_identity_title(value: str) -> str:
    """Normalize harmless calendar wording so duplicate public listings collapse."""
    title = normalized_text(value)
    title = re.sub(
        r"\b(?:\d+(?:st|nd|rd|th)|annual|traditional|competition|competitive)\b",
        " ",
        title,
    )
    title = re.sub(r"\b20\d{2}\b", " ", title)
    return clean_text(title)


def merge_events(existing: list[dict], candidates: list[dict], today: date | None = None, stats=None):
    today = today or utc_today()
    minimum = (today - timedelta(days=EVENT_WINDOW_PAST_DAYS)).isoformat()
    maximum = (today + timedelta(days=EVENT_WINDOW_FUTURE_DAYS)).isoformat()
    rows = []
    by_key = {}
    withdrawn=[r for r in candidates if r.get('eventStatus') in {'cancelled','postponed'} and float(r.get('confidence') or 0)>=.82]
    for item in [*existing, *candidates]:
        if any(str(w.get('bandId'))==str(item.get('bandId')) and canonical_url(w.get('sourceUrl'))==canonical_url(item.get('sourceUrl')) and (w.get('sourceUid') and w.get('sourceUid')==item.get('sourceUid') or event_identity_title(w.get('title'))==event_identity_title(item.get('title'))) for w in withdrawn):continue
        start = str(item.get("startDate") or "")
        url = canonical_url(item.get("sourceUrl"))
        if not (
            start <= maximum and str(item.get("endDate") or start) >= minimum
            and url.startswith("https://")
            and is_publishable_event(item, today)
        ):
            continue
        item = {**item, "status": event_status(start, item.get("endDate"), today)}
        identity = event_identity_title(item.get("title"))
        key = f"{item.get('bandId')}|{start}|{identity}"
        duplicate = next((
            old_key for old_key, old in by_key.items()
            if old.get("bandId") == item.get("bandId")
            and (
                (old.get("sourceUid") and old.get("sourceUid")==item.get("sourceUid"))
                or (old.get("sourceUrl") == url and old.get("startDate")==start and (
                    event_identity_title(old.get('title'))==identity
                    or SequenceMatcher(None,event_identity_title(old.get('title')),identity).ratio()>=.84
                ))
                or (
                    old.get("startDate") == start
                    and event_identity_title(old.get("title")) == identity
                )

            )
        ), None)
        if duplicate:
            if stats is not None:stats["duplicatesSuppressed"]=stats.get("duplicatesSuppressed",0)+1
            old = by_key[duplicate]
            item_quality = (bool(item.get("endDate")), float(item.get("confidence") or 0))
            old_quality = (bool(old.get("endDate")), float(old.get("confidence") or 0))
            if item_quality >= old_quality:
                item['id']=old.get('id') or item.get('id')
                item['discoveredAt']=old.get('discoveredAt') or item.get('discoveredAt')
                by_key[duplicate] = item
        else:
            by_key[key] = item
    rows = list(by_key.values())
    rows.sort(key=lambda item: (item.get("startDate", ""), item.get("title", "")))
    return rows


def is_publishable_event(item: dict, today: date | None = None) -> bool:
    """Reject directory pages, code noise, stale dates, and dates without event context."""
    title = clean_text(item.get("title"))
    description = clean_text(item.get("description"))
    url = canonical_url(item.get("sourceUrl"))
    method = str(item.get("extractionMethod") or "")
    normalized_title = normalized_text(title)
    path = urllib.parse.urlsplit(url).path.lower().rstrip("/")
    query = urllib.parse.urlsplit(url).query.lower()
    source_years = set(re.findall(r"(?<!\d)(20\d{2})(?!\d)", urllib.parse.unquote(url)))
    start_year = str(item.get("startDate") or "")[:4]
    if source_years and start_year not in source_years:
        return False
    try:
        start=date.fromisoformat(str(item.get('startDate') or ''))
        end=date.fromisoformat(str(item.get('endDate') or item.get('startDate') or ''))
        if end<start:return False
    except ValueError:return False
    if item.get('eventStatus') in {'cancelled','postponed'}:return False
    if not title or len(title) < 6 or len(title) > 165:
        return False
    if normalized_title in GENERIC_TITLES or normalized_title in {
        "communities", "information", "older posts", "apply now", "job postings",
        "news posts", "whats new", "about", "events calendar", "community calendar",
    }:
        return False
    if NON_EVENT_WORDS.search(f"{title} {description}"):
        return False
    if employment_item(title,url) and not re.search(r"\b(?:job|career) fair\b",title,re.I):return False
    if any(token in f"{title} {description}" for token in ("{ --", "grid-template", "googleanalytics", "monsterinsights", "function(", "var mi_")):
        return False
    if re.search(r"/(?:category|tag|author|page|about|news-posts|whats-new)(?:/|$)", path):
        return False
    if any(key in query for key in ("category=", "offset=", "page=")):
        return False
    if re.search(r"/events/\d{4}-\d{2}-\d{2}$", path):
        return False
    if path.endswith(("/events", "/calendar", "/events.html", "/announcements")) and method == "html-page":
        return False
    if method in {"json-ld","icalendar"}:
        return True
    if method=='eventer':
        occurrence=re.search(r'/eventer/[^/]+/edate/(20\d{2}-\d{2}-\d{2})/?$',path)
        return bool(occurrence and occurrence.group(1)==item.get('startDate') and any(d==item.get('startDate') for d,_ in explicit_event_dates(description)))
    if path in {'','/events','/calendar','/events.html','/announcements'} and not re.search(r'(?:eventid|event_id)=',query):return False
    if method == "meta-api":
        return is_event_text(title, description) and bool(explicit_event_dates(description))
    if method.startswith("ocr") or method in {"pdftotext", "html", "html-page", "html-calendar-detail", "shared-index"}:
        expected_start, _ = choose_event_date(title, description, today)
        if not expected_start or expected_start != str(item.get("startDate") or ""):
            return False
        if method.startswith("ocr") or method == "pdftotext":
            return is_event_text(title, description) and bool(explicit_event_dates(f"{title} {description}"))
        if not explicit_event_dates(f"{title} {description}"):
            return False
    explicit_date = bool(re.search(r"\b(?:event date|date|when|starts?|runs?|join us)\s*[:\-]?\s*", description, re.I))
    if method == 'html-calendar-detail':
        dated = re.search(r'/events?/(20\d{2}-\d{2}-\d{2})(?:[-/]|$)', path)
        return bool(dated and dated.group(1) == item.get('startDate') and explicit_date and is_event_text(title, description))
    title_has_event = bool(EVENT_WORDS.search(title))
    return title_has_event and (explicit_date or bool(event_dates(title)))


def scan_event_source(community,source,args,token,today):
    fetcher=Fetcher(delay=args.delay,timeout=args.timeout)
    run_row={'bandId':community['bandId'],'communityName':community['communityName'],'sourceName':source.get('name'),
             'sourceUrl':source.get('url'),'sourceType':source.get('type'),'status':'ok','eventsFound':0,'pagesChecked':0,'mediaChecked':0,'errors':[]}
    found=[];review=[]
    def issue(url,status,reason):review.append({'bandId':community['bandId'],'communityName':community['communityName'],'sourceUrl':url,'status':status,'reason':reason})
    if source.get('adapter')=='facebook':
        if not token or not (source.get('metaPageId') or source.get('pageHandle')):
            run_row['status']='authorized_api_required';issue(source.get('url'),'authorized_api_required','Facebook requires an authorized Meta API token and mapped page ID/handle')
        else:
            try:found=discover_meta_events(fetcher,community,source,token,today)
            except Exception as error:run_row.update(status=error_status(error),error=str(error)[:300])
        run_row['eventsFound']=len(found);return found,review,run_row
    queue=[source.get('url'),*(source.get('discoveryUrls') or [])];visited=set();media=[]
    while queue and len(visited)<args.max_pages_per_source:
        url=canonical_url(queue.pop(0))
        if not url or url in visited:continue
        visited.add(url)
        try:
            body,final_url,typ=fetcher.get(url)
            if 'calendar' in typ or final_url.lower().split('?')[0].endswith('.ics'):
                items,problems=extract_ical_events(body,final_url,community,source);found.extend(items)
                for problem in problems:issue(final_url,'calendar_review',problem['reason'])
                run_row['pagesChecked']+=1;continue
            if source.get('adapter')=='rss' or 'xml' in typ or body.lstrip().startswith((b'<?xml',b'<rss',b'<feed')):
                root=ET.fromstring(body)
                for entry in root.findall('.//item') or root.findall('.//{*}entry'):
                    def text(tag):return clean_text(entry.findtext(tag) or entry.findtext('{*}'+tag))
                    title=text('title');context=re.sub(r'<[^>]+>',' ',text('description') or text('summary') or text('content'))
                    link=text('link');link_node=entry.find('{*}link')
                    if not link and link_node is not None:link=link_node.get('href','')
                    if not link or not is_event_text(title,context) or not association_allowed(community,source,title,context):continue
                    start,end=choose_event_date(title,context,today)
                    if not start:continue
                    row=normalized_event(community,source,title=title,context=context,url=urllib.parse.urljoin(final_url,link),start=start,end=end,method='html')
                    row['dateSource']='explicit-event-text'
                    if text('guid') or text('id'):row['sourceUid']=text('guid') or text('id')
                    published,_=parse_date_text(text('published') or text('pubDate'))
                    if published:row.update(publishedAt=published,publicationDateSource='feed:published')
                    found.append(row)
                run_row['pagesChecked']+=1;continue
            if 'html' not in typ:issue(final_url,'unsupported_content_type',typ);continue
            markup=body.decode('utf-8',errors='replace');diagnostic=page_diagnostic(markup,final_url,community,source)
            if diagnostic:
                issue(final_url,diagnostic,'Source is not an identity-confirmed readable community page')
                if diagnostic=='javascript_required':queue[0:0]=feed_links(markup,final_url)
                continue
            run_row['pagesChecked']+=1
            page_events,links,page_media=extract_html_events(markup,final_url,community,source,today)
            found.extend(page_events);media.extend(page_media)
            for link in feed_links(markup,final_url)+links:
                if (urllib.parse.urlsplit(link).hostname or '').removeprefix('www.')==(urllib.parse.urlsplit(final_url).hostname or '').removeprefix('www.') and link not in visited and link not in queue:queue.append(link)
        except Exception as error:
            run_row['errors'].append({'url':url,'status':error_status(error),'reason':str(error)[:300]})
    for url in list(dict.fromkeys(media))[:args.max_media_per_source]:
        run_row['mediaChecked']+=1
        try:
            item=extract_media_event(fetcher,url,community,source,today)
            if item and association_allowed(community,source,item['title'],item.get('description','')):found.append(item)
        except Exception as error:issue(url,'media_extraction_failed',str(error)[:300])
    if run_row['errors']:run_row['status']='partial' if run_row['pagesChecked'] else run_row['errors'][0]['status']
    elif not run_row['pagesChecked']:run_row['status']=review[0]['status'] if review else 'unavailable'
    run_row['eventsFound']=len(found)
    source.update(lastCheckedAt=iso_now(),lastScanStatus=run_row['status'])
    if run_row['pagesChecked']:
        source['lastSuccessfulScanAt']=iso_now()
        if source.get('status')=='candidate':source['status']='verified'
    return found,review,run_row


def run(args):
    data = load_json(DATA_PATH, {"bands": []})
    news = load_json(NEWS_PATH, {"articles": [], "communitySources": []})
    current = load_json(EVENTS_PATH, {"schemaVersion": 1, "events": []})
    registry = source_registry(data, news, load_json(REGISTRY_PATH, {"communities": []}))
    fetcher = Fetcher(delay=args.delay, timeout=args.timeout)
    token = os.getenv("META_ACCESS_TOKEN")
    today = utc_today()
    candidates = []
    review = []
    runs = []
    communities = registry.get("communities", [])
    if args.band_id:
        selected = {str(value) for value in args.band_id}
        communities = [row for row in communities if str(row.get("bandId")) in selected]
    if args.province and args.province.upper() != "ALL":
        requested_province = args.province.upper()
        communities = [
            row for row in communities
            if str(row.get("provinceTerritory", "SK")).upper() == requested_province
        ]

    inputs=[(community,source) for community in communities for source in community.get('sources',[]) if source_is_monitorable(source)]
    with ThreadPoolExecutor(max_workers=max(1,getattr(args,'workers',6))) as executor:
        futures={executor.submit(scan_event_source,c,source,args,token,today):(c,source) for c,source in inputs}
        for future in as_completed(futures):
            found,issues,run_row=future.result();candidates.extend(found);review.extend(issues);runs.append(run_row)
            print(f"[{len(runs)}/{len(inputs)}] {run_row['bandId']} {run_row['sourceUrl']}: {run_row['status']} events={len(found)}",flush=True)

    for source in SHARED_EVENT_INDEXES:
        source_province = source.get("provinceTerritory")
        shared_communities = [
            row for row in communities
            if not source_province
            or str(row.get("provinceTerritory", "SK")).upper() == source_province
        ]
        if not shared_communities:
            continue
        run_row = {
            "bandId": None,
            "communityName": f"{source_province or 'Regional'} shared indexes",
            "sourceName": source["name"],
            "sourceUrl": source["url"],
            "sourceType": source["type"],
            "status": "ok",
            "eventsFound": 0,
            "pagesChecked": 0,
            "mediaChecked": 0,
        }
        found = []
        try:
            for url in [source["url"], *(source.get("discoveryUrls") or [])]:
                body, final_url, content_type = fetcher.get(url)
                run_row["pagesChecked"] += 1
                if "html" not in content_type:
                    continue
                found.extend(extract_shared_index_events(
                    body.decode("utf-8", errors="replace"),
                    final_url,
                    shared_communities,
                    source,
                    today,
                ))
            run_row["eventsFound"] = len(found)
            candidates.extend(found)
        except Exception as error:
            run_row["status"] = error_status(error)
            run_row["error"] = clean_text(error)[:300]
        runs.append(run_row)

    for candidate in candidates:
        if not is_publishable_event(candidate,today):
            review.append({'bandId':candidate.get('bandId'),'status':'held_for_review','reason':'Candidate lacks unambiguous event date/identity or has invalid/cancelled source data','originalRecord':candidate})
    for item in current.get("events", []):
        if not is_publishable_event(item, today):
            review.append({"status": "held_for_review", "reviewReason": "Existing event failed current source quality checks", "originalRecord": item})
    review = merge_update_reviews(load_json(REVIEW_PATH, {}).get("items", []), review, iso_now())
    merge_stats={}
    merged = merge_events(current.get("events", []), candidates, today,merge_stats)
    changes=track_changes(current.get('events',[]),merged,iso_now(),'events')
    archive={str(r.get('id')):r for r in current.get('archivedEvents',[])}
    minimum=(today-timedelta(days=EVENT_WINDOW_PAST_DAYS)).isoformat()
    for item in current.get('events',[]):
        if str(item.get('endDate') or item.get('startDate') or '')<minimum and is_publishable_event(item,today):
            archive[str(item['id'])]={**item,'status':'Expired','archivedAt':iso_now()}
    for item in candidates:
        if item.get('eventStatus') in {'cancelled','postponed'}:archive[str(item['id'])]={**item,'status':item['eventStatus'].title(),'archivedAt':iso_now()}
    frontend_sources = [
        {"bandId": row["bandId"], "communityName": row["communityName"], "sources": [{key: source.get(key) for key in ("type", "name", "url", "status", "lastScanStatus", "lastCheckedAt", "lastSuccessfulScanAt") if source.get(key) is not None} for source in row.get("sources", [])]}
        for row in registry.get("communities", [])
    ]
    output = {
        "schemaVersion": 1,
        "generated": iso_now(),
        "coverage": {"trackedCommunities": len(data.get("bands", [])), "communitiesWithEvents": len({str(item.get("bandId")) for item in merged}), "events": len(merged), "upcoming": sum(item.get("status") in {"Upcoming", "Ongoing"} for item in merged)},
        "events": merged,
        "archivedEvents":list(archive.values()),
        "communitySources": frontend_sources,
    }
    report={"schemaVersion":2,"generated":iso_now(),"scanScope":{"communityIds":[str(r['bandId']) for r in communities],"communitiesScanned":len(communities),"fullScan":len(communities)==len(registry.get('communities',[]))},
            'before':len(current.get('events',[])),'after':len(merged),'newCandidates':len(candidates),'sourceRuns':runs,'reviewCount':len(review),
            'statusCounts':dict(Counter(r['status'] for r in runs)),'recordChanges':changes,'duplicatesSuppressed':merge_stats.get('duplicatesSuppressed',0),'expiredArchived':len(archive),
            'quality':quality_metrics(registry,merged,runs,review,today,'events')}
    if not getattr(args,'dry_run',False):
        write_json(EVENTS_PATH,output);write_json(REGISTRY_PATH,registry)
        write_json(REVIEW_PATH,{'schemaVersion':1,'generated':iso_now(),'items':review});write_json(REPORT_PATH,report)
    print(json.dumps(output["coverage"], indent=2))
    return report


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--band-id", action="append", default=[])
    parser.add_argument("--province", type=str.upper, choices=["SK", "AB", "MB", "ALL"])
    parser.add_argument("--workers",type=int,default=6)
    parser.add_argument("--dry-run",action="store_true")
    parser.add_argument("--delay", type=float, default=0.3)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--max-pages-per-source", type=int, default=6)
    parser.add_argument("--max-media-per-source", type=int, default=3)
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
