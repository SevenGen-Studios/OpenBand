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
import shutil
import subprocess
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
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
CONTACTS_PATH = ROOT / "contacts-data.json"

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
    "register",
    "view larger",
    "view all news",
    "view all posts",
    "view all events",
    "news and updates",
    "sign up today",
    "education",
    "health",
    "housing",
    "news and events",
    "upcoming events",
    "next posts",
}
GENERIC_PAGE_PATTERNS = re.compile(
    r"\b(web design|webflow cloneable|cookie policy|privacy policy|terms of use|"
    r"member portal|view all|listen live|subscription messaging|cdn-cgi|"
    r"leadership|departments|contact us|about us)\b",
    re.I,
)
EMPLOYMENT_PATTERNS = re.compile(
    r"\b(employment opportunity|job posting|job opportunity|careers?|is hiring|"
    r"positions? available|apply for (?:the )?position|open until filled|"
    r"part[- ]time contract\s*\(?(?:apply|deadline)|\*\s*closed\s*\*)\b",
    re.I,
)
UPDATE_PAGE_PATTERNS = re.compile(
    r"\b(news|updates?|announcements?|notices?|media|press|events?|newsletter|"
    r"community calendar|bulletin)\b",
    re.I,
)
MEDIA_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
NON_NEWS_MEDIA = re.compile(
    r"\b(logo|icon|favicon|banner|header|footer|avatar|sponsor|seal|crest)\b",
    re.I,
)
EXCLUDED_PATTERNS = re.compile(
    r"\b(happy birthday|birthday wishes|good morning|good night|meme|"
    r"like and share|tag (?:a|your) friend|contest|giveaway|winner|"
    r"generic greeting|daily quote)\b",
    re.I,
)
SUPPORTED_PATTERNS = re.compile(
    r"\b(announcement|notice|update|funding|grant|construction|infrastructure|"
    r"housing|meeting|annual general meeting|agm|election|governance|council|"
    r"training|business|economic|health|safety|school|"
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
    date_source=None,
    extraction_method="html",
    source_page=None,
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
        "dateSource": date_source or "source-metadata",
        "extractionMethod": extraction_method,
    }
    if source_page:
        item["sourcePage"] = canonical_url(source_page)
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
        self.images = []

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
        elif tag == "img" and (attrs.get("src") or attrs.get("data-src")):
            image = {
                "src": attrs.get("src") or attrs.get("data-src"),
                "alt": clean_text(attrs.get("alt")),
            }
            self.images.append(image)
            if self.blocks:
                self.blocks[-1]["image"] = image["src"]
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
            structured = context is not None
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
                    "structured": structured,
                }
            )
        return rows


class ArticleMetadataParser(HTMLParser):
    """Extract article identity and explicit publication metadata from a detail page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.times = []
        self.title_parts = []
        self.h1_parts = []
        self.body_parts = []
        self.json_ld_parts = []
        self._capture = None
        self.canonical = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            if key and attrs.get("content"):
                self.meta[key] = attrs["content"]
        elif tag == "link" and "canonical" in str(attrs.get("rel", "")).lower():
            self.canonical = attrs.get("href", "")
        elif tag == "time" and attrs.get("datetime"):
            self.times.append(attrs["datetime"])
        elif tag in {"title", "h1", "p"}:
            self._capture = tag
        elif tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self._capture = "jsonld"

    def handle_data(self, data):
        value = clean_text(data)
        if not value:
            return
        if self._capture == "title":
            self.title_parts.append(value)
        elif self._capture == "h1":
            self.h1_parts.append(value)
        elif self._capture == "p":
            self.body_parts.append(value)
        elif self._capture == "jsonld":
            self.json_ld_parts.append(data)

    def handle_endtag(self, tag):
        if self._capture == tag or (tag == "script" and self._capture == "jsonld"):
            self._capture = None

    def json_ld_records(self):
        records = []
        for raw in self.json_ld_parts:
            try:
                value = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            values = value if isinstance(value, list) else [value]
            for item in values:
                if not isinstance(item, dict):
                    continue
                graph = item.get("@graph")
                if isinstance(graph, list):
                    records.extend(row for row in graph if isinstance(row, dict))
                records.append(item)
        return records


def article_page_metadata(markup, page_url):
    parser = ArticleMetadataParser()
    parser.feed(markup)
    records = parser.json_ld_records()
    title = clean_text(
        parser.meta.get("og:title")
        or next((row.get("headline") for row in records if row.get("headline")), "")
        or " ".join(parser.h1_parts)
        or " ".join(parser.title_parts)
    )
    summary = clean_text(
        parser.meta.get("og:description")
        or parser.meta.get("description")
        or next((row.get("description") for row in records if row.get("description")), "")
        or " ".join(parser.body_parts[:3])
    )
    date_sources = [
        (parser.meta.get("article:published_time"), "article:published_time"),
        (parser.meta.get("date"), "meta:date"),
    ]
    date_sources.extend(
        (row.get("datePublished"), "json-ld:datePublished")
        for row in records
        if row.get("datePublished")
    )
    date_sources.extend((value, "time:datetime") for value in parser.times)
    for raw_date, source in date_sources:
        published, precision = parse_date_text(raw_date)
        if published:
            return {
                "title": title,
                "summary": summary,
                "published": published,
                "datePrecision": precision,
                "dateSource": source,
                "canonical": canonical_url(urllib.parse.urljoin(page_url, parser.canonical or page_url)),
                "thumbnail": parser.meta.get("og:image"),
            }
    visible = clean_text(" ".join(parser.body_parts[:6]))
    labeled = re.search(
        r"\b(?:published|posted|issued|release date)\s*(?:on)?\s*[:\-]?\s*"
        r"([^|]{0,50}20\d{2})",
        visible,
        re.I,
    )
    if labeled:
        published, precision = parse_date_text(labeled.group(1))
        if published:
            return {
                "title": title,
                "summary": summary,
                "published": published,
                "datePrecision": precision,
                "dateSource": "visible-published-label",
                "canonical": canonical_url(urllib.parse.urljoin(page_url, parser.canonical or page_url)),
                "thumbnail": parser.meta.get("og:image"),
            }
    return {
        "title": title,
        "summary": summary,
        "published": None,
        "datePrecision": None,
        "dateSource": None,
        "canonical": canonical_url(urllib.parse.urljoin(page_url, parser.canonical or page_url)),
        "thumbnail": parser.meta.get("og:image"),
    }


def run_text_command(command, timeout=45):
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
        return result.stdout if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def extract_document_text(fetcher, url):
    """Use embedded PDF text first, then free local OCR for scanned documents."""
    body, final_url, content_type = fetcher.get(url)
    if len(body) > 15 * 1024 * 1024:
        return "", "document_too_large", final_url
    suffix = Path(urllib.parse.urlsplit(final_url).path).suffix.lower()
    with tempfile.TemporaryDirectory() as directory:
        if content_type == "application/pdf" or suffix == ".pdf":
            path = Path(directory) / "notice.pdf"
            path.write_bytes(body)
            if shutil.which("pdftotext"):
                text = run_text_command(["pdftotext", "-layout", str(path), "-"])
                if len(clean_text(text)) >= 80:
                    return text, "pdf_text", final_url
            if not shutil.which("pdftoppm") or not shutil.which("tesseract"):
                return "", "ocr_unavailable", final_url
            prefix = Path(directory) / "page"
            run_text_command(
                ["pdftoppm", "-f", "1", "-l", "2", "-jpeg", "-r", "180", str(path), str(prefix)],
                timeout=45,
            )
            pages = [
                run_text_command(["tesseract", str(image), "stdout", "--psm", "6"], timeout=30)
                for image in sorted(Path(directory).glob("page-*.jpg"))
            ]
            return "\n".join(pages), "pdf_ocr", final_url
        if content_type.startswith("image/") or suffix in MEDIA_SUFFIXES:
            if not shutil.which("tesseract"):
                return "", "ocr_unavailable", final_url
            path = Path(directory) / f"notice{suffix if suffix in MEDIA_SUFFIXES else '.img'}"
            path.write_bytes(body)
            return (
                run_text_command(["tesseract", str(path), "stdout", "--psm", "6"], timeout=30),
                "image_ocr",
                final_url,
            )
    return "", "unsupported_media", final_url


def document_title(text):
    candidates = []
    for raw in str(text or "").splitlines()[:80]:
        line = clean_text(raw).strip("-|:•")
        if not 10 <= len(line) <= 150:
            continue
        if GENERIC_PAGE_PATTERNS.search(line) or EMPLOYMENT_PATTERNS.search(line):
            continue
        if is_supported_update(line):
            candidates.append((1 if len(line) < 100 else 0, -len(line), line))
    return sorted(candidates, reverse=True)[0][2] if candidates else ""


def document_publication_date(text):
    labeled = re.search(
        r"\b(?:published|posted|issued|news release|release date)\s*(?:on)?\s*[:\-]?\s*"
        r"([^\n|]{0,60}20\d{2})",
        str(text or ""),
        re.I,
    )
    if labeled:
        published, precision = parse_date_text(labeled.group(1))
        if published:
            return published, precision, "document-published-label"
    heading = clean_text(" ".join(str(text or "").splitlines()[:12]))
    if re.search(r"\bnewsletter\b", heading, re.I):
        published, precision = parse_date_text(heading)
        if published:
            return published, precision, "newsletter-heading"
    return None, None, None


def is_supported_update(title, context=""):
    text = clean_text(f"{title} {context}")
    if (
        EXCLUDED_PATTERNS.search(text)
        or GENERIC_PAGE_PATTERNS.search(title)
        or EMPLOYMENT_PATTERNS.search(text)
    ):
        return False
    return bool(SUPPORTED_PATTERNS.search(text))


def generic_news_title(title):
    text = clean_text(title)
    normalized = normalized_text(text)
    if len(text) < 8 or normalized in GENERIC_LINK_TEXT:
        return True
    return bool(
        re.match(
            r"^(?:(?:news and events|upcoming events|events calendar)(?:\s+.*)?|"
            r"next posts?|.* official website)$",
            normalized,
            re.I,
        )
    )


def non_article_url(url):
    parts = urllib.parse.urlsplit(canonical_url(url))
    path = parts.path.rstrip("/") or "/"
    return path == "/" or bool(
        re.search(r"/(?:category|tag|author|page)/|/events/category/", path, re.I)
    )


def employment_item(title, url=""):
    path = urllib.parse.urlsplit(str(url or "")).path
    return bool(
        EMPLOYMENT_PATTERNS.search(title or "")
        or re.search(r"/(?:jobs?|careers?|employment)(?:[-/]|$)", path, re.I)
    )


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
                date_source=(
                    "structured-listing"
                    if anchor.get("structured")
                    else "unstructured-listing"
                ),
                source_page=page_url,
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


def prune_invalid_generated_articles(articles, today):
    """Remove machine rows that cannot meet the current publication safeguards."""
    retained = []
    removed = []
    today_text = today.isoformat()
    for item in articles:
        reason = None
        if item.get("discoveredAt") and str(item.get("publishedAt") or "") > today_text:
            reason = "Future event date was previously stored as publication date"
        elif item.get("discoveredAt") and employment_item(
            item.get("title"), item.get("url")
        ):
            reason = "Employment posting belongs in Jobs & Employment, not News"
        elif item.get("discoveredAt") and (
            GENERIC_PAGE_PATTERNS.search(item.get("title") or "")
            or generic_news_title(item.get("title"))
        ):
            reason = "Generic navigation or evergreen page was previously stored as news"
        elif (
            item.get("discoveredAt")
            and item.get("sourceType") in OFFICIAL_SOURCE_TYPES
            and item.get("url")
            and non_article_url(item.get("url"))
        ):
            reason = "Homepage or archive URL was previously stored as an article"
        elif item.get("discoveredAt") and "scontent-" in str(item.get("url") or ""):
            reason = "Temporary Facebook image URL was stored instead of an original post"
        elif (
            item.get("discoveredAt")
            and item.get("sourceType") in OFFICIAL_SOURCE_TYPES
            and not item.get("dateSource")
        ):
            reason = "Legacy machine-discovered item lacks verifiable publication-date provenance"
        if reason:
            removed.append(
                {
                    "bandId": item.get("bandId"),
                    "communityName": item.get("communityName"),
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "reason": reason,
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
    if not clean_text(item.get("title")) or not is_supported_update(
        item.get("title"), item.get("summary")
    ):
        return "Title does not clearly describe a supported community update"
    if employment_item(item.get("title"), item.get("url")):
        return "Employment posting belongs in Jobs & Employment"
    if generic_news_title(item.get("title")):
        return "Title identifies navigation, a directory, or an evergreen section"
    if (
        item.get("sourceType") in OFFICIAL_SOURCE_TYPES
        and non_article_url(item.get("url"))
    ):
        return "Source URL is a homepage or archive rather than a dated article"
    if item.get("dateSource") in {"unstructured-listing", "structured-listing"} and not item.get("detailVerified"):
        return "Publication date could not be verified on the detail page"
    if "scontent-" in str(item.get("url") or ""):
        return "Temporary Facebook image URL is not an original durable source"
    return None


def build_coverage_report(
    registry,
    articles,
    review,
    failures,
    before_count,
    accepted,
    invalid_existing_removed,
    source_runs=None,
):
    today = utc_now().date()
    recent_cutoff = (today - timedelta(days=90)).isoformat()
    action_review = [item for item in review if item.get("status") != "extracted"]
    review_counts = Counter(str(item.get("bandId")) for item in action_review)
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
        "invalidExistingRemoved": invalid_existing_removed,
        "manualReviewCount": len(action_review),
        "mediaDocumentsChecked": sum(
            1 for item in review if item.get("extractionMethod")
        ),
        "mediaDocumentsExtracted": sum(
            1 for item in review if item.get("status") == "extracted"
        ),
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
        "sourceRuns": source_runs or [],
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
    contacts = {
        str(item.get("nation_id")): item
        for item in load_json(CONTACTS_PATH, {"contacts": []}).get("contacts", [])
        if item.get("nation_id") is not None
    }
    rows = []
    for band in data.get("bands", []):
        band_id = str(band["id"])
        current = registry_rows.get(band_id, {})
        old = existing_sources.get(band_id, {})
        sources = list(current.get("sources") or [])
        known_urls = {canonical_url(source.get("url")) for source in sources}
        contact = contacts.get(band_id, {})
        contact_url = canonical_url(contact.get("website_url"))
        if contact_url.startswith("http://"):
            contact_url = "https://" + contact_url.removeprefix("http://")
        if contact_url.startswith("https://") and contact_url not in known_urls:
            sources.append(
                {
                    "type": "Official First Nation Website",
                    "name": f"{band['name']} official website",
                    "url": contact_url,
                    "status": "verified",
                    "adapter": "html",
                    "monitor": True,
                    "official": True,
                    "sourceOrigin": "ISC First Nation profile",
                }
            )
            known_urls.add(contact_url)
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


def same_host(left, right):
    return (
        urllib.parse.urlsplit(left).netloc.lower().removeprefix("www.")
        == urllib.parse.urlsplit(right).netloc.lower().removeprefix("www.")
    )


def discovered_update_pages(markup, page_url):
    parser = CommunityHTMLParser()
    parser.feed(markup)
    pages = []
    for anchor in parser.results():
        url = canonical_url(urllib.parse.urljoin(page_url, anchor.get("href")))
        hint = clean_text(f"{anchor.get('title')} {urllib.parse.urlsplit(url).path}")
        suffix = Path(urllib.parse.urlsplit(url).path).suffix.lower()
        if (
            url.startswith("https://")
            and same_host(page_url, url)
            and suffix not in MEDIA_SUFFIXES
            and UPDATE_PAGE_PATTERNS.search(hint)
            and url.rstrip("/") != page_url.rstrip("/")
            and url not in pages
        ):
            pages.append(url)
    return pages[:4]


def discovered_media(markup, page_url):
    parser = CommunityHTMLParser()
    parser.feed(markup)
    rows = []
    for anchor in parser.results():
        url = canonical_url(urllib.parse.urljoin(page_url, anchor.get("href")))
        suffix = Path(urllib.parse.urlsplit(url).path).suffix.lower()
        hint = clean_text(f"{anchor.get('title')} {anchor.get('context')} {url}")
        if suffix not in MEDIA_SUFFIXES or NON_NEWS_MEDIA.search(hint):
            continue
        published, precision = parse_date_text(anchor.get("context"))
        rows.append(
            {
                "url": url,
                "label": clean_text(anchor.get("title")),
                "context": clean_text(anchor.get("context")),
                "published": published,
                "datePrecision": precision,
                "sourcePage": page_url,
            }
        )
    for image in parser.images:
        url = canonical_url(urllib.parse.urljoin(page_url, image.get("src")))
        hint = clean_text(f"{image.get('alt')} {url}")
        if (
            Path(urllib.parse.urlsplit(url).path).suffix.lower() in MEDIA_SUFFIXES
            and not NON_NEWS_MEDIA.search(hint)
            and is_supported_update(hint)
        ):
            rows.append(
                {
                    "url": url,
                    "label": clean_text(image.get("alt")),
                    "context": "",
                    "published": None,
                    "datePrecision": None,
                    "sourcePage": page_url,
                }
            )
    return list({row["url"]: row for row in rows if row["url"].startswith("https://")}.values())[:3]


def enrich_html_candidate(fetcher, item):
    try:
        body, final_url, content_type = fetcher.get(item["url"])
    except Exception as error:
        return item, f"detail fetch failed: {type(error).__name__}: {error}"
    if "html" not in content_type:
        return item, "detail URL did not return HTML"
    metadata = article_page_metadata(body.decode("utf-8", errors="replace"), final_url)
    detail_title = clean_text(metadata.get("title"))
    if detail_title and titles_match(detail_title, item.get("title")):
        item["title"] = detail_title[:180]
    elif detail_title and normalized_text(item.get("title")) in normalized_text(detail_title):
        item["title"] = detail_title[:180]
    if metadata.get("summary") and len(metadata["summary"]) >= 35:
        item["summary"] = metadata["summary"][:420]
    if metadata.get("published"):
        item["publishedAt"] = metadata["published"]
        item["datePrecision"] = metadata.get("datePrecision") or "day"
        item["dateSource"] = metadata.get("dateSource")
        item["detailVerified"] = True
    elif item.get("dateSource") == "structured-listing":
        item["detailVerified"] = bool(
            detail_title and titles_match(detail_title, item.get("title"))
        )
    if metadata.get("canonical"):
        item["url"] = metadata["canonical"]
    if metadata.get("thumbnail"):
        item["thumbnail"] = canonical_url(
            urllib.parse.urljoin(final_url, metadata["thumbnail"])
        )
    return item, None


def detail_candidates_from_page(
    fetcher, markup, page_url, community, source, seen_urls, budget=10
):
    """Recover dated articles when an index omits dates but detail metadata is explicit."""
    parser = CommunityHTMLParser()
    parser.feed(markup)
    candidates = []
    review = []
    consumed = 0
    for anchor in parser.results():
        if budget <= 0:
            break
        title = clean_text(anchor.get("title"))
        url = canonical_url(urllib.parse.urljoin(page_url, anchor.get("href")))
        suffix = Path(urllib.parse.urlsplit(url).path).suffix.lower()
        if (
            url in seen_urls
            or not url.startswith("https://")
            or not same_host(page_url, url)
            or suffix in MEDIA_SUFFIXES
            or not 8 <= len(title) <= 180
            or normalized_text(title) in GENERIC_LINK_TEXT
            or not is_supported_update(title, anchor.get("context"))
        ):
            continue
        budget -= 1
        consumed += 1
        try:
            body, final_url, content_type = fetcher.get(url)
            if "html" not in content_type:
                continue
            metadata = article_page_metadata(
                body.decode("utf-8", errors="replace"), final_url
            )
        except Exception as error:
            review.append({
                "bandId": community["bandId"],
                "communityName": community["communityName"],
                "sourceName": source.get("name"),
                "url": url,
                "status": "detail_unverified",
                "reason": f"detail fetch failed: {type(error).__name__}: {error}",
            })
            continue
        detail_title = clean_text(metadata.get("title")) or title
        if not metadata.get("published") or not is_supported_update(
            detail_title, metadata.get("summary")
        ):
            continue
        item = normalized_candidate(
            community,
            source,
            title=detail_title[:180],
            summary=item_summary(
                detail_title,
                metadata.get("summary"),
                source.get("name", "The source"),
            ),
            url=metadata.get("canonical") or final_url,
            published=metadata["published"],
            date_precision=metadata.get("datePrecision") or "day",
            thumbnail=(
                urllib.parse.urljoin(final_url, metadata.get("thumbnail"))
                if metadata.get("thumbnail")
                else None
            ),
            date_source=metadata.get("dateSource"),
            extraction_method="article-metadata",
            source_page=page_url,
        )
        item["detailVerified"] = True
        candidates.append(item)
        seen_urls.add(url)
    return candidates, review, consumed


def media_candidate(fetcher, community, source, media):
    try:
        text, method, final_url = extract_document_text(fetcher, media["url"])
    except Exception as error:
        return None, {
            "bandId": community["bandId"],
            "communityName": community["communityName"],
            "url": media["url"],
            "status": "document_unavailable",
            "reason": f"{type(error).__name__}: {error}",
        }
    title = document_title(text) or clean_text(media.get("label"))
    published, precision, date_source = document_publication_date(text)
    if not published and media.get("published"):
        published = media["published"]
        precision = media.get("datePrecision") or "day"
        date_source = "structured-listing"
    review = {
        "bandId": community["bandId"],
        "communityName": community["communityName"],
        "sourceName": source.get("name"),
        "url": final_url or media["url"],
        "extractionMethod": method,
        "detectedTitle": title or None,
        "detectedDate": published,
    }
    if not title or not published or not is_supported_update(title, text[:800]):
        review["status"] = "manual_review"
        review["reason"] = "Document lacks a clear news title, publication date, or relevant update context"
        return None, review
    item = normalized_candidate(
        community,
        source,
        title=title,
        summary=item_summary(title, clean_text(text)[:900], source.get("name", "The source")),
        url=final_url or media["url"],
        published=published,
        date_precision=precision,
        date_source=date_source,
        extraction_method=method,
        source_page=media.get("sourcePage"),
    )
    item["detailVerified"] = date_source != "structured-listing"
    review["status"] = "extracted"
    review["reason"] = "Source-backed media text extracted"
    return item, review


def scan_source(community, source, args, access_token):
    fetcher = Fetcher(delay=args.delay, timeout=args.timeout)
    candidates = []
    review = []
    failures = []
    checked_urls = []
    adapter = source.get("adapter")
    try:
        if adapter == "facebook":
            if not access_token:
                return [], [{
                    "bandId": community["bandId"],
                    "communityName": community["communityName"],
                    "sourceName": source.get("name"),
                    "url": source.get("url"),
                    "status": "authorized_api_required",
                    "reason": "Facebook posts require an authorized Meta API token",
                }], [], [source.get("url")]
            rows = discover_meta_posts(fetcher, community, source, access_token)
            return rows, review, failures, [source.get("url")]
        pages = []
        for url in discovery_urls(source):
            if not url:
                continue
            body, final_url, content_type = fetcher.get(url)
            checked_urls.append(final_url)
            if adapter == "rss" or "xml" in content_type:
                candidates.extend(extract_feed_candidates(body, final_url, community, source))
                continue
            if "html" not in content_type:
                continue
            markup = body.decode("utf-8", errors="replace")
            pages.append((final_url, markup))
            for update_url in discovered_update_pages(markup, final_url):
                try:
                    update_body, update_final, update_type = fetcher.get(update_url)
                    checked_urls.append(update_final)
                    if "html" in update_type:
                        pages.append((update_final, update_body.decode("utf-8", errors="replace")))
                except Exception as error:
                    failures.append({"url": update_url, "reason": f"update page: {type(error).__name__}: {error}"})
        media = []
        seen_candidate_urls = {candidate["url"] for candidate in candidates}
        detail_budget = 12
        for page_url, markup in pages:
            candidates.extend(extract_html_candidates(markup, page_url, community, source))
            media.extend(discovered_media(markup, page_url))
            recovered, detail_review, consumed = detail_candidates_from_page(
                fetcher,
                markup,
                page_url,
                community,
                source,
                seen_candidate_urls,
                detail_budget,
            )
            detail_budget = max(0, detail_budget - consumed)
            candidates.extend(recovered)
            review.extend(detail_review)
            seen_candidate_urls.update(candidate["url"] for candidate in candidates)
        enriched = []
        for item in list({candidate["url"]: candidate for candidate in candidates}.values())[:16]:
            detailed, warning = enrich_html_candidate(fetcher, item)
            if warning:
                review.append({
                    "bandId": community["bandId"],
                    "communityName": community["communityName"],
                    "sourceName": source.get("name"),
                    "url": item.get("url"),
                    "status": "detail_unverified",
                    "reason": warning,
                })
            enriched.append(detailed)
        candidates = enriched
        for media_item in list({item["url"]: item for item in media}.values())[:3]:
            item, document_review = media_candidate(fetcher, community, source, media_item)
            review.append(document_review)
            if item:
                candidates.append(item)
    except Exception as error:
        failures.append({"url": source.get("url"), "reason": f"{type(error).__name__}: {error}"})
    return candidates, review, failures, checked_urls


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
    source_runs = []
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

    scan_inputs = [
        (community, source)
        for community in communities
        for source in community.get("sources") or []
        if source_is_monitorable(source)
    ]
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        scan_results = executor.map(
            lambda row: scan_source(row[0], row[1], args, access_token),
            scan_inputs,
        )
    for (community, source), result in zip(scan_inputs, scan_results):
        found, source_review, source_failures, checked_urls = result
        candidates.extend(found)
        review.extend(source_review)
        for failure in source_failures:
            failures.append(
                {
                    "bandId": community["bandId"],
                    "communityName": community["communityName"],
                    "sourceName": source.get("name"),
                    "sourceType": source.get("type"),
                    "url": failure.get("url") or source.get("url"),
                    "reason": failure.get("reason"),
                }
            )
        source_runs.append(
            {
                "bandId": community["bandId"],
                "communityName": community["communityName"],
                "sourceName": source.get("name"),
                "sourceType": source.get("type"),
                "url": source.get("url"),
                "pagesChecked": len(checked_urls),
                "candidatesFound": len(found),
                "reviewItems": len(source_review),
                "status": "checked" if checked_urls else "unavailable",
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
        source_runs,
    )
    review_output = {
        "schemaVersion": 1,
        "generated": iso_now(),
        "items": review,
        "summary": {
            "manualReview": sum(1 for item in review if item.get("status") != "extracted"),
            "mediaExtracted": sum(1 for item in review if item.get("status") == "extracted"),
            "sourceFailures": len(failures),
        },
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
        f"articles={len(original_before)}->{len(merged)} "
        f"invalid_removed={len(invalid_existing_removed)}"
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
    parser.add_argument("--skip-search", action="store_true")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
