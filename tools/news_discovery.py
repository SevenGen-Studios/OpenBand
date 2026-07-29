#!/usr/bin/env python3
"""Discover and normalize source-backed Saskatchewan community updates."""

from __future__ import annotations

import argparse
import email.utils
import hashlib
import html as html_module
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data.json"
NEWS_PATH = ROOT / "news-data.json"
REGISTRY_PATH = ROOT / "news-sources.json"
CACHE_PATH = ROOT / "news-discovery-cache.json"
REVIEW_PATH = ROOT / "news-review-queue.json"
REPORT_PATH = ROOT / "news-coverage-report.json"

USER_AGENT = "OpenBandNews/1.0 (+https://openband.ca/news/)"
SOURCE_TYPES = [
    "Traditional News",
    "Official First Nation Website",
    "Community Website",
    "Facebook",
    "Community Notice",
    "Newsletter",
    "Tribal Council",
    "School or Health Organization",
    "Economic Development Organization",
    "Government Source",
]
PILOT_BAND_IDS = {406, 371, 395, 361, 352}
OFFICIAL_SOURCE_TYPES = {
    "Official First Nation Website",
    "Community Website",
    "Community Notice",
    "Newsletter",
    "Facebook",
}
AUTHORITATIVE_RANK = {
    "Official First Nation Website": 100,
    "Community Website": 96,
    "Community Notice": 94,
    "Newsletter": 92,
    "Facebook": 90,
    "School or Health Organization": 87,
    "Economic Development Organization": 86,
    "Tribal Council": 84,
    "Government Source": 80,
    "Traditional News": 60,
}
GENERIC_LINK_TEXT = {
    "home",
    "about",
    "contact",
    "read more",
    "learn more",
    "news",
    "events",
    "careers",
    "view all",
    "click here",
    "download",
    "previous",
    "next",
}
EXCLUDED_PATTERNS = re.compile(
    r"\b(happy birthday|birthday wishes|good morning|good night|meme|"
    r"like and share|tag (?:a|your) friend|contest|giveaway|winner|"
    r"generic greeting|daily quote)\b",
    re.I,
)
SUPPORTED_PATTERNS = re.compile(
    r"\b(announcement|notice|update|funding|grant|construction|infrastructure|"
    r"housing|meeting|annual general meeting|agm|election|governance|council|"
    r"employment|job|career|training|business|economic|health|safety|school|"
    r"education|land|resource|environment|event|powwow|emergency|evacuation|"
    r"program|service|partnership|agreement|newsletter|year in review|agenda|"
    r"claim|settlement|water|treatment plant|application|community|recreation|"
    r"culture|language|justice|public works|development)\b",
    re.I,
)
DATE_PATTERNS = [
    re.compile(
        r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
        r"Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?"
        r"(?:\s*(?:-|to)\s*\d{1,2}(?:st|nd|rd|th)?)?,?\s+(\d{4})\b",
        re.I,
    ),
    re.compile(
        r"\b(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
        r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
        r"Nov(?:ember)?|Dec(?:ember)?)\s+(\d{4})\b",
        re.I,
    ),
    re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b"),
    re.compile(r"\b(20\d{2})(\d{2})(\d{2})T\d{6}Z?\b"),
]
MONTH_YEAR_RE = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\s+(20\d{2})\b",
    re.I,
)
MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_now():
    return utc_now().isoformat().replace("+00:00", "Z")


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def clean_text(value):
    return " ".join(str(value or "").replace("\xa0", " ").split())


def normalized_text(value):
    value = unicodedata.normalize("NFKD", clean_text(value))
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower().replace("&", " and ").replace("’", "'")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def slugify(value):
    return "-".join(normalized_text(value).split())


def canonical_url(value):
    if not value:
        return ""
    parts = urllib.parse.urlsplit(value)
    query = [
        (key, item)
        for key, item in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"fbclid", "gclid", "mc_cid", "mc_eid"}
    ]
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urllib.parse.urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urllib.parse.urlencode(query), "")
    )


def parse_date_text(value):
    text = clean_text(value)
    if not text:
        return None, None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.date().isoformat(), "day"
    except ValueError:
        pass

    for index, pattern in enumerate(DATE_PATTERNS):
        match = pattern.search(text)
        if not match:
            continue
        try:
            if index == 0:
                month, day, year = match.groups()
            elif index == 1:
                day, month, year = match.groups()
            elif index == 2:
                year, month, day = match.groups()
                return date(int(year), int(month), int(day)).isoformat(), "day"
            else:
                year, month, day = match.groups()
                return date(int(year), int(month), int(day)).isoformat(), "day"
            return date(int(year), MONTHS[month[:3].lower()], int(day)).isoformat(), "day"
        except ValueError:
            continue

    match = MONTH_YEAR_RE.search(text)
    if match:
        month, year = match.groups()
        return date(int(year), MONTHS[month[:3].lower()], 1).isoformat(), "month"
    return None, None


def classify_category(value):
    text = normalized_text(value)
    rules = [
        ("Elections", r"\belection|ballot|candidate|nomination\b"),
        ("Financial", r"\bfinancial|audit|budget|remuneration\b"),
        ("Infrastructure", r"\binfrastructure|construction|public works|water|road|capital\b"),
        ("Housing", r"\bhousing|cmhc|home repair\b"),
        ("Healthcare", r"\bhealth|clinic|wellness|medical|safety\b"),
        ("Education", r"\bschool|education|student|scholarship|tuition\b"),
        ("Business & Economic Development", r"\bbusiness|economic|venture|investment\b"),
        ("Employment", r"\bemployment|career|job|hiring|training\b"),
        ("Funding & Grants", r"\bfunding|grant|investment announcement\b"),
        ("Land Claims", r"\bland claim|specific claim|settlement claim\b"),
        ("Treaties", r"\btreaty|entitlement|tle\b"),
        ("Environment", r"\benvironment|climate|wildlife|forestry\b"),
        ("Culture & Language", r"\bculture|language|traditional|elder|powwow\b"),
        ("Justice", r"\bjustice|police|tribunal|court\b"),
        ("Emergencies", r"\bemergency|evacuation|wildfire|boil water|closure\b"),
        ("Governance", r"\bgovernance|chief|council|agm|annual general meeting\b"),
        ("Community Events", r"\bevent|meeting|homecoming|sports|recreation|agenda\b"),
    ]
    for category, pattern in rules:
        if re.search(pattern, text):
            return category
    return "Other"


def source_confidence(source):
    if source.get("associationConfidence") is not None:
        return float(source["associationConfidence"])
    if source.get("official"):
        return 0.98
    if source.get("type") in {"Tribal Council", "Government Source"}:
        return 0.84
    return 0.78


def source_is_monitorable(source):
    return (
        source.get("monitor", True)
        and source.get("status") in {"verified", "baseline"}
        and source.get("adapter") in {"html", "rss", "facebook"}
    )


class Fetcher:
    def __init__(self, delay=0.35, timeout=25):
        self.delay = delay
        self.timeout = timeout
        self.robots = {}
        self.last_request = 0.0

    def _pace(self):
        wait = self.delay - (time.monotonic() - self.last_request)
        if wait > 0:
            time.sleep(wait)

    def allowed(self, url):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in {"http", "https"}:
            return False
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.robots:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(origin + "/robots.txt")
            try:
                request = urllib.request.Request(
                    origin + "/robots.txt", headers={"User-Agent": USER_AGENT}
                )
                self._pace()
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    robots_text = response.read().decode("utf-8", errors="replace")
                self.last_request = time.monotonic()
                parser.parse(robots_text.splitlines())
                self.robots[origin] = parser
            except Exception:
                self.robots[origin] = None
        parser = self.robots[origin]
        return True if parser is None else parser.can_fetch(USER_AGENT, url)

    def get(self, url, headers=None, respect_robots=True):
        if respect_robots and not self.allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        request_headers.update(headers or {})
        request = urllib.request.Request(url, headers=request_headers)
        self._pace()
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = response.read()
            final_url = response.geturl()
            content_type = response.headers.get_content_type()
        self.last_request = time.monotonic()
        return body, final_url, content_type


def item_summary(title, block_text, source_name):
    text = clean_text(block_text)
    if title and text.lower().startswith(title.lower()):
        text = clean_text(text[len(title) :])
    text = re.sub(
        r"^(?:[A-Z][a-z]{2,8}\s+\d{1,2},?\s+20\d{2}|\d{4}-\d{2}-\d{2})\s*",
        "",
        text,
    )
    if len(text) < 35:
        text = f"{source_name} published this community update."
    return text[:420].rstrip(" ,.;") + "."


def candidate_id(community, published, title):
    digest = hashlib.sha1(
        f"{community.get('bandId')}|{published}|{normalized_text(title)}".encode("utf-8")
    ).hexdigest()[:10]
    return f"{slugify(community.get('communityName'))}-{published}-{digest}"


def normalized_candidate(
    community,
    source,
    *,
    title,
    summary,
    url,
    published,
    date_precision="day",
    thumbnail=None,
):
    source_type = source.get("type") or "Community Website"
    item = {
        "id": candidate_id(community, published, title),
        "storyKey": f"{community.get('bandId')}-{published}-{slugify(title)[:80]}",
        "title": clean_text(title),
        "communityName": community["communityName"],
        "communityAliases": community.get("aliases") or [],
        "provinceTerritory": "SK",
        "category": classify_category(f"{title} {summary}"),
        "sourceType": source_type,
        "sourceName": source.get("name") or community["communityName"],
        "publishedAt": published,
        "datePrecision": date_precision,
        "url": canonical_url(url),
        "summary": clean_text(summary),
        "tags": ["community-update", "source-backed"],
        "bandId": community["bandId"],
        "discoveredAt": iso_now(),
        "communityConfidence": round(source_confidence(source), 2),
    }
    if thumbnail and str(thumbnail).startswith("http"):
        item["thumbnail"] = canonical_url(thumbnail)
    return item


class CommunityHTMLParser(HTMLParser):
    """Collect links with the nearest article-like text block."""

    BLOCK_TAGS = {"article", "li"}
    BLOCK_CLASS_TOKENS = {"post", "news", "event", "card", "entry", "update", "notice"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.stack = []
        self.blocks = []
        self.anchors = []
        self.active_anchor = None
        self.default_image = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(" ".join(attrs.get("class", "").split()).lower().split())
        is_block = tag in self.BLOCK_TAGS or (
            tag == "div"
            and any(
                token in class_name
                for token in self.BLOCK_CLASS_TOKENS
                for class_name in classes
            )
        )
        node = {
            "tag": tag,
            "is_block": is_block,
            "start": len(self.parts),
            "anchors": [],
            "image": None,
        }
        self.stack.append(node)
        if is_block:
            self.blocks.append(node)
        if tag == "meta" and attrs.get("property") == "og:image":
            self.default_image = attrs.get("content")
        elif tag == "img" and attrs.get("src") and self.blocks:
            self.blocks[-1]["image"] = attrs["src"]
        elif tag == "time" and attrs.get("datetime"):
            self.parts.append(attrs["datetime"])
        elif tag == "a" and attrs.get("href"):
            self.active_anchor = {
                "href": attrs["href"],
                "start": len(self.parts),
                "end": None,
                "context": None,
                "image": None,
            }
            self.anchors.append(self.active_anchor)
            if self.blocks:
                self.blocks[-1]["anchors"].append(len(self.anchors) - 1)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data):
        text = clean_text(data)
        if text:
            self.parts.append(text)

    def handle_endtag(self, tag):
        if tag == "a" and self.active_anchor is not None:
            self.active_anchor["end"] = len(self.parts)
            self.active_anchor = None
        match_index = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                match_index = index
                break
        if match_index is None:
            return
        closing = self.stack[match_index:]
        self.stack = self.stack[:match_index]
        for node in reversed(closing):
            if not node["is_block"]:
                continue
            context = clean_text(" ".join(self.parts[node["start"] :]))
            for anchor_index in node["anchors"]:
                anchor = self.anchors[anchor_index]
                if anchor["context"] is None:
                    anchor["context"] = context
                    anchor["image"] = node.get("image")
            if node in self.blocks:
                self.blocks.remove(node)

    def results(self):
        rows = []
        for anchor in self.anchors:
            start = anchor["start"]
            end = anchor["end"] if anchor["end"] is not None else start
            title = clean_text(" ".join(self.parts[start:end]))
            context = anchor["context"]
            if context is None:
                context = clean_text(
                    " ".join(self.parts[max(0, start - 8) : min(len(self.parts), end + 18)])
                )
            rows.append(
                {
                    "href": anchor["href"],
                    "title": title,
                    "context": context,
                    "image": anchor.get("image") or self.default_image,
                }
            )
        return rows


def is_supported_update(title, context=""):
    text = clean_text(f"{title} {context}")
    if EXCLUDED_PATTERNS.search(text):
        return False
    return bool(SUPPORTED_PATTERNS.search(text))


def extract_html_candidates(html, page_url, community, source):
    parser = CommunityHTMLParser()
    parser.feed(html)
    candidates = []
    seen = set()
    for anchor in parser.results():
        title = anchor["title"]
        if (
            len(title) < 8
            or len(title) > 180
            or normalized_text(title) in GENERIC_LINK_TEXT
        ):
            continue
        url = canonical_url(urllib.parse.urljoin(page_url, anchor["href"]))
        if not url.startswith("http") or url in seen:
            continue
        if urllib.parse.urlsplit(url).netloc.endswith("facebook.com"):
            continue

        block_text = anchor["context"] or title
        published, precision = parse_date_text(block_text or title)
        if not published:
            published, precision = parse_date_text(title)
        if not published or not is_supported_update(title, block_text):
            continue

        thumbnail = (
            urllib.parse.urljoin(page_url, anchor["image"])
            if anchor.get("image")
            else None
        )
        candidates.append(
            normalized_candidate(
                community,
                source,
                title=title,
                summary=item_summary(title, block_text, source.get("name", "The source")),
                url=url,
                published=published,
                date_precision=precision,
                thumbnail=thumbnail,
            )
        )
        seen.add(url)
    return candidates


def xml_text(node, names):
    for name in names:
        value = node.findtext(name)
        if value:
            return clean_text(value)
    return ""


def extract_feed_candidates(xml_bytes, feed_url, community, source):
    root = ET.fromstring(xml_bytes)
    entries = list(root.findall(".//item"))
    if not entries:
        entries = list(root.findall(".//{*}entry"))
    candidates = []
    for entry in entries:
        title = xml_text(entry, ["title", "{*}title"])
        link = xml_text(entry, ["link", "{*}link"])
        if not link:
            link_node = entry.find("{*}link")
            link = link_node.get("href", "") if link_node is not None else ""
        summary = xml_text(
            entry,
            ["description", "summary", "{*}summary", "{*}content"],
        )
        raw_date = xml_text(
            entry,
            ["pubDate", "published", "updated", "{*}published", "{*}updated"],
        )
        try:
            parsed = email.utils.parsedate_to_datetime(raw_date)
            published = parsed.date().isoformat()
        except (TypeError, ValueError, OverflowError):
            published, _ = parse_date_text(raw_date)
        if not title or not link or not published or not is_supported_update(title, summary):
            continue
        candidates.append(
            normalized_candidate(
                community,
                source,
                title=title,
                summary=clean_text(
                    html_module.unescape(re.sub(r"<[^>]+>", " ", summary))
                ),
                url=urllib.parse.urljoin(feed_url, link),
                published=published,
            )
        )
    return candidates


def discover_meta_posts(fetcher, community, source, access_token):
    page_id = source.get("metaPageId") or source.get("pageHandle")
    if not access_token or not page_id:
        return []
    version = os.getenv("META_API_VERSION", "v23.0")
    fields = "message,created_time,permalink_url,full_picture"
    query = urllib.parse.urlencode(
        {"fields": fields, "limit": "25"}
    )
    url = f"https://graph.facebook.com/{version}/{page_id}/posts?{query}"
    body, _, _ = fetcher.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        respect_robots=False,
    )
    payload = json.loads(body.decode("utf-8"))
    candidates = []
    for post in payload.get("data", []):
        message = clean_text(post.get("message"))
        if len(message) < 15 or not is_supported_update(message):
            continue
        published, _ = parse_date_text(post.get("created_time"))
        if not published or not post.get("permalink_url"):
            continue
        first_sentence = re.split(r"(?<=[.!?])\s+", message, maxsplit=1)[0]
        label = first_sentence[:110].rstrip(" ,.;:-")
        candidates.append(
            normalized_candidate(
                community,
                source,
                title=f"{label} (community post)",
                summary=message[:420],
                url=post["permalink_url"],
                published=published,
                thumbnail=post.get("full_picture"),
            )
        )
    return candidates


def community_name_match(community, value):
    """Require an exact normalized community name or a useful exact alias."""
    haystack = f" {normalized_text(value)} "
    names = [community.get("communityName")] + list(community.get("aliases") or [])
    for name in names:
        normalized = normalized_text(name)
        if len(normalized) >= 5 and f" {normalized} " in haystack:
            return True
    return False


def discover_gdelt_articles(fetcher, community):
    """Search GDELT's free public index and retain direct, strongly matched links."""
    params = urllib.parse.urlencode(
        {
            "query": f'"{community["communityName"]}" Saskatchewan',
            "mode": "ArtList",
            "maxrecords": "25",
            "format": "json",
            "sort": "DateDesc",
        }
    )
    body, _, _ = fetcher.get(
        f"https://api.gdeltproject.org/api/v2/doc/doc?{params}",
        headers={"Accept": "application/json"},
    )
    payload = json.loads(body.decode("utf-8", errors="replace"))
    candidates = []
    for article in payload.get("articles") or []:
        title = clean_text(article.get("title"))
        original_url = canonical_url(article.get("url"))
        if (
            not title
            or not original_url.startswith("https://")
            or not community_name_match(community, title)
            or not is_supported_update(title)
        ):
            continue
        published, precision = parse_date_text(article.get("seendate"))
        if not published:
            continue
        source_name = clean_text(article.get("domain")) or urllib.parse.urlsplit(
            original_url
        ).netloc
        source = {
            "type": "Traditional News",
            "name": source_name,
            "official": False,
            "associationConfidence": 0.86,
        }
        candidates.append(
            normalized_candidate(
                community,
                source,
                title=title,
                summary=(
                    f"{source_name} published this report concerning "
                    f"{community['communityName']}."
                ),
                url=original_url,
                published=published,
                date_precision=precision,
                thumbnail=article.get("socialimage"),
            )
        )
    return candidates


def communities_for_targeted_search(communities, articles, *, limit, pilot, cursor):
    """Rotate searches across communities lacking a result from the last 90 days."""
    if pilot:
        return communities, cursor
    cutoff = (utc_now().date() - timedelta(days=90)).isoformat()
    recent_band_ids = {
        str(item.get("bandId"))
        for item in articles
        if str(item.get("publishedAt") or "") >= cutoff
    }
    undercovered = [
        community
        for community in communities
        if str(community.get("bandId")) not in recent_band_ids
    ]
    if not undercovered or limit <= 0:
        return [], cursor
    start = cursor % len(undercovered)
    count = min(limit, len(undercovered))
    selected = [
        undercovered[(start + offset) % len(undercovered)]
        for offset in range(count)
    ]
    return selected, (start + count) % len(undercovered)


def titles_match(left, right):
    return SequenceMatcher(
        None, normalized_text(left), normalized_text(right)
    ).ratio() >= 0.84


def merge_articles(existing, candidates):
    merged = [dict(item) for item in existing]
    accepted = []
    for candidate in candidates:
        duplicate_index = None
        candidate_url = canonical_url(candidate.get("url"))
        for index, current in enumerate(merged):
            if str(current.get("bandId")) != str(candidate.get("bandId")):
                continue
            same_url = canonical_url(current.get("url")) == candidate_url
            close_story = (
                current.get("publishedAt") == candidate.get("publishedAt")
                and titles_match(current.get("title"), candidate.get("title"))
            )
            if same_url or close_story:
                duplicate_index = index
                break
        if duplicate_index is None:
            merged.append(candidate)
            accepted.append(candidate)
            continue

        current = merged[duplicate_index]
        alternate = list(current.get("alternateSources") or [])
        current_rank = AUTHORITATIVE_RANK.get(current.get("sourceType"), 0)
        candidate_rank = AUTHORITATIVE_RANK.get(candidate.get("sourceType"), 0)
        if candidate_rank > current_rank:
            candidate["alternateSources"] = alternate + [
                {
                    "sourceName": current.get("sourceName"),
                    "sourceType": current.get("sourceType"),
                    "url": current.get("url"),
                }
            ]
            merged[duplicate_index] = candidate
        elif canonical_url(current.get("url")) != candidate_url:
            alternate.append(
                {
                    "sourceName": candidate.get("sourceName"),
                    "sourceType": candidate.get("sourceType"),
                    "url": candidate.get("url"),
                }
            )
            current["alternateSources"] = list(
                {
                    canonical_url(item.get("url")): item
                    for item in alternate
                    if item.get("url")
                }.values()
            )
    merged.sort(key=lambda item: str(item.get("publishedAt") or ""), reverse=True)
    return merged, accepted


def build_coverage_report(registry, articles, review, failures, before_count, accepted):
    today = utc_now().date()
    recent_cutoff = (today - timedelta(days=90)).isoformat()
    review_counts = Counter(str(item.get("bandId")) for item in review)
    failure_counts = Counter(str(item.get("bandId")) for item in failures)
    rows = []
    for community in registry.get("communities", []):
        band_articles = [
            item
            for item in articles
            if str(item.get("bandId")) == str(community.get("bandId"))
        ]
        sources = community.get("sources") or []
        newest = max(
            (item.get("publishedAt") for item in band_articles if item.get("publishedAt")),
            default=None,
        )
        rows.append(
            {
                "bandId": community["bandId"],
                "communityName": community["communityName"],
                "resultCount": len(band_articles),
                "resultsLast90Days": sum(
                    1
                    for item in band_articles
                    if str(item.get("publishedAt") or "") >= recent_cutoff
                ),
                "newestResult": newest,
                "knownSourceCount": sum(
                    1 for source in sources if source.get("type") != "Government Source"
                ),
                "missingOfficialWebsite": not any(
                    source.get("type") == "Official First Nation Website"
                    and source.get("status") == "verified"
                    for source in sources
                ),
                "missingOfficialFacebook": not any(
                    source.get("type") == "Facebook"
                    and source.get("status") == "verified"
                    for source in sources
                ),
                "manualReviewCount": review_counts[str(community["bandId"])],
                "failedSourceCount": failure_counts[str(community["bandId"])],
            }
        )
    return {
        "schemaVersion": 1,
        "generated": iso_now(),
        "articlesBefore": before_count,
        "articlesAfter": len(articles),
        "newAccepted": len(accepted),
        "manualReviewCount": len(review),
        "sourceFailureCount": len(failures),
        "communitiesTracked": len(rows),
        "communitiesWithResults": sum(1 for row in rows if row["resultCount"]),
        "communitiesWithRecentResults": sum(
            1 for row in rows if row["resultsLast90Days"]
        ),
        "communitiesWithoutRecentResults": [
            row["communityName"] for row in rows if not row["resultsLast90Days"]
        ],
        "facebook": {
            "authorizedApiConfigured": bool(os.getenv("META_ACCESS_TOKEN")),
            "limitation": (
                "Public Facebook pages are mapped, but posts are fetched only through "
                "an authorized Meta API token. OpenBand never bypasses login walls, "
                "CAPTCHAs, privacy controls, or platform restrictions."
            ),
        },
        "communities": rows,
        "sourceFailures": failures,
    }


def ensure_registry(data, news, registry):
    existing_sources = {
        str(item.get("bandId")): item for item in news.get("communitySources", [])
    }
    registry_rows = {
        str(item.get("bandId")): item
        for item in registry.get("communities", [])
        if item.get("bandId") is not None
    }
    rows = []
    for band in data.get("bands", []):
        band_id = str(band["id"])
        current = registry_rows.get(band_id, {})
        old = existing_sources.get(band_id, {})
        sources = list(current.get("sources") or [])
        known_urls = {canonical_url(source.get("url")) for source in sources}
        for source in old.get("sources") or []:
            url = canonical_url(source.get("url"))
            if not url or url in known_urls:
                continue
            copied = dict(source)
            copied.setdefault(
                "adapter",
                "html"
                if copied.get("type") == "Official First Nation Website"
                else "static",
            )
            copied.setdefault(
                "monitor", copied.get("type") == "Official First Nation Website"
            )
            copied.setdefault(
                "official", copied.get("type") == "Official First Nation Website"
            )
            sources.append(copied)
            known_urls.add(url)
        isc_url = (
            "https://fnp-ppn.aadnc-aandc.gc.ca/fnp/Main/Search/"
            f"FederalFundingMain.aspx?BAND_NUMBER={band['id']}&lang=eng"
        )
        if canonical_url(isc_url) not in known_urls:
            sources.append(
                {
                    "type": "Government Source",
                    "name": "Indigenous Services Canada FNFTA filings",
                    "url": isc_url,
                    "status": "baseline",
                    "adapter": "static",
                    "monitor": False,
                    "official": True,
                }
            )
        rows.append(
            {
                "bandId": band["id"],
                "communityName": band["name"],
                "aliases": current.get("aliases") or [],
                "provinceTerritory": "SK",
                "treaty": band.get("treaty"),
                "sources": sources,
                "discoveryQueries": current.get("discoveryQueries")
                or build_discovery_queries(band["name"], current.get("aliases") or []),
            }
        )
    return {
        "schemaVersion": 1,
        "generated": registry.get("generated") or iso_now(),
        "notes": (
            "Manually maintain verified community websites, public Facebook pages, "
            "and local organizations here. The discovery job preserves these records."
        ),
        "communities": rows,
    }


def build_discovery_queries(name, aliases):
    names = [name] + list(aliases or [])
    queries = []
    for value in names:
        queries.extend(
            [
                f'"{value}" announcement Saskatchewan',
                f'"{value}" community update',
                f'site:facebook.com "{value}" announcement',
                f'"{value}" funding OR housing OR infrastructure',
            ]
        )
    return list(dict.fromkeys(queries))


def registry_for_frontend(registry):
    rows = []
    for community in registry.get("communities", []):
        public_sources = []
        for source in community.get("sources") or []:
            public_sources.append(
                {
                    key: source.get(key)
                    for key in ("type", "name", "url", "status")
                    if source.get(key) is not None
                }
            )
        non_baseline = [
            source
            for source in public_sources
            if source.get("type") != "Government Source"
        ]
        rows.append(
            {
                "bandId": community["bandId"],
                "communityName": community["communityName"],
                "provinceTerritory": "SK",
                "treaty": community.get("treaty"),
                "monitoringStatus": (
                    "official-source-found" if non_baseline else "source-research-needed"
                ),
                "sources": public_sources,
            }
        )
    return rows


def discovery_urls(source):
    return list(
        dict.fromkeys(
            [source.get("url")] + list(source.get("discoveryUrls") or [])
        )
    )


def run(args):
    data = load_json(DATA_PATH, {"bands": []})
    news = load_json(NEWS_PATH, {"schemaVersion": 1, "articles": []})
    registry = ensure_registry(
        data,
        news,
        load_json(REGISTRY_PATH, {"schemaVersion": 1, "communities": []}),
    )
    cache = load_json(CACHE_PATH, {"schemaVersion": 1, "seenUrls": {}})
    fetcher = Fetcher(delay=args.delay, timeout=args.timeout)
    failures = []
    review = []
    candidates = []
    access_token = os.getenv("META_ACCESS_TOKEN")
    today = utc_now().date()
    cutoff = (today - timedelta(days=args.lookback_days)).isoformat()

    communities = registry.get("communities", [])
    if args.pilot:
        communities = [
            community
            for community in communities
            if int(community["bandId"]) in PILOT_BAND_IDS
        ]
    if args.band_id:
        requested = {str(value) for value in args.band_id}
        communities = [
            community
            for community in communities
            if str(community["bandId"]) in requested
        ]

    for community in communities:
        for source in community.get("sources") or []:
            if not source_is_monitorable(source):
                continue
            adapter = source.get("adapter")
            try:
                if adapter == "facebook":
                    candidates.extend(
                        discover_meta_posts(fetcher, community, source, access_token)
                    )
                    continue
                for url in discovery_urls(source):
                    if not url:
                        continue
                    body, final_url, content_type = fetcher.get(url)
                    if adapter == "rss" or "xml" in content_type:
                        found = extract_feed_candidates(
                            body, final_url, community, source
                        )
                    elif "html" in content_type:
                        found = extract_html_candidates(
                            body.decode("utf-8", errors="replace"),
                            final_url,
                            community,
                            source,
                        )
                    else:
                        found = []
                    candidates.extend(found)
            except Exception as error:
                failures.append(
                    {
                        "bandId": community["bandId"],
                        "communityName": community["communityName"],
                        "sourceName": source.get("name"),
                        "sourceType": source.get("type"),
                        "url": source.get("url"),
                        "reason": f"{type(error).__name__}: {error}",
                    }
                )

    if not args.skip_search:
        search_communities, next_cursor = communities_for_targeted_search(
            communities,
            news.get("articles") or [],
            limit=args.max_search_communities,
            pilot=args.pilot,
            cursor=int(cache.get("searchCursor") or 0),
        )
        for community in search_communities:
            try:
                candidates.extend(discover_gdelt_articles(fetcher, community))
            except Exception as error:
                failures.append(
                    {
                        "bandId": community["bandId"],
                        "communityName": community["communityName"],
                        "sourceName": "GDELT public news index",
                        "sourceType": "Discovery Search",
                        "url": "https://api.gdeltproject.org/",
                        "reason": f"{type(error).__name__}: {error}",
                    }
                )
        cache["searchCursor"] = next_cursor

    acceptable = []
    existing_urls = {
        canonical_url(item.get("url")) for item in news.get("articles") or []
    }
    cached_urls = set(cache.get("seenUrls") or {})
    for item in candidates:
        if item.get("publishedAt", "") < cutoff:
            continue
        item_url = canonical_url(item.get("url"))
        if item_url in cached_urls and item_url in existing_urls:
            continue
        if item.get("communityConfidence", 0) < args.confidence_threshold:
            item["reviewReason"] = "Community association confidence below threshold"
            review.append(item)
            continue
        acceptable.append(item)

    before = list(news.get("articles") or [])
    merged, accepted = merge_articles(before, acceptable)
    for item in merged:
        url = canonical_url(item.get("url"))
        if url:
            cache.setdefault("seenUrls", {})[url] = item.get("discoveredAt") or iso_now()
    cache["schemaVersion"] = 1
    cache["updated"] = iso_now()

    news.update(
        {
            "schemaVersion": 1,
            "generated": iso_now(),
            "scope": "Saskatchewan First Nations community updates",
            "sourceTypes": SOURCE_TYPES,
            "articles": merged,
            "communitySources": registry_for_frontend(registry),
        }
    )
    report = build_coverage_report(
        registry, merged, review, failures, len(before), accepted
    )
    review_output = {
        "schemaVersion": 1,
        "generated": iso_now(),
        "items": review,
    }
    if not args.dry_run:
        write_json(REGISTRY_PATH, registry)
        write_json(NEWS_PATH, news)
        write_json(CACHE_PATH, cache)
        write_json(REVIEW_PATH, review_output)
        write_json(REPORT_PATH, report)
    print(
        f"communities={len(communities)} candidates={len(candidates)} "
        f"accepted={len(accepted)} review={len(review)} failures={len(failures)} "
        f"articles={len(before)}->{len(merged)}"
    )
    return report


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--band-id", action="append")
    parser.add_argument("--lookback-days", type=int, default=550)
    parser.add_argument("--confidence-threshold", type=float, default=0.82)
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--max-search-communities", type=int, default=15)
    parser.add_argument("--skip-search", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
