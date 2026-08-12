#!/usr/bin/env python3
"""Collect and validate source-linked OpenBand employment records.

The collector is intentionally deterministic. It discovers candidate links from
configured public pages, applies manual corrections last, and only publishes a
candidate automatically when its source configuration explicitly permits it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_STATUSES = {"Open", "Closing soon"}
PUBLIC_STATUSES = ACTIVE_STATUSES | {"Date unavailable"}
JOB_WORDS = re.compile(
    r"\b(job|career|position|worker|manager|director|coordinator|teacher|nurse|"
    r"clerk|accountant|receptionist|janitor|maintenance|employment|officer|"
    r"counsellor|educator|peacekeeper|support)\b",
    re.IGNORECASE,
)
GENERIC_LINK_TITLES = re.compile(
    r"^(jobs?|careers?|employment(?: opportunities)?|job opportunities|view jobs?|apply(?: now)?|job summary|position summary)$",
    re.IGNORECASE,
)
CLOSED_WORDS = re.compile(
    r"\b(position filled|posting closed|applications? closed|no longer accepting|competition closed)\b",
    re.IGNORECASE,
)
OPEN_UNTIL_FILLED = re.compile(r"\b(open until filled|until (?:a suitable candidate is )?filled)\b", re.IGNORECASE)
EMPLOYMENT_PAGE_WORDS = re.compile(r"\b(job|jobs|career|careers|employment|opportunities|work with us)\b", re.IGNORECASE)
MEDIA_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
NON_JOB_MEDIA = re.compile(r"\b(logo|icon|favicon|banner|header|footer|avatar|sponsor)\b", re.IGNORECASE)
MONTHS = {
    name.lower(): number
    for number, name in enumerate(
        ("", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
    )
}


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def clean_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def slug(value: str) -> str:
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", clean_text(value).lower()))


def clean_job_title(value: str) -> str:
    title = clean_text(value)
    title = re.sub(r"^.*?\bis hiring!?\s*(?:position)?\s*[:\-]\s*", "", title, flags=re.I)
    title = re.sub(r"\s*[\-(–—]\s*(?:apply by|deadline to apply|open until filled)\b.*$", "", title, flags=re.I)
    title = re.sub(r"\s*\((?:apply by|deadline|open until filled)\b.*\)\s*$", "", title, flags=re.I)
    return clean_text(title.strip(" -–—:"))


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def effective_status(record: dict, today: date) -> str:
    closing = parse_date(record.get("closingDate"))
    checked = parse_date(record.get("lastChecked"))
    stated = clean_text(record.get("status"))
    if closing:
        if closing < today:
            return "Closed"
        if closing <= today + timedelta(days=7):
            return "Closing soon"
        return "Open"
    if stated == "Closed":
        return "Closed"
    if stated in ACTIVE_STATUSES:
        return stated if checked and checked >= today - timedelta(days=21) else "Pending verification"
    if stated == "Date unavailable" and checked and checked >= today - timedelta(days=21):
        return stated
    return "Pending verification"


def listing_key(record: dict) -> str:
    title = re.sub(r"\b(and|the)\b", " ", clean_job_title(record.get("title") or ""), flags=re.I)
    parts = [title, record.get("employer"), record.get("communityId"), record.get("location")]
    return "|".join(slug(str(value or "")) for value in parts)


def discovery_key(record: dict) -> str:
    title = re.sub(r"\b(and|the)\b", " ", clean_job_title(record.get("title") or ""), flags=re.I)
    associations = sorted(
        {clean_text(record.get("communityId"))} | {clean_text(value) for value in record.get("firstNationIds", [])}
    )
    return "|".join([slug(title), slug(record.get("sourceId") or ""), ",".join(value for value in associations if value)])


def stable_id(record: dict) -> str:
    key = listing_key(record)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    return f"job-{slug(record.get('title') or 'listing')[:48]}-{digest}"


def normalize_listing(raw: dict, today: date) -> dict:
    first_nation_ids = []
    for value in raw.get("firstNationIds", []):
        normalized = clean_text(value)
        if normalized and normalized not in first_nation_ids:
            first_nation_ids.append(normalized)
    record = {
        "id": clean_text(raw.get("id")),
        "title": clean_job_title(raw.get("title")),
        "employer": clean_text(raw.get("employer")),
        "communityName": clean_text(raw.get("communityName")),
        "communityId": clean_text(raw.get("communityId")),
        "firstNationIds": first_nation_ids,
        "scope": clean_text(raw.get("scope")) or ("regional" if first_nation_ids else "community"),
        "sourceId": clean_text(raw.get("sourceId")),
        "location": clean_text(raw.get("location")),
        "employmentType": clean_text(raw.get("employmentType")),
        "category": clean_text(raw.get("category")) or "Other",
        "postedDate": raw.get("postedDate") or None,
        "closingDate": raw.get("closingDate") or None,
        "salary": raw.get("salary") or None,
        "applicationMethod": raw.get("applicationMethod") or None,
        "applicationUrl": raw.get("applicationUrl") or None,
        "sourceUrl": clean_text(raw.get("sourceUrl")),
        "sourceName": clean_text(raw.get("sourceName")) or "Original source",
        "description": clean_text(raw.get("description")),
        "qualifications": clean_text(raw.get("qualifications")) or None,
        "workplaceType": clean_text(raw.get("workplaceType")) or None,
        "status": clean_text(raw.get("status")) or "Pending verification",
        "lastChecked": str(raw.get("lastChecked") or today.isoformat())[:10],
        "extractionConfidence": clean_text(raw.get("extractionConfidence")) or "low",
        "verifiedOfficialSource": bool(raw.get("verifiedOfficialSource")),
        "manualOverride": bool(raw.get("manualOverride")),
    }
    record["id"] = record["id"] or stable_id(record)
    record["status"] = effective_status(record, today)
    return record


def validation_warnings(record: dict) -> list[str]:
    warnings = []
    for field in ("title", "employer", "sourceUrl"):
        if not record.get(field):
            warnings.append(f"Missing {field}")
    if record.get("sourceUrl") and not str(record["sourceUrl"]).startswith(("https://", "http://")):
        warnings.append("Invalid source URL")
    if record.get("applicationUrl") and not str(record["applicationUrl"]).startswith(("https://", "http://")):
        warnings.append("Invalid application URL")
    if record.get("status") in ACTIVE_STATUSES and not record.get("verifiedOfficialSource"):
        warnings.append("Active listing is not tied to a verified official source")
    return warnings


class AnchorCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current = None
        self.anchors = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag.lower() == "a":
            self.current = {"href": attributes.get("href", ""), "text": [], "images": []}
        elif tag.lower() == "img":
            image = {
                "src": attributes.get("src") or attributes.get("data-src") or attributes.get("data-lazy-src") or "",
                "alt": attributes.get("alt", ""),
                "width": attributes.get("width"),
                "height": attributes.get("height"),
            }
            if image["src"]:
                self.images.append(image)
                if self.current is not None:
                    self.current["images"].append(image)

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current is not None:
            text = clean_text(" ".join(self.current["text"]))
            if text and self.current["href"]:
                self.anchors.append({"href": self.current["href"], "text": text, "images": self.current["images"]})
            elif self.current["href"] and self.current["images"]:
                alt = clean_text(" ".join(image.get("alt", "") for image in self.current["images"]))
                self.anchors.append({"href": self.current["href"], "text": alt, "images": self.current["images"]})
            self.current = None


def configured_sources(root: Path) -> list[dict]:
    """Merge curated boards with ISC-listed community sites and verified Facebook pages."""
    curated = read_json(root / "jobs-sources.json", {"sources": []}).get("sources", [])
    sources = list(curated)
    known_pairs = {(str(cid), source["url"].rstrip("/")) for source in sources for cid in source.get("communityIds", [])}
    contacts = read_json(root / "contacts-data.json", {"contacts": []}).get("contacts", [])
    for contact in contacts:
        url = clean_text(contact.get("website_url"))
        if url.startswith("http://"):
            url = "https://" + url.removeprefix("http://")
        community_id = str(contact.get("nation_id") or "")
        if not url or (community_id, url.rstrip("/")) in known_pairs:
            continue
        sources.append({
            "id": f"community-site-{community_id}",
            "name": f"{contact.get('nation_name')} official website",
            "url": url,
            "sourceType": "isc_listed_first_nation_website",
            "communityIds": [community_id],
            "communityNames": [contact.get("nation_name")],
            "verifiedOfficialSource": True,
            "autoPublish": False,
            "discoverEmploymentPages": True,
            "scanMedia": True,
        })
        known_pairs.add((community_id, url.rstrip("/")))
    news = read_json(root / "news-data.json", {"communitySources": []})
    for community in news.get("communitySources", []):
        community_id = str(community.get("bandId") or "")
        for source in community.get("sources", []):
            url = clean_text(source.get("url"))
            if source.get("status") != "verified" or "facebook.com" not in url.lower():
                continue
            if (community_id, url.rstrip("/")) in known_pairs:
                continue
            sources.append({
                "id": f"community-facebook-{community_id}-{len(sources)}",
                "name": f"{community.get('communityName')} official Facebook page",
                "url": url,
                "sourceType": "verified_official_facebook",
                "communityIds": [community_id],
                "communityNames": [community.get("communityName")],
                "verifiedOfficialSource": True,
                "autoPublish": False,
                "discoverEmploymentPages": False,
                "scanMedia": True,
            })
            known_pairs.add((community_id, url.rstrip("/")))
    return sources


def fetch_markup(url: str) -> tuple[str, str | None]:
    request = urllib.request.Request(url, headers={"User-Agent": "OpenBandJobs/1.1 (+https://openband.ca)"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                return "", f"non-HTML source ({content_type})"
            return response.read().decode("utf-8", errors="replace"), None
    except Exception as exc:
        return "", str(exc)


def fetch_binary(url: str) -> tuple[bytes, str, str | None]:
    request = urllib.request.Request(url, headers={"User-Agent": "OpenBandJobs/1.1 (+https://openband.ca)"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            content = response.read(15 * 1024 * 1024 + 1)
            if len(content) > 15 * 1024 * 1024:
                return b"", "", "document exceeds 15 MB limit"
            return content, response.headers.get_content_type(), None
    except Exception as exc:
        return b"", "", str(exc)


def run_text_command(command: list[str], timeout: int = 45) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def extract_document_text(url: str) -> tuple[str, str, str | None]:
    """Use embedded PDF text first, then free local OCR as a fallback."""
    payload, content_type, error = fetch_binary(url)
    if error:
        return "", "fetch_failed", error
    suffix = Path(urllib.parse.urlsplit(url).path).suffix.lower()
    if content_type == "application/pdf" or suffix == ".pdf":
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "posting.pdf"
            pdf_path.write_bytes(payload)
            if shutil.which("pdftotext"):
                text = run_text_command(["pdftotext", "-layout", str(pdf_path), "-"])
                if len(clean_text(text)) >= 80:
                    return text, "pdf_text", None
            if not shutil.which("pdftoppm") or not shutil.which("tesseract"):
                return "", "ocr_unavailable", "PDF has no usable text and OCR tools are unavailable"
            prefix = Path(directory) / "page"
            run_text_command(["pdftoppm", "-f", "1", "-l", "2", "-jpeg", "-r", "180", str(pdf_path), str(prefix)], timeout=45)
            pages = []
            for image_path in sorted(Path(directory).glob("page-*.jpg")):
                pages.append(run_text_command(["tesseract", str(image_path), "stdout", "--psm", "6"], timeout=30))
            text = "\n".join(pages)
            return text, "pdf_ocr", None if clean_text(text) else "OCR returned no text"
    if content_type.startswith("image/") or suffix in MEDIA_SUFFIXES:
        if not shutil.which("tesseract"):
            return "", "ocr_unavailable", "Tesseract is unavailable"
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / f"posting{suffix if suffix in MEDIA_SUFFIXES else '.img'}"
            image_path.write_bytes(payload)
            text = run_text_command(["tesseract", str(image_path), "stdout", "--psm", "6"], timeout=30)
            return text, "image_ocr", None if clean_text(text) else "OCR returned no text"
    return "", "unsupported_media", f"unsupported content type {content_type or 'unknown'}"


def title_from_document(text: str) -> str:
    generic = re.compile(r"^(job|employment|career)\s+(posting|opportunity|notice)s?$", re.IGNORECASE)
    candidates = []
    for raw_line in text.splitlines()[:80]:
        line = clean_text(raw_line).strip("-|:•")
        if not 6 <= len(line) <= 130 or generic.match(line) or GENERIC_LINK_TITLES.match(line):
            continue
        if re.search(r"\b(closing|deadline|salary|applications?|qualifications?|responsibilities)\b", line, re.I):
            continue
        if JOB_WORDS.search(line):
            score = 2 if re.search(r"\b(manager|director|coordinator|teacher|nurse|worker|clerk|officer|assistant|operator)\b", line, re.I) else 1
            candidates.append((score, -len(line), line))
    if not candidates:
        return ""
    title = sorted(candidates, reverse=True)[0][2]
    return clean_text(re.sub(r"^(?:job|employment)\s+(?:posting|opportunity)\s*[:\-]?\s*", "", title, flags=re.I))


def document_candidate(url: str, source: dict, today: date) -> tuple[dict | None, dict]:
    text, method, error = extract_document_text(url)
    title = title_from_document(text)
    closing = extract_labeled_date(text, ("closing", "deadline", "apply by", "applications close")) if text else None
    posted = extract_labeled_date(text, ("posted", "posting date", "published")) if text else None
    status = "Pending verification"
    if text and CLOSED_WORDS.search(text):
        status = "Closed"
    elif closing:
        status = effective_status({"closingDate": closing, "lastChecked": today.isoformat()}, today)
    elif text and OPEN_UNTIL_FILLED.search(text):
        status = "Date unavailable"
    community_ids = [str(value) for value in source.get("communityIds", [])]
    community_names = source.get("communityNames", [])
    review = {
        "sourceId": source["id"],
        "sourceName": source["name"],
        "sourceUrl": url,
        "communityIds": community_ids,
        "communityNames": community_names,
        "candidateTitle": title or None,
        "extractionMethod": method,
        "status": status,
        "reason": error or ("No reliable job title detected" if not title else "Closing status requires verification"),
        "textSnippet": clean_text(text)[:700] or None,
    }
    if not title:
        return None, review
    candidate = normalize_listing({
        "title": title,
        "employer": source["name"],
        "communityId": community_ids[0] if len(community_ids) == 1 else "",
        "communityName": community_names[0] if len(community_names) == 1 else "",
        "firstNationIds": community_ids if len(community_ids) > 1 and source.get("associationMode") != "source_only" else [],
        "scope": "regional" if len(community_ids) > 1 else "community",
        "sourceId": source["id"],
        "sourceUrl": url,
        "sourceName": source["name"],
        "description": "Opportunity extracted from an official image or PDF posting. Review the original source for complete details.",
        "postedDate": posted,
        "closingDate": closing,
        "status": status,
        "lastChecked": today.isoformat(),
        "extractionConfidence": "high" if status in PUBLIC_STATUSES | {"Closed"} else "medium",
        "verifiedOfficialSource": bool(source.get("verifiedOfficialSource")),
    }, today)
    return candidate, review


def page_text(markup: str) -> str:
    return clean_text(re.sub(r"<[^>]+>", " ", markup))


def extract_labeled_date(text: str, labels: tuple[str, ...]) -> str | None:
    label_pattern = "|".join(re.escape(label) for label in labels)
    patterns = (
        rf"(?:{label_pattern})\s*(?:date)?\s*[:\-]?\s*([A-Z][a-z]+)\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(20\d{{2}})",
        rf"(?:{label_pattern})\s*(?:date)?\s*[:\-]?\s*(20\d{{2}})[-/](\d{{1,2}})[-/](\d{{1,2}})",
    )
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        try:
            if index == 0:
                month, day, year = match.groups()
                return date(int(year), MONTHS[month.lower()], int(day)).isoformat()
            year, month, day = match.groups()
            return date(int(year), int(month), int(day)).isoformat()
        except (KeyError, ValueError):
            continue
    return None


def inspect_candidate_page(url: str, today: date) -> tuple[dict, list[str]]:
    markup, error = fetch_markup(url)
    if error:
        return {}, [f"detail fetch failed: {error}"]
    text = page_text(markup)
    closing = extract_labeled_date(text, ("closing", "deadline", "apply by", "applications close"))
    posted = extract_labeled_date(text, ("posted", "posting date", "published"))
    status = "Pending verification"
    if CLOSED_WORDS.search(text):
        status = "Closed"
    elif closing:
        status = effective_status({"closingDate": closing, "lastChecked": today.isoformat()}, today)
    elif OPEN_UNTIL_FILLED.search(text):
        status = "Date unavailable"
    return {
        "closingDate": closing,
        "postedDate": posted,
        "status": status,
        "detailText": text,
    }, []


def fetch_source(source: dict, today: date | None = None) -> tuple[list[dict], list[str], str, list[dict]]:
    today = today or date.today()
    warnings = []
    markup, error = fetch_markup(source["url"])
    if error:
        review = [{
            "sourceId": source["id"],
            "sourceName": source["name"],
            "sourceUrl": source["url"],
            "communityIds": [str(value) for value in source.get("communityIds", [])],
            "communityNames": source.get("communityNames", []),
            "status": "source_unavailable",
            "reason": error,
        }]
        return [], [f"{source['id']}: fetch failed: {error}"], "", review
    root_parser = AnchorCollector()
    root_parser.feed(markup)
    pages = [(source["url"], markup, bool(source.get("parser") == "job_link_index"))]
    if source.get("discoverEmploymentPages"):
        host = urllib.parse.urlsplit(source["url"]).netloc.lower().removeprefix("www.")
        discovered = []
        for anchor in root_parser.anchors:
            href = urllib.parse.urljoin(source["url"], anchor["href"])
            target_host = urllib.parse.urlsplit(href).netloc.lower().removeprefix("www.")
            label = f"{anchor.get('text', '')} {urllib.parse.urlsplit(href).path}"
            if target_host != host or not EMPLOYMENT_PAGE_WORDS.search(label):
                continue
            if Path(urllib.parse.urlsplit(href).path).suffix.lower() in MEDIA_SUFFIXES:
                continue
            if href.rstrip("/") != source["url"].rstrip("/") and href not in discovered:
                discovered.append(href)
        for page_url in discovered[:4]:
            page_markup, page_error = fetch_markup(page_url)
            if page_error:
                warnings.append(f"{source['id']}: employment page fetch failed: {page_error}")
                continue
            pages.append((page_url, page_markup, True))
    candidates = []
    review_items = []
    seen = set()
    media_urls = []
    detail_budget = 4
    for page_url, page_markup, employment_context in pages:
        parser = AnchorCollector()
        parser.feed(page_markup)
        for anchor in parser.anchors:
            title = clean_text(anchor["text"])
            href = urllib.parse.urljoin(page_url, anchor["href"])
            suffix = Path(urllib.parse.urlsplit(href).path).suffix.lower()
            media_hint = f"{title} {href}"
            if suffix in MEDIA_SUFFIXES and (employment_context or JOB_WORDS.search(media_hint)):
                if href not in media_urls:
                    media_urls.append(href)
                continue
            if len(title) < 5 or len(title) > 140 or not JOB_WORDS.search(title):
                continue
            if GENERIC_LINK_TITLES.match(title) or not href.startswith(("https://", "http://")):
                continue
            if href in seen or href.rstrip("/") in {page_url.rstrip("/"), source["url"].rstrip("/")}:
                continue
            seen.add(href)
            community_ids = [str(value) for value in source.get("communityIds", [])]
            community_names = source.get("communityNames", [])
            inspect = bool(source.get("inspectDetails") or source.get("discoverEmploymentPages")) and detail_budget > 0
            detail, detail_warnings = inspect_candidate_page(href, today) if inspect else ({}, [])
            if inspect:
                detail_budget -= 1
            warnings.extend(f"{source['id']}: {warning}" for warning in detail_warnings)
            detected_status = detail.get("status", "Pending verification")
            if detected_status == "Pending verification" and source.get("autoPublish"):
                detected_status = "Date unavailable"
            candidate = normalize_listing({
                "title": title,
                "employer": source["name"],
                "communityId": community_ids[0] if len(community_ids) == 1 else "",
                "communityName": community_names[0] if len(community_names) == 1 else "",
                "firstNationIds": community_ids if len(community_ids) > 1 and source.get("associationMode") != "source_only" else [],
                "scope": "regional" if len(community_ids) > 1 else "community",
                "sourceId": source["id"],
                "sourceUrl": href,
                "sourceName": source["name"],
                "description": "Candidate opportunity discovered on an official employment source. Details require verification.",
                "postedDate": detail.get("postedDate"),
                "closingDate": detail.get("closingDate"),
                "status": detected_status,
                "lastChecked": today.isoformat(),
                "extractionConfidence": "high" if detected_status in PUBLIC_STATUSES | {"Closed"} else "low",
                "verifiedOfficialSource": bool(source.get("verifiedOfficialSource")),
            }, today)
            candidates.append(candidate)
        if source.get("scanMedia"):
            for image in parser.images:
                src = urllib.parse.urljoin(page_url, image.get("src", ""))
                hint = f"{image.get('alt', '')} {src}"
                if not src.startswith(("https://", "http://")) or NON_JOB_MEDIA.search(hint):
                    continue
                if employment_context or JOB_WORDS.search(hint):
                    if src not in media_urls:
                        media_urls.append(src)
    for media_url in media_urls[:3]:
        candidate, review = document_candidate(media_url, source, today)
        review_items.append(review)
        if candidate:
            candidates.append(candidate)
    if not candidates:
        warnings.append(f"{source['id']}: no candidate job links detected")
    return candidates, warnings, page_text(markup), review_items


def source_coverage(source: dict, tracked_ids: set[str]) -> set[str]:
    if source.get("coversAllTrackedCommunities"):
        return set(tracked_ids)
    return {clean_text(value) for value in source.get("communityIds", []) if clean_text(value) in tracked_ids}


def listing_is_confirmed_on_source(record: dict, source_texts: dict[str, str]) -> bool:
    source_id = clean_text(record.get("sourceId"))
    page_text = source_texts.get(source_id, "")
    title = clean_text(record.get("title"))
    if not page_text or not title:
        return False
    normalized_page = slug(page_text)
    normalized_title = slug(re.sub(r"\b(job|employment)\s+opportunit(?:y|ies)\b", "", title, flags=re.I))
    return bool(normalized_title and normalized_title in normalized_page)


def expand_verified_batches(overrides: dict) -> list[dict]:
    rows = list(overrides.get("manualListings", []))
    for batch in overrides.get("verifiedBatches", []):
        common = {key: value for key, value in batch.items() if key != "jobs"}
        for job in batch.get("jobs", []):
            rows.append({**common, **job, "manualOverride": True})
    return rows


def collect(root: Path, today: date, offline: bool = False) -> tuple[dict, dict]:
    sources = configured_sources(root)
    overrides = read_json(root / "jobs-overrides.json", {})
    previous = read_json(root / "jobs-data.json", {"listings": []})
    warnings = []
    candidates = []
    source_texts = {}
    review_items = []
    source_runs = []
    if not offline:
        with ThreadPoolExecutor(max_workers=6) as executor:
            scan_results = executor.map(lambda source: fetch_source(source, today), sources)
        for source, result in zip(sources, scan_results):
            found, source_warnings, source_text, source_review = result
            candidates.extend(found)
            warnings.extend(source_warnings)
            review_items.extend(source_review)
            source_runs.append({
                "sourceId": source["id"],
                "sourceName": source["name"],
                "url": source["url"],
                "sourceType": source.get("sourceType"),
                "communityIds": [str(value) for value in source.get("communityIds", [])],
                "candidatesFound": len(found),
                "reviewItems": len(source_review),
                "status": "checked" if source_text else "unavailable",
                "warnings": source_warnings,
            })
            if source_text:
                source_texts[source["id"]] = source_text
    else:
        candidates.extend(row for row in previous.get("listings", []) if not row.get("manualOverride"))

    by_id = {}
    by_discovery = {}
    duplicate_count = 0
    suppressed = {str(value) for value in overrides.get("suppressIds", [])}
    corrections = overrides.get("corrections", {})
    manual_rows = []
    for raw in expand_verified_batches(overrides):
        refreshed = dict(raw)
        if not offline and listing_is_confirmed_on_source(refreshed, source_texts):
            refreshed["lastChecked"] = today.isoformat()
        manual_rows.append(refreshed)
    for raw in candidates + manual_rows:
        patched = {**raw, **corrections.get(str(raw.get("id", "")), {})}
        record = normalize_listing(patched, today)
        if record["id"] in suppressed:
            continue
        issues = validation_warnings(record)
        if issues:
            record["status"] = "Pending verification"
            record["warnings"] = issues
        key = listing_key(record)
        source_key = discovery_key(record)
        existing_key = by_discovery.get(source_key)
        existing = by_id.get(key) or (by_id.get(existing_key) if existing_key else None)
        if existing:
            duplicate_count += 1
            if record.get("manualOverride") or not existing.get("manualOverride") and record.get("extractionConfidence") == "high":
                old_key = listing_key(existing)
                if old_key != key:
                    by_id.pop(old_key, None)
                by_id[key] = record
                by_discovery[source_key] = key
        else:
            by_id[key] = record
            by_discovery[source_key] = key

    listings = sorted(by_id.values(), key=lambda row: (row.get("postedDate") or row.get("lastChecked") or "", row["title"]), reverse=True)
    active = [row for row in listings if row["status"] in ACTIVE_STATUSES]
    public = [row for row in listings if row["status"] in PUBLIC_STATUSES]
    public_community_ids = set()
    for row in public:
        if row.get("communityId"):
            public_community_ids.add(str(row["communityId"]))
        public_community_ids.update(str(value) for value in row.get("firstNationIds", []) if value)
    data = {
        "schemaVersion": 1,
        "generated": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "listingCount": len(listings),
        "activeCount": len(active),
        "communityCount": len(public_community_ids),
        "listings": listings,
        "employmentPrograms": overrides.get("employmentPrograms", []),
        "warnings": warnings,
    }
    map_data = read_json(root / "map-data.json", {"communities": []})
    tracked = {str(row.get("id")): row for row in map_data.get("communities", []) if row.get("id") is not None}
    coverage_sources = {community_id: [] for community_id in tracked}
    for source in sources:
        for community_id in source_coverage(source, set(tracked)):
            coverage_sources[community_id].append({
                "id": source["id"],
                "name": source["name"],
                "url": source["url"],
                "sourceType": source.get("sourceType"),
                "direct": len(source.get("communityIds", [])) == 1,
            })
    data["communityCoverage"] = [
        {
            "communityId": community_id,
            "communityName": tracked[community_id].get("name"),
            "sources": coverage_sources[community_id],
            "activeListings": len([
                row for row in public
                if str(row.get("communityId")) == community_id or community_id in row.get("firstNationIds", [])
            ]),
            "status": "active_listings" if any(
                str(row.get("communityId")) == community_id or community_id in row.get("firstNationIds", [])
                for row in public
            ) else "sources_checked_no_active_listing",
        }
        for community_id in sorted(tracked, key=lambda value: tracked[value].get("name", ""))
    ]
    report = {
        "generated": data["generated"],
        "sourcesConfigured": len(sources),
        "sourcesChecked": 0 if offline else len(sources),
        "verifiedActiveListings": len([row for row in active if row.get("verifiedOfficialSource")]),
        "communitiesWithListings": data["communityCount"],
        "pendingVerification": len([row for row in listings if row["status"] == "Pending verification"]),
        "expiredOrClosed": len([row for row in listings if row["status"] == "Closed"]),
        "duplicatesSuppressed": duplicate_count,
        "trackedCommunities": len(tracked),
        "communitiesWithSourceCoverage": len([value for value in coverage_sources.values() if value]),
        "communitiesWithDirectSources": len([
            value for value in coverage_sources.values() if any(source.get("direct") for source in value)
        ]),
        "mediaDocumentsReviewed": len(review_items),
        "warnings": warnings,
    }
    pending_rows = [row for row in listings if row["status"] == "Pending verification"]
    report["_reviewQueue"] = {
        "schemaVersion": 1,
        "generated": data["generated"],
        "summary": {
            "pendingCandidates": len(pending_rows),
            "mediaDocuments": len(review_items),
            "sourceWarnings": len(warnings),
        },
        "pendingCandidates": pending_rows,
        "documentReviews": review_items,
        "sourceWarnings": warnings,
    }
    report["_sourceRegistry"] = {
        "schemaVersion": 1,
        "generated": data["generated"],
        "trackedCommunityCount": len(tracked),
        "configuredSourceCount": len(sources),
        "communities": [
            {
                "communityId": community_id,
                "communityName": tracked[community_id].get("name"),
                "directSources": [source for source in coverage_sources[community_id] if source.get("direct")],
                "regionalSources": [source for source in coverage_sources[community_id] if not source.get("direct")],
                "status": "direct_source_configured" if any(source.get("direct") for source in coverage_sources[community_id]) else "regional_sources_only",
            }
            for community_id in sorted(tracked, key=lambda value: tracked[value].get("name", ""))
        ],
        "sourceRuns": source_runs,
    }
    return data, report


def write_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    data, report = collect(args.root, args.today, args.offline)
    review_queue = report.pop("_reviewQueue")
    source_registry = report.pop("_sourceRegistry")
    write_json(args.root / "jobs-data.json", data)
    write_json(args.root / "jobs-coverage-report.json", report)
    write_json(args.root / "jobs-review-queue.json", review_queue)
    write_json(args.root / "jobs-source-registry.json", source_registry)
    print(
        f"Jobs: {report['verifiedActiveListings']} verified active, "
        f"{report['pendingVerification']} pending, {report['expiredOrClosed']} closed"
    )


if __name__ == "__main__":
    main()
