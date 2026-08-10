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
PROJECTS_PATH = ROOT / "projects-data.json"

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
PROJECT_ACTION_PATTERNS = re.compile(
    r"\b(announce|announced|approval|approved|award|awarded|build|building|built|"
    r"complete|completed|completion|construct|construction|develop|development|"
    r"expand|expansion|fund|funded|funding|groundbreak|open|opened|opening|plan|"
    r"planned|proposal|proposed|repair|renovate|renovation|replace|replacement|"
    r"retrofit|tender|upgrade|upgrades|work underway)\b",
    re.I,
)
PROJECT_CATEGORY_RULES = [
    ("Housing", r"\b(housing|homes?|residential|subdivision|apartment|duplex|units?)\b"),
    ("Water & Wastewater", r"\b(water|wastewater|sewer|sewage|lagoon|pumphouse|pump station)\b"),
    ("Roads & Bridges", r"\b(road|roads|bridge|bridges|culvert|drainage|pathway|trail)\b"),
    ("Education Facility", r"\b(school|daycare|head start|education facility|classroom)\b"),
    ("Health Centre", r"\b(health centre|health center|clinic|hospital|wellness centre|wellness center)\b"),
    ("Emergency Infrastructure", r"\b(fire hall|firehall|emergency operations|safe home|safe house)\b"),
    ("Broadband Infrastructure", r"\b(broadband|high.speed internet|fibre|fiber optic|cell tower|network tower)\b"),
    ("Renewable Energy", r"\b(solar|wind farm|renewable energy|battery storage|microgrid)\b"),
    ("Community Building", r"\b(community (?:centre|center|building|hall)|band office|recreation centre|arena)\b"),
    ("Waste Infrastructure", r"\b(landfill|solid waste|transfer station|recycling facility)\b"),
]
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


def classify_project_signal(value):
    """Return a conservative infrastructure-project classification or None."""
    text = clean_text(value)
    normalized = normalized_text(text)
    categories = [
        category
        for category, pattern in PROJECT_CATEGORY_RULES
        if re.search(pattern, normalized, re.I)
    ]
    if not categories or not PROJECT_ACTION_PATTERNS.search(normalized):
        return None

    explicit_project = bool(
        re.search(
            r"\b(project|construction|development|infrastructure|capital project|"
            r"new (?:homes?|school|facility|building|centre|center)|"
            r"housing (?:build|program|repair|renovation))\b",
            normalized,
            re.I,
        )
    )
    confidence = 0.9 if explicit_project else 0.78
    if re.search(r"\b(apply|application|waitlist|maintenance request|service interruption)\b", normalized):
        confidence -= 0.18

    location_scope = "Unspecified"
    if re.search(r"\burban reserve\b", normalized):
        location_scope = "Urban Reserve"
    elif re.search(r"\boff.reserve|off reserve\b", normalized):
        location_scope = "Off Reserve"
    elif re.search(r"\bon.reserve|on reserve\b", normalized):
        location_scope = "On Reserve"
    elif re.search(r"\bregional|multiple communities|member nations\b", normalized):
        location_scope = "Regional"

    return {
        "category": categories[0],
        "additionalCategories": categories[1:],
        "confidence": round(max(0.0, min(confidence, 1.0)), 2),
        "locationScope": location_scope,
    }


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


def load_meta_page_tokens(value=None):
    """Load per-Page tokens from a secret JSON object without exposing them."""
    raw = value if value is not None else os.getenv("META_PAGE_TOKENS_JSON", "")
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("META_PAGE_TOKENS_JSON must be a JSON object") from error
    if not isinstance(payload, dict):
        raise ValueError("META_PAGE_TOKENS_JSON must be a JSON object")
    return {
        str(key): str(token)
        for key, token in payload.items()
        if clean_text(key) and clean_text(token)
    }


def meta_token_for_source(source, default_token, page_tokens=None):
    page_tokens = page_tokens or {}
    identifiers = [source.get("metaPageId"), source.get("pageHandle")]
    for identifier in identifiers:
        if identifier is not None and str(identifier) in page_tokens:
            return page_tokens[str(identifier)]
    return default_token


def meta_source_kind(source):
    return normalized_text(source.get("entityKind") or "page")


def discover_meta_posts(
    fetcher,
    community,
    source,
    access_token,
    *,
    since_date=None,
    max_pages=8,
):
    page_id = source.get("metaPageId") or source.get("pageHandle")
    if meta_source_kind(source) != "page" or not access_token or not page_id:
        return []
    version = os.getenv("META_API_VERSION", "v23.0")
    fields = "message,story,created_time,permalink_url,full_picture"
    parameters = {"fields": fields, "limit": "100"}
    if since_date:
        parameters["since"] = f"{since_date}T00:00:00Z"
    query = urllib.parse.urlencode(parameters)
    url = f"https://graph.facebook.com/{version}/{page_id}/posts?{query}"
    candidates = []
    seen_urls = set()
    for _ in range(max(1, max_pages)):
        body, _, _ = fetcher.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            respect_robots=False,
        )
        payload = json.loads(body.decode("utf-8"))
        if payload.get("error"):
            error = payload["error"]
            raise PermissionError(
                f"Meta API error {error.get('code', 'unknown')}: "
                f"{clean_text(error.get('message'))}"
            )
        for post in payload.get("data", []):
            message = clean_text(post.get("message") or post.get("story"))
            permalink = canonical_url(post.get("permalink_url"))
            if (
                len(message) < 15
                or not permalink
                or permalink in seen_urls
                or not is_supported_update(message)
            ):
                continue
            published, _ = parse_date_text(post.get("created_time"))
            if not published or (since_date and published < since_date):
                continue
            first_sentence = re.split(r"(?<=[.!?])\s+", message, maxsplit=1)[0]
            label = first_sentence[:110].rstrip(" ,.;:-")
            item = normalized_candidate(
                community,
                source,
                title=f"{label} (community post)",
                summary=message[:420],
                url=permalink,
                published=published,
                thumbnail=post.get("full_picture"),
            )
            item["tags"].append("authorized-facebook-page")
            item["facebookSource"] = {
                "entityKind": "Page",
                "official": bool(source.get("official")),
                "pageId": str(page_id),
            }
            project_signal = classify_project_signal(message)
            if project_signal:
                item["projectSignal"] = project_signal
                item["tags"].append("housing-infrastructure-project")
            candidates.append(item)
            seen_urls.add(permalink)

        next_url = clean_text((payload.get("paging") or {}).get("next"))
        if not next_url:
            break
        next_parts = urllib.parse.urlsplit(next_url)
        if next_parts.scheme != "https" or next_parts.netloc != "graph.facebook.com":
            raise ValueError("Meta paging URL was not on graph.facebook.com")
        next_query = [
            (key, value)
            for key, value in urllib.parse.parse_qsl(next_parts.query, keep_blank_values=True)
            if key.lower() != "access_token"
        ]
        url = urllib.parse.urlunsplit(
            (next_parts.scheme, next_parts.netloc, next_parts.path, urllib.parse.urlencode(next_query), "")
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


def discover_gdelt_batch(fetcher, communities):
    """Search GDELT once for several communities and retain strongly matched links."""
    community_query = " OR ".join(
        f'"{community["communityName"]}"' for community in communities
    )
    params = urllib.parse.urlencode(
        {
            "query": f"({community_query}) Saskatchewan",
            "mode": "ArtList",
            "maxrecords": "250",
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
        community = next(
            (
                candidate
                for candidate in communities
                if community_name_match(candidate, title)
            ),
            None,
        )
        if (
            not title
            or not original_url.startswith("https://")
            or community is None
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


def discover_gdelt_articles(fetcher, community):
    """Compatibility wrapper for a single-community discovery search."""
    return discover_gdelt_batch(fetcher, [community])


def chunks(values, size):
    for index in range(0, len(values), size):
        yield values[index : index + size]


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


def merge_facebook_project_signals(projects_payload, candidates):
    """Add strong official-Page project signals to the unverified project feed."""
    payload = dict(projects_payload or {})
    existing = [dict(item) for item in payload.get("unverifiedProjects") or []]
    known_urls = {
        canonical_url(source.get("url"))
        for item in existing
        for source in item.get("sources") or []
        if source.get("url")
    }
    added = []
    for item in candidates:
        signal = item.get("projectSignal") or {}
        facebook_source = item.get("facebookSource") or {}
        url = canonical_url(item.get("url"))
        if (
            item.get("sourceType") != "Facebook"
            or not facebook_source.get("official")
            or facebook_source.get("entityKind") != "Page"
            or float(signal.get("confidence") or 0) < 0.78
            or not url
            or url in known_urls
        ):
            continue
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        location_scope = signal.get("locationScope") or "Unspecified"
        record = {
            "id": f"facebook-project-signal-{digest}",
            "firstNationIds": [str(item.get("bandId"))],
            "category": signal.get("category") or "Community Infrastructure",
            "name": re.sub(r"\s*\(community post\)\s*$", "", item.get("title") or "Community project update"),
            "discussionSummary": clean_text(item.get("summary"))[:420],
            "signalType": "Authorized official First Nation Facebook Page post",
            "whyUnverified": (
                "The official community post is a credible project signal, but OpenBand "
                "has not yet corroborated all delivery details with a second public source."
            ),
            "locationScope": location_scope,
            "lastSeenAt": item.get("publishedAt"),
            "sources": [
                {
                    "name": item.get("sourceName") or item.get("communityName"),
                    "url": url,
                    "publishedAt": item.get("publishedAt"),
                }
            ],
        }
        existing.append(record)
        added.append(record)
        known_urls.add(url)
    payload["unverifiedProjects"] = existing
    if added:
        payload["generatedAt"] = utc_now().date().isoformat()
    return payload, added


def prune_invalid_generated_articles(articles, today):
    """Remove only machine-discovered rows with impossible future publication dates."""
    retained = []
    removed = []
    today_text = today.isoformat()
    for item in articles:
        if item.get("discoveredAt") and str(item.get("publishedAt") or "") > today_text:
            removed.append(
                {
                    "bandId": item.get("bandId"),
                    "communityName": item.get("communityName"),
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "reason": "Future event date was previously stored as publication date",
                }
            )
            continue
        retained.append(item)
    return retained, removed


def candidate_review_reason(item, today, confidence_threshold):
    if str(item.get("publishedAt") or "") > today.isoformat():
        return "Date appears to be a future event date, not a publication date"
    if not canonical_url(item.get("url")).startswith("https://"):
        return "Original source URL is not HTTPS"
    if item.get("communityConfidence", 0) < confidence_threshold:
        return "Community association confidence below threshold"
    return None


def build_coverage_report(
    registry,
    articles,
    review,
    failures,
    before_count,
    accepted,
    invalid_existing_removed,
    facebook_activity=None,
    project_signals_added=None,
):
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
    facebook_activity = dict(facebook_activity or {})
    facebook_activity.setdefault("limitation", (
        "Only authorized public Pages are fetched through Meta's ordinary API. "
        "Groups, private content, login walls and access-restricted content are not fetched."
    ))
    return {
        "schemaVersion": 1,
        "generated": iso_now(),
        "articlesBefore": before_count,
        "articlesAfter": len(articles),
        "newAccepted": len(accepted),
        "invalidExistingRemoved": invalid_existing_removed,
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
            **facebook_activity,
        },
        "facebookProjectSignalsAdded": len(project_signals_added or []),
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
                "facebookMonitoring": {
                    "pageStatus": (
                        "registered"
                        if any(
                            source.get("type") == "Facebook"
                            and meta_source_kind(source) == "page"
                            for source in sources
                        )
                        else "source-research-needed"
                    ),
                    "groupStatus": "registry-only-no-ordinary-api-fetch",
                    "policy": (
                        "Authorized public Pages may be fetched through Meta's API; "
                        "Groups and access-restricted content are never scraped."
                    ),
                },
                "discoveryQueries": list(
                    dict.fromkeys(
                        list(current.get("discoveryQueries") or [])
                        + build_discovery_queries(
                            band["name"], current.get("aliases") or []
                        )
                    )
                ),
            }
        )
    return {
        "schemaVersion": 1,
        "generated": registry.get("generated") or iso_now(),
        "notes": (
            "Maintain verified community websites, authorized public Facebook Pages, "
            "and local organizations here. Facebook Groups may be catalogued for "
            "transparency but are never fetched by the ordinary API scanner. The "
            "discovery job preserves these records."
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
                f'site:facebook.com "{value}" housing infrastructure project',
                f'site:facebook.com/groups "{value}" housing infrastructure project',
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
    page_tokens = load_meta_page_tokens()
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

    facebook_sources = [
        source
        for community in communities
        for source in community.get("sources") or []
        if source.get("adapter") == "facebook" or source.get("type") == "Facebook"
    ]
    facebook_activity = {
        "authorizedApiConfigured": bool(access_token or page_tokens),
        "registeredPageSourceCount": sum(
            1 for source in facebook_sources if meta_source_kind(source) == "page"
        ),
        "registeredGroupSourceCount": sum(
            1 for source in facebook_sources if meta_source_kind(source) == "group"
        ),
        "pagesScanned": 0,
        "matchedPosts": 0,
        "pagesAwaitingAuthorization": 0,
        "groupsSkippedByPolicy": sum(
            1 for source in facebook_sources if meta_source_kind(source) == "group"
        ),
        "limitation": (
            "Only registered, authorized public Pages are fetched through Meta's ordinary "
            "API. Public and private Groups are skipped because the ordinary API does not "
            "provide compliant general-purpose group scanning."
        ),
    }

    for community in communities:
        for source in community.get("sources") or []:
            if not source_is_monitorable(source):
                continue
            adapter = source.get("adapter")
            try:
                if adapter == "facebook":
                    if meta_source_kind(source) != "page":
                        continue
                    source_token = meta_token_for_source(
                        source, access_token, page_tokens
                    )
                    if not source_token:
                        facebook_activity["pagesAwaitingAuthorization"] += 1
                        continue
                    found = discover_meta_posts(
                        fetcher,
                        community,
                        source,
                        source_token,
                        since_date=cutoff,
                        max_pages=args.max_meta_pages,
                    )
                    facebook_activity["pagesScanned"] += 1
                    facebook_activity["matchedPosts"] += len(found)
                    candidates.extend(found)
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
        for index, community_batch in enumerate(chunks(search_communities, 5)):
            if index and args.search_delay > 0:
                time.sleep(args.search_delay)
            try:
                candidates.extend(discover_gdelt_batch(fetcher, community_batch))
            except Exception as error:
                for community in community_batch:
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
        review_reason = candidate_review_reason(
            item, today, args.confidence_threshold
        )
        if review_reason:
            item["reviewReason"] = review_reason
            review.append(item)
            continue
        acceptable.append(item)

    original_before = list(news.get("articles") or [])
    before, invalid_existing_removed = prune_invalid_generated_articles(
        original_before, today
    )
    merged, accepted = merge_articles(before, acceptable)
    projects_payload, project_signals_added = merge_facebook_project_signals(
        load_json(PROJECTS_PATH, {"schemaVersion": 1, "unverifiedProjects": []}),
        acceptable,
    )
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
        registry,
        merged,
        review,
        failures,
        len(original_before),
        accepted,
        invalid_existing_removed,
        facebook_activity,
        project_signals_added,
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
        if project_signals_added:
            write_json(PROJECTS_PATH, projects_payload)
    print(
        f"communities={len(communities)} candidates={len(candidates)} "
        f"accepted={len(accepted)} review={len(review)} failures={len(failures)} "
        f"articles={len(original_before)}->{len(merged)} "
        f"invalid_removed={len(invalid_existing_removed)}"
        f" facebook_pages={facebook_activity['pagesScanned']}"
        f" project_signals={len(project_signals_added)}"
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
    parser.add_argument("--search-delay", type=float, default=6.0)
    parser.add_argument("--max-meta-pages", type=int, default=8)
    parser.add_argument("--skip-search", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
