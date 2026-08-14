#!/usr/bin/env python3
"""Discover source-backed Saskatchewan First Nation community events.

Only events that pass the public publish gate are written to the site dataset.
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
    )


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
EVENT_WORDS = re.compile(
    r"\b(pow[ -]?wow|wacipi|round dance|treaty day|feast|gathering|ceremony|"
    r"celebration|community (?:meeting|event|clean[ -]?up)|annual general meeting|agm|"
    r"open house|workshop|training|conference|forum|fair|clinic|screening|"
    r"tournament|relay race|races|rodeo|bingo|fundraiser|market|festival|parade|camp|youth day|"
    r"family day|language class|culture camp|land-based|sports day|information session|"
    r"election day|vote|meeting|event)\b",
    re.I,
)
NON_EVENT_WORDS = re.compile(
    r"\b(job posting|job opportunity|employment opportunity|opportunities|request for proposals?|rpf|rfp|tender|"
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
    r"(?:\s*(?:-|–|to)\s*(\d{1,2})(?:st|nd|rd|th)?)?(?:,?\s*(20\d{2}))?\b",
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


def event_category(value: str) -> str:
    text = normalized_text(value)
    rules = [
        (r"pow ?wow|wacipi|round dance|feast|ceremony|culture|language|land based", "Culture & Language"),
        (r"treaty day", "Treaty Days"),
        (r"health|clinic|screening|wellness|healing", "Health & Wellness"),
        (r"youth|family|children|kids|camp", "Youth & Family"),
        (r"tournament|sports|hockey|softball|rodeo|golf", "Recreation & Sports"),
        (r"training|workshop|class|education|conference|forum", "Education & Training"),
        (r"election|vote|annual general meeting|agm|community meeting|council", "Governance & Meetings"),
        (r"emergency|evacuation|wildfire", "Emergency Information"),
    ]
    for pattern, category in rules:
        if re.search(pattern, text):
            return category
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


def event_dates(value: str, today: date | None = None) -> list[tuple[str, str | None]]:
    """Return unique event date ranges found in text, including yearless flyers."""
    today = today or utc_today()
    rows = []
    seen = set()
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


def choose_event_date(title: str, context: str, today: date | None = None):
    today = today or utc_today()
    minimum = today - timedelta(days=EVENT_WINDOW_PAST_DAYS)
    maximum = today + timedelta(days=EVENT_WINDOW_FUTURE_DAYS)
    title_dates = event_dates(title, today)
    context_dates = event_dates(context, today)
    viable = [row for row in title_dates + context_dates if minimum <= date.fromisoformat(row[0]) <= maximum]
    if not viable:
        return None, None
    upcoming = [row for row in viable if date.fromisoformat(row[0]) >= today]
    selected = min(upcoming or viable, key=lambda row: abs((date.fromisoformat(row[0]) - today).days))
    return selected


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
    return bool(EVENT_WORDS.search(text)) and not bool(NON_EVENT_WORDS.search(text))


def event_id(community: dict, start: str, title: str) -> str:
    digest = hashlib.sha1(
        f"{community.get('bandId')}|{start}|{normalized_text(title)}".encode("utf-8")
    ).hexdigest()[:10]
    return f"{slugify(community.get('communityName'))}-{start}-{digest}"


def event_title(title: str, context: str) -> str:
    title = clean_text(title)
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
        "provinceTerritory": "SK",
        "title": title,
        "category": event_category(f"{title} {context}"),
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

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
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
            if self.in_title:
                self.page_title = clean_text(f"{self.page_title} {value}")

    def handle_endtag(self, tag):
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


def extract_jsonld_events(parser: EventPageParser, page_url: str, community: dict, source: dict) -> list[dict]:
    rows = []
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
            start, _ = parse_date_text(item.get("startDate"))
            end, _ = parse_date_text(item.get("endDate"))
            title = clean_text(item.get("name"))
            context = clean_text(f"{item.get('description', '')} {item.get('startDate', '')}")
            if not start or not title or not is_event_text(title, context):
                continue
            location = item.get("location") or {}
            if isinstance(location, dict):
                context = clean_text(f"{context} Location: {location.get('name', '')}")
            image = item.get("image")
            image = image[0] if isinstance(image, list) and image else image
            rows.append(normalized_event(community, source, title=title, context=context, url=item.get("url") or page_url, start=start, end=end, image=image, method="json-ld"))
    return rows


def extract_html_events(html: str, page_url: str, community: dict, source: dict, today: date | None = None):
    parser = EventPageParser()
    parser.feed(html)
    events = extract_jsonld_events(parser, page_url, community, source)
    follow = []
    media = []
    seen = {item["sourceUrl"] for item in events}
    for row in parser.anchor_rows():
        url = canonical_url(urllib.parse.urljoin(page_url, row["href"]))
        combined = clean_text(f"{row['title']} {row['context']}")
        if FOLLOW_LINK_WORDS.search(combined) and url.startswith("http"):
            follow.append(url)
        if re.search(r"\.(?:pdf|png|jpe?g)(?:$|\?)", url, re.I) and is_event_text(row["title"], row["context"]):
            media.append(url)
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
    if not events and is_event_text(parser.page_title, parser.page_text):
        start, end = choose_event_date(parser.page_title, parser.page_text, today)
        if start and canonical_url(page_url) not in seen:
            events.append(normalized_event(community, source, title=parser.page_title, context=parser.page_text, url=page_url, start=start, end=end, method="html-page"))
    return events, list(dict.fromkeys(follow)), list(dict.fromkeys(media))


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
            known = {canonical_url(source.get("url")) for source in community.get("sources", [])}
            for source in override["sources"]:
                if canonical_url(source.get("url")) not in known:
                    community.setdefault("sources", []).append(source)
    return {
        "schemaVersion": 1,
        "generated": iso_now(),
        "notes": "Event discovery sources are derived from the verified News registry. Add event-specific calendars here when found.",
        "communities": merged.get("communities", []),
    }


def merge_events(existing: list[dict], candidates: list[dict], today: date | None = None):
    today = today or utc_today()
    minimum = (today - timedelta(days=EVENT_WINDOW_PAST_DAYS)).isoformat()
    maximum = (today + timedelta(days=EVENT_WINDOW_FUTURE_DAYS)).isoformat()
    rows = []
    by_key = {}
    for item in [*existing, *candidates]:
        start = str(item.get("startDate") or "")
        url = canonical_url(item.get("sourceUrl"))
        if not (minimum <= start <= maximum and url.startswith("https://") and is_publishable_event(item)):
            continue
        key = f"{item.get('bandId')}|{start}|{normalized_text(item.get('title'))}"
        duplicate = next((old_key for old_key, old in by_key.items() if old.get("bandId") == item.get("bandId") and old.get("startDate") == start and (old.get("sourceUrl") == url or normalized_text(old.get("title")) == normalized_text(item.get("title")))), None)
        if duplicate:
            if float(item.get("confidence") or 0) > float(by_key[duplicate].get("confidence") or 0):
                by_key[duplicate] = item
        else:
            by_key[key] = item
    rows = list(by_key.values())
    rows.sort(key=lambda item: (item.get("startDate", ""), item.get("title", "")))
    return rows


def is_publishable_event(item: dict) -> bool:
    """Reject directory pages, code noise, and dates without event context."""
    title = clean_text(item.get("title"))
    description = clean_text(item.get("description"))
    url = canonical_url(item.get("sourceUrl"))
    method = str(item.get("extractionMethod") or "")
    normalized_title = normalized_text(title)
    path = urllib.parse.urlsplit(url).path.lower().rstrip("/")
    query = urllib.parse.urlsplit(url).query.lower()
    if not title or len(title) < 6 or len(title) > 165:
        return False
    if normalized_title in GENERIC_TITLES or normalized_title in {
        "communities", "information", "older posts", "apply now", "job postings",
        "news posts", "whats new", "about", "events calendar", "community calendar",
    }:
        return False
    if NON_EVENT_WORDS.search(f"{title} {description}"):
        return False
    if any(token in f"{title} {description}" for token in ("{ --", "grid-template", "googleanalytics", "monsterinsights", "function(", "var mi_")):
        return False
    if re.search(r"/(?:category|tag|author|page|about|news-posts|whats-new)(?:/|$)", path):
        return False
    if any(key in query for key in ("category=", "offset=", "page=")):
        return False
    if path.endswith(("/events", "/calendar", "/events.html", "/announcements")) and method == "html-page":
        return False
    if method == "json-ld":
        return True
    if method.startswith("ocr") or method == "pdftotext":
        return is_event_text(title, description)
    if method == "meta-api":
        return is_event_text(title, description) and bool(event_dates(description))
    explicit_date = bool(re.search(r"\b(?:event date|date|when|starts?|runs?|join us)\s*[:\-]?\s*", description, re.I))
    title_has_event = bool(EVENT_WORDS.search(title))
    return title_has_event and (explicit_date or bool(event_dates(title)))


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

    for community in communities:
        for source in community.get("sources") or []:
            if not source_is_monitorable(source):
                continue
            run_row = {"bandId": community["bandId"], "communityName": community["communityName"], "sourceName": source.get("name"), "sourceUrl": source.get("url"), "sourceType": source.get("type"), "status": "ok", "eventsFound": 0, "pagesChecked": 0, "mediaChecked": 0}
            found = []
            try:
                if source.get("adapter") == "facebook":
                    if not token:
                        run_row["status"] = "authorized_api_required"
                    else:
                        found.extend(discover_meta_events(fetcher, community, source, token, today))
                else:
                    queue = [source.get("url"), *(source.get("discoveryUrls") or [])]
                    visited = set()
                    media = []
                    while queue and len(visited) < args.max_pages_per_source:
                        url = canonical_url(queue.pop(0))
                        if not url or url in visited:
                            continue
                        visited.add(url)
                        body, final_url, content_type = fetcher.get(url)
                        run_row["pagesChecked"] += 1
                        if "html" not in content_type:
                            continue
                        page_events, links, page_media = extract_html_events(body.decode("utf-8", errors="replace"), final_url, community, source, today)
                        found.extend(page_events)
                        media.extend(page_media)
                        for link in links:
                            if urllib.parse.urlsplit(link).netloc == urllib.parse.urlsplit(final_url).netloc and link not in visited:
                                queue.append(link)
                    for media_url in list(dict.fromkeys(media))[:args.max_media_per_source]:
                        run_row["mediaChecked"] += 1
                        try:
                            item = extract_media_event(fetcher, media_url, community, source, today)
                            if item:
                                found.append(item)
                        except Exception as error:
                            review.append({"bandId": community["bandId"], "communityName": community["communityName"], "sourceUrl": media_url, "reason": f"media extraction failed: {error}"})
                run_row["eventsFound"] = len(found)
                candidates.extend(found)
            except Exception as error:
                run_row["status"] = "failed"
                run_row["error"] = clean_text(error)[:300]
            runs.append(run_row)

    merged = merge_events(current.get("events", []), candidates, today)
    frontend_sources = [
        {"bandId": row["bandId"], "communityName": row["communityName"], "sources": [{key: source.get(key) for key in ("type", "name", "url", "status") if source.get(key) is not None} for source in row.get("sources", [])]}
        for row in registry.get("communities", [])
    ]
    output = {
        "schemaVersion": 1,
        "generated": iso_now(),
        "coverage": {"trackedCommunities": len(data.get("bands", [])), "communitiesWithEvents": len({str(item.get("bandId")) for item in merged}), "events": len(merged), "upcoming": sum(item.get("status") in {"Upcoming", "Ongoing"} for item in merged)},
        "events": merged,
        "communitySources": frontend_sources,
    }
    write_json(EVENTS_PATH, output)
    write_json(REGISTRY_PATH, registry)
    write_json(REVIEW_PATH, {"schemaVersion": 1, "generated": iso_now(), "items": review})
    write_json(REPORT_PATH, {"schemaVersion": 1, "generated": iso_now(), "before": len(current.get("events", [])), "after": len(merged), "newCandidates": len(candidates), "sourceRuns": runs, "reviewCount": len(review), "statusCounts": dict(sorted({status: sum(row["status"] == status for row in runs) for status in {row["status"] for row in runs}}.items()))})
    print(json.dumps(output["coverage"], indent=2))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--band-id", action="append", default=[])
    parser.add_argument("--delay", type=float, default=0.3)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--max-pages-per-source", type=int, default=6)
    parser.add_argument("--max-media-per-source", type=int, default=3)
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
