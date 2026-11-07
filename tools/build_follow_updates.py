"""Publish verified updates for the inbox and background delivery."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from tools.events_discovery import is_publishable_event
from tools.build_site import slugify
from tools.jobs_collector import ACTIVE_STATUSES, effective_status, parse_date, validation_warnings, write_json
from tools.news_discovery import canonical_url

ROOT = Path(__file__).resolve().parents[1]


def https_url(value):
    try:
        parsed = urlsplit(str(value or ""))
    except ValueError:
        return ""
    return str(value) if parsed.scheme == "https" and parsed.hostname and not parsed.username else ""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def build(root=ROOT, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.date()
    output = root / "follow-updates.json"

    def load(name):
        return json.loads((root / name).read_text(encoding="utf-8"))

    communities = {
        str(band["id"]): {
            "name": band["name"], "province": band["province"],
            "path": f"/first-nations/{slugify(band['name'])}/",
        }
        for band in load("data.json")["bands"]
    }
    old_feed = load(output.name) if output.exists() else {}
    previous = {row["id"]: row for row in old_feed.get("updates", []) + old_feed.get("inactive", [])}
    updates = {}

    def add(kind, row, community_ids, source, milestone, details):
        source = https_url(source)
        title = str(row.get("title") or row.get("name") or "").strip()
        if not row.get("id") or not source or not title:
            return
        # Use the source permalink for articles and vacancy reposts. A calendar
        # can publish several occurrences on one URL, so events retain their IDs.
        identity = canonical_url(source) if kind in {"news", "jobs"} else row["id"]
        if kind == "jobs" and urlsplit(source).fragment:
            identity += "#" + urlsplit(source).fragment
        for community_id in sorted(set(map(str, community_ids)) & communities.keys()):
            key = digest([kind, community_id, identity])
            prior = previous.get(key)
            revision = digest({key: value for key, value in details.items() if key != "milestoneDate"})
            observed = prior["updatedAt"] if prior and prior["revision"] == revision else now.isoformat()
            item = {
                "id": key, "revision": revision, "kind": kind, "communityId": community_id,
                "title": title, "sourceUrl": source, "date": milestone.isoformat() if milestone else None,
                "firstSeenAt": (prior or {}).get("firstSeenAt") or (prior or {}).get("updatedAt") or now.isoformat(),
                "updatedAt": observed, **details,
            }
            # A repeated source URL can appear via different discovery adapters.
            # Prefer the more recently dated version without emitting two cards.
            existing = updates.get(key)
            if not existing or (item["date"] or "") > (existing["date"] or ""):
                updates[key] = item

    recent = today - timedelta(days=30)
    for row in load("news-data.json")["articles"]:
        published = parse_date(row.get("publishedAt"))
        if published and recent <= published <= today:
            add("news", row, [row.get("bandId")], row.get("url"), published, {})

    for row in load("events-data.json")["events"]:
        start = parse_date(row.get("startDate"))
        end = parse_date(row.get("endDate")) or start
        if start and end >= today and is_publishable_event(row, today):
            add("events", row, [row.get("bandId")], row.get("sourceUrl"), start, {
                "startDate": start.isoformat(), "endDate": end.isoformat(),
                "time": row.get("startTime"), "endTime": row.get("endTime"),
                "timeZone": row.get("timeZone"), "location": row.get("location"),
            })

    for row in load("jobs-data.json")["listings"]:
        if row.get("verifiedOfficialSource") and not validation_warnings(row) and effective_status(row, today) in ACTIVE_STATUSES:
            add("jobs", row, [row.get("communityId"), *row.get("firstNationIds", [])], row.get("sourceUrl"),
                parse_date(row.get("postedDate")), {"closingDate": row.get("closingDate")})

    for row in load("projects-data.json")["projects"]:
        milestone = parse_date(row.get("statusAsOf"))
        sources = row.get("sources") or []
        if row.get("status") and milestone and recent <= milestone <= today and sources:
            add("projects", row, row.get("firstNationIds", []), sources[0].get("url"), milestone, {
                "status": row["status"], "milestoneDate": milestone.isoformat(),
            })

    cutoff = (today - timedelta(days=90)).isoformat()
    inactive = [{"id": key, "revision": row["revision"], "updatedAt": row["updatedAt"],
                 "firstSeenAt": row.get("firstSeenAt") or row["updatedAt"]}
                for key, row in sorted(previous.items()) if key not in updates and row["updatedAt"][:10] >= cutoff]
    payload = {
        "schemaVersion": 1, "communities": communities, "inactive": inactive,
        "updates": sorted(updates.values(), key=lambda row: (row["updatedAt"], row["date"] or "", row["id"]), reverse=True),
    }
    directory = root / "follow-data"
    directory.mkdir(exist_ok=True)
    grouped = {community_id: [] for community_id in communities}
    for item in payload["updates"]:
        grouped[item["communityId"]].append(item)
    for community_id, community in communities.items():
        path = directory / f"{community_id}.json"
        entry = {"schemaVersion": 1, "communities": {community_id: community}, "updates": grouped[community_id]}
        if not path.exists() or entry != load(path.relative_to(root)):
            write_json(path, entry)
    index = directory / "communities.json"
    if not index.exists() or communities != load(index.relative_to(root)):
        write_json(index, communities)
    if payload != old_feed:
        write_json(output, payload)
    return payload


if __name__ == "__main__":
    print(f"My community feed has {len(build()['updates'])} verified updates.")
