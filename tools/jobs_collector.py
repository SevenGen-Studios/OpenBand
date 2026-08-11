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
import re
import urllib.parse
import urllib.request
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


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def clean_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def slug(value: str) -> str:
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", clean_text(value).lower()))


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
    parts = [record.get("title"), record.get("employer"), record.get("communityId"), record.get("location")]
    return "|".join(slug(str(value or "")) for value in parts)


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
        "title": clean_text(raw.get("title")),
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

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.current = {"href": dict(attrs).get("href", ""), "text": []}

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current is not None:
            text = clean_text(" ".join(self.current["text"]))
            if text and self.current["href"]:
                self.anchors.append({"href": self.current["href"], "text": text})
            self.current = None


def fetch_source(source: dict) -> tuple[list[dict], list[str], str]:
    warnings = []
    request = urllib.request.Request(
        source["url"],
        headers={"User-Agent": "OpenBandJobs/1.0 (+https://openband.ca)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            markup = response.read().decode("utf-8", errors="replace")
    except Exception as exc:  # network failures belong in the report, not public data
        return [], [f"{source['id']}: fetch failed: {exc}"], ""
    parser = AnchorCollector()
    parser.feed(markup)
    candidates = []
    seen = set()
    for anchor in parser.anchors:
        title = clean_text(anchor["text"])
        href = urllib.parse.urljoin(source["url"], anchor["href"])
        if len(title) < 5 or len(title) > 140 or not JOB_WORDS.search(title):
            continue
        if not href.startswith(("https://", "http://")):
            continue
        if href in seen or href.rstrip("/") == source["url"].rstrip("/"):
            continue
        seen.add(href)
        community_ids = [str(value) for value in source.get("communityIds", [])]
        community_names = source.get("communityNames", [])
        candidate = normalize_listing(
            {
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
                "status": "Date unavailable" if source.get("autoPublish") else "Pending verification",
                "lastChecked": date.today().isoformat(),
                "extractionConfidence": "medium" if source.get("autoPublish") else "low",
                "verifiedOfficialSource": bool(source.get("verifiedOfficialSource")),
            },
            date.today(),
        )
        candidates.append(candidate)
    if not candidates:
        warnings.append(f"{source['id']}: no candidate job links detected")
    return candidates, warnings, clean_text(re.sub(r"<[^>]+>", " ", markup))


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
    source_data = read_json(root / "jobs-sources.json", {"sources": []})
    overrides = read_json(root / "jobs-overrides.json", {})
    previous = read_json(root / "jobs-data.json", {"listings": []})
    warnings = []
    candidates = []
    source_texts = {}
    if not offline:
        for source in source_data.get("sources", []):
            found, source_warnings, source_text = fetch_source(source)
            candidates.extend(found)
            warnings.extend(source_warnings)
            if source_text:
                source_texts[source["id"]] = source_text
    else:
        candidates.extend(row for row in previous.get("listings", []) if not row.get("manualOverride"))

    by_id = {}
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
        existing = by_id.get(key)
        if existing:
            duplicate_count += 1
            if record.get("manualOverride") or not existing.get("manualOverride") and record.get("extractionConfidence") == "high":
                by_id[key] = record
        else:
            by_id[key] = record

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
    for source in source_data.get("sources", []):
        for community_id in source_coverage(source, set(tracked)):
            coverage_sources[community_id].append({"id": source["id"], "name": source["name"], "url": source["url"]})
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
        "sourcesConfigured": len(source_data.get("sources", [])),
        "sourcesChecked": 0 if offline else len(source_data.get("sources", [])),
        "verifiedActiveListings": len([row for row in active if row.get("verifiedOfficialSource")]),
        "communitiesWithListings": data["communityCount"],
        "pendingVerification": len([row for row in listings if row["status"] == "Pending verification"]),
        "expiredOrClosed": len([row for row in listings if row["status"] == "Closed"]),
        "duplicatesSuppressed": duplicate_count,
        "trackedCommunities": len(tracked),
        "communitiesWithSourceCoverage": len([value for value in coverage_sources.values() if value]),
        "warnings": warnings,
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
    write_json(args.root / "jobs-data.json", data)
    write_json(args.root / "jobs-coverage-report.json", report)
    print(
        f"Jobs: {report['verifiedActiveListings']} verified active, "
        f"{report['pendingVerification']} pending, {report['expiredOrClosed']} closed"
    )


if __name__ == "__main__":
    main()
