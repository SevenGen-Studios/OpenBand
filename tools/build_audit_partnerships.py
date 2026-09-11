"""Publish only audit leads corroborated by OpenBand's reviewed public sources."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ENTITY_ALIASES = {
    "org-kitsaki": ("kitsaki management",),
    "org-des-nedhe": ("des nedhe",),
    "org-kemc": ("kahkewistahaw economic management", "kahkewistahaw management"),
    "org-waterhen-development": ("waterhen lake first nation development",),
    "org-piapot-development": ("piapot development", "piapot urban development"),
    "org-fcdc": ("fort a la corne",),
    "org-whitebear-development": ("white bear nations development",),
    "org-pbgoc": ("peter ballantyne group of companies",),
    "org-fhq-developments": ("fhq developments", "fhq development", "fhqtc developments"),
    "org-pafnbd": ("prince albert first nations business development", "pafnbd"),
    "biz-tron": ("tron construction and mining",),
    "biz-morsky": ("morsky industrial services",),
}


def normalized(value: str) -> str:
    value = value.lower().replace("&", "and")
    value = re.sub(r"[•\u2022\uf0b7\"]", " ", value)
    value = re.sub(r"\([^)]*(?:note|interest)[^)]*\)", " ", value)
    value = re.sub(r"\b(?:limited partnership|l\.?p\.?|incorporated|inc\.?|limited|ltd\.?|corporation|corp\.?)\b", " ", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def matches_alias(label: str, aliases: tuple[str, ...]) -> bool:
    candidate = normalized(label)
    return any(normalized(alias) in candidate for alias in aliases)


def source_lookup(enterprise: dict) -> dict[str, dict]:
    return {row["id"]: row for row in enterprise.get("sources", [])}


def public_sources(source_ids: list[str], sources: dict[str, dict]) -> list[dict]:
    rows = []
    for source_id in source_ids:
        source = sources.get(source_id)
        if source and source.get("url"):
            rows.append({
                "name": source.get("publisher") or source.get("title") or "Public source",
                "title": source.get("title"),
                "url": source["url"],
                "publishedAt": source.get("publicationDate"),
                "checkedAt": source.get("lastVerified"),
            })
    return rows


def build_partnerships(leads: list[dict], enterprise: dict, map_data: dict) -> list[dict]:
    organizations = {row["id"]: row for row in enterprise.get("organizations", [])}
    businesses = {row["id"]: row for row in enterprise.get("businesses", [])}
    sources = source_lookup(enterprise)
    candidates: dict[tuple[str, str], dict] = {}

    for relation in enterprise.get("organizationRelationships", []):
        if relation.get("parentType") != "firstNation" or relation.get("verificationStatus") not in {"Verified", "Publicly reported"}:
            continue
        band_id = re.sub(r"^band-", "", str(relation.get("parentId", "")))
        entity_id = relation.get("childId")
        candidates[(band_id, entity_id)] = {
            "relationship": relation.get("relationshipType"),
            "ownershipPercentage": relation.get("ownershipPercentage"),
            "sourceIds": relation.get("sourceIds", []),
        }
        for business in businesses.values():
            if business.get("parentOrganizationId") == entity_id and business.get("verificationStatus") in {"Verified", "Publicly reported"}:
                candidates[(band_id, business["id"])] = {
                    "relationship": "operating business of the community's verified economic organization",
                    "ownershipPercentage": None,
                    "sourceIds": business.get("sourceIds", []),
                }

    council_by_band = {str(row["id"]): row.get("tribalCouncil") for row in map_data.get("communities", [])}
    for relation in enterprise.get("tribalCouncilOrganizations", []):
        if relation.get("verificationStatus") not in {"Verified", "Publicly reported"}:
            continue
        for band_id, council in council_by_band.items():
            if council != relation.get("tribalCouncil"):
                continue
            for entity_id in relation.get("organizationIds", []):
                candidates[(band_id, entity_id)] = {
                    "relationship": relation.get("relationshipType"),
                    "ownershipPercentage": None,
                    "sourceIds": relation.get("sourceIds", []),
                }

    grouped: dict[tuple[str, str], list[dict]] = {}
    for lead in leads:
        band_id = str(lead.get("firstNationIds", [""])[0])
        for (candidate_band, entity_id), relationship in candidates.items():
            aliases = ENTITY_ALIASES.get(entity_id, ())
            if band_id == candidate_band and aliases and matches_alias(lead.get("originalLabel", ""), aliases):
                grouped.setdefault((band_id, entity_id), []).append(lead)

    output = []
    for (band_id, entity_id), matched in grouped.items():
        matched.sort(key=lambda row: row.get("fiscalYear", ""), reverse=True)
        latest = matched[0]
        entity = organizations.get(entity_id) or businesses.get(entity_id)
        relationship = candidates[(band_id, entity_id)]
        corroboration = public_sources(
            list(dict.fromkeys([*relationship.get("sourceIds", []), *entity.get("sourceIds", [])])), sources
        )
        if not entity or not corroboration:
            continue
        audit_source = latest.get("sourceDocument", {})
        output.append({
            "id": f"audit-partnership-{band_id}-{entity_id}",
            "firstNationIds": [band_id],
            "name": entity["name"],
            "entityType": entity.get("organizationType") or "Business or partnership",
            "description": entity.get("description") or entity.get("mandate") or "A source-verified economic organization or business.",
            "relationship": relationship.get("relationship"),
            "ownershipPercentage": relationship.get("ownershipPercentage"),
            "latestAuditDisclosure": {
                "fiscalYear": latest.get("fiscalYear"),
                "originalLabel": latest.get("originalLabel"),
                "reportedAmount": latest.get("currentYearAmount"),
                "sourceUrl": audit_source.get("url"),
                "sourceReferences": latest.get("sourceReferences", []),
            },
            "auditYears": sorted({row.get("fiscalYear") for row in matched if row.get("fiscalYear")}, reverse=True),
            "sources": corroboration,
            "lastVerifiedAt": max((row.get("checkedAt") or row.get("publishedAt") or "" for row in corroboration), default=date.today().isoformat()),
            "verificationStatus": "Public source corroborated",
        })
    return sorted(output, key=lambda row: (row["firstNationIds"][0], row["name"]))


def main() -> None:
    projects_path = ROOT / "projects-data.json"
    projects = json.loads(projects_path.read_text(encoding="utf-8"))
    research = json.loads((ROOT / "project-research-leads.json").read_text(encoding="utf-8"))
    enterprise = json.loads((ROOT / "community-enterprise.json").read_text(encoding="utf-8"))
    map_data = json.loads((ROOT / "map-data.json").read_text(encoding="utf-8"))
    rows = build_partnerships(research.get("auditResearchLeads", []), enterprise, map_data)
    projects["verifiedPartnerships"] = rows
    projects["partnershipAudit"] = {
        "description": "Audit disclosures shown here are independently corroborated by reviewed public organization or business sources.",
        "generatedAt": date.today().isoformat(),
        "records": len(rows),
    }
    projects_path.write_text(json.dumps(projects, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Built {len(rows)} source-corroborated partnership records")


if __name__ == "__main__":
    main()
