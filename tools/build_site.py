"""Generate OpenBand's GitHub Pages routes and search-engine metadata."""

from __future__ import annotations

import html
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://openband.ca"
PROVINCIAL_TOTAL = 74


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower().replace("&", " and ").replace("'", "").replace("’", "")
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", value))


def nation_initials(name: str) -> str:
    ignored = {"first", "nation", "nations", "cree", "dene", "denesuline", "indian", "band"}
    words = re.findall(r"[A-Za-z0-9]+", name or "")
    chosen = [word for word in words if word.lower() not in ignored] or words
    return "".join(word[0] for word in chosen[:2]).upper() or "FN"


def nation_logo_markup(band: dict, size: str = "small", *, eager: bool = False) -> str:
    name = str(band.get("name") or "First Nation")
    verified = bool(band.get("logo_verified") and band.get("logo_url"))
    label = f"{name} official logo" if verified else f"{name} logo unverified; OpenBand placeholder"
    content = f'<span class="fn-logo-initials" aria-hidden="true">{html.escape(nation_initials(name))}</span>'
    if verified:
        loading = "eager" if eager else "lazy"
        priority = ' fetchpriority="high"' if eager else ""
        content = f'<img src="{html.escape(str(band["logo_url"]), quote=True)}" alt="" loading="{loading}" decoding="async"{priority}>'
    state = "" if verified else " fn-logo-unverified"
    return (
        f'<span class="fn-logo fn-logo-{html.escape(size)}{state}" role="img" aria-label="{html.escape(label, quote=True)}">'
        f'{content}</span>'
    )


def remuneration_filings(band: dict) -> list[dict]:
    rows = [
        filing
        for filing in band.get("filings", [])
        if "remuneration" in str(filing.get("docType", "")).lower()
    ]
    return sorted(rows, key=lambda item: str(item.get("year", "")), reverse=True)


def is_parsed(filing: dict) -> bool:
    return bool(filing.get("people")) and not str(filing.get("parse_status", "")).startswith("manual_review")


def set_meta(source: str, *, title: str, description: str, path: str, structured: dict) -> str:
    canonical = f"{ORIGIN}{path}"
    replacements = {
        r"<title>.*?</title>": f"<title>{html.escape(title)}</title>",
        r'<meta name="description" content="[^"]*">': f'<meta name="description" content="{html.escape(description, quote=True)}">',
        r'<link rel="canonical" href="[^"]*">': f'<link rel="canonical" href="{canonical}">',
        r'<meta property="og:title" content="[^"]*">': f'<meta property="og:title" content="{html.escape(title, quote=True)}">',
        r'<meta property="og:description" content="[^"]*">': f'<meta property="og:description" content="{html.escape(description, quote=True)}">',
        r'<meta property="og:url" content="[^"]*">': f'<meta property="og:url" content="{canonical}">',
        r'<meta name="twitter:title" content="[^"]*">': f'<meta name="twitter:title" content="{html.escape(title, quote=True)}">',
        r'<meta name="twitter:description" content="[^"]*">': f'<meta name="twitter:description" content="{html.escape(description, quote=True)}">',
        r'<script type="application/ld\+json">.*?</script>': '<script type="application/ld+json">' + json.dumps(structured, ensure_ascii=False, separators=(",", ":")) + "</script>",
    }
    for pattern, replacement in replacements.items():
        source, count = re.subn(pattern, replacement, source, count=1, flags=re.DOTALL)
        if count != 1:
            raise RuntimeError(f"Could not replace metadata pattern: {pattern}")
    return source


def election_prerender(band: dict, records: list[dict]) -> str:
    winners = [
        record for record in records
        if str(record.get("firstNationId")) == str(band["id"]) and record.get("elected") and record.get("electionDate")
    ]
    if not winners:
        return ""
    latest_date = max(str(record["electionDate"]) for record in winners)
    winners = [record for record in winners if str(record["electionDate"]) == latest_date]
    source_url = winners[0].get("sourceUrl", "")
    source_name = winners[0].get("sourceName", "Election results")
    def list_for(position: str) -> str:
        rows = [record for record in winners if record.get("position", "").lower() == position]
        return "".join(
            f'<li><strong>{html.escape(record["candidateName"])}</strong>'
            f'<span>{html.escape(str(record["votesReceived"]))} votes</span></li>'
            if record.get("votesReceived") is not None else f'<li><strong>{html.escape(record["candidateName"])}</strong></li>'
            for record in rows
        )
    chief, councillors = list_for("chief"), list_for("councillor")
    date_label = latest_date
    parts = []
    if chief:
        parts.append(f"<div><h4>Chief</h4><ul>{chief}</ul></div>")
    if councillors:
        parts.append(f"<div><h4>Councillors</h4><ul>{councillors}</ul></div>")
    return (
        '<section class="election-card"><div class="election-heading"><div>'
        f'<h3>Elections &amp; Leadership</h3><p>Latest election — {html.escape(date_label)}</p></div>'
        f'<a href="{html.escape(source_url, quote=True)}" rel="noopener">{html.escape(source_name)} results</a></div>'
        f'<div class="election-results">{"".join(parts)}</div>'
        f'<div class="election-source"><strong>Source:</strong> <a href="{html.escape(source_url, quote=True)}" rel="noopener">{html.escape(source_name)}</a></div></section>'
    )


def projects_prerender(
    band: dict,
    projects: list[dict],
    financial_disclosures: list[dict],
    unverified_projects: list[dict],
) -> str:
    priority = {"Under Construction": 0, "Planned": 1, "Completed": 2}
    rows = [
        project for project in projects
        if str(band["id"]) in {str(value) for value in project.get("firstNationIds", [])}
    ]
    rows.sort(key=lambda project: str(project.get("name") or ""))
    rows.sort(key=lambda project: str(project.get("statusAsOf") or ""), reverse=True)
    rows.sort(key=lambda project: priority.get(project.get("status"), 3))
    cards = []
    for project in rows[:3]:
        sources = "".join(
            f'<a href="{html.escape(source["url"], quote=True)}" rel="noopener">'
            f'{html.escape(source.get("name") or "Original source")}</a>'
            for source in project.get("sources", []) if source.get("url")
        )
        status = project.get("status")
        status_class = re.sub(r"[^a-z0-9]+", "-", str(status or "").lower()).strip("-")
        status_html = (
            f'<span class="project-status status-{status_class}">{html.escape(status)}</span>'
            if status else ""
        )
        cards.append(
            '<article class="project-row"><div class="project-row-top">'
            f'<span class="project-category">{html.escape(project.get("category") or "Community Project")}</span>'
            f'{status_html}</div><h4>{html.escape(project["name"])}</h4>'
            f'<p>{html.escape(project.get("description") or "")}</p>'
            f'<div class="project-sources"><strong>Source:</strong>{sources}</div></article>'
        )
    content = (
        f'<div class="project-list">{"".join(cards)}</div>'
        if cards else
        '<div class="projects-empty">No current or recently completed project has been added from a verifiable public source yet.</div>'
    )
    disclosures = [
        project for project in financial_disclosures
        if str(band["id"]) in {str(value) for value in project.get("firstNationIds", [])}
    ]
    disclosures.sort(key=lambda project: (str(project.get("fiscalYear") or ""), project.get("name") or ""), reverse=True)
    disclosure_cards = []
    for project in disclosures[:4]:
        source = next((item for item in project.get("sources", []) if item.get("url")), None)
        references = " · ".join(
            f'PDF page {reference.get("pdfPage")} · {reference.get("table")}'
            for reference in project.get("sourceReferences", [])
        )
        source_html = (
            f'<a href="{html.escape(source["url"], quote=True)}" rel="noopener">'
            f'{html.escape(references or source.get("name") or "Audited statement")}</a>'
            if source else ""
        )
        disclosure_cards.append(
            '<article class="project-row audited-project-row"><div class="project-row-top">'
            f'<span class="project-category">{html.escape(project.get("category") or "Community Project")}</span>'
            '<span class="audited-disclosure-label">Audited disclosure</span></div>'
            f'<h4>{html.escape(project["name"])}</h4><p>{html.escape(project.get("description") or "")}</p>'
            '<p class="project-disclosure-note">Financial disclosure only. OpenBand does not infer construction status, total project cost, approval, or completion.</p>'
            f'<div class="project-sources"><strong>{html.escape(project.get("fiscalYear") or "Audited year")}:</strong>{source_html}</div></article>'
        )
    disclosure_section = (
        '<section class="financial-projects"><div class="unverified-heading"><div>'
        '<h3>Projects Named in Audited Statements</h3>'
        '<p>Project names and financial amounts explicitly reported in audited notes or schedules.</p></div>'
        f'<span class="project-count">{len(disclosures)} disclosures</span></div>'
        '<div class="audited-project-warning"><strong>Evidence level:</strong> These records confirm a financial-statement disclosure, not current construction status.</div>'
        f'<div class="project-list">{"".join(disclosure_cards)}</div></section>'
        if disclosures else ""
    )
    unverified = [
        project for project in unverified_projects
        if str(band["id"]) in {str(value) for value in project.get("firstNationIds", [])}
    ]
    unverified.sort(key=lambda project: str(project.get("lastSeenAt") or ""), reverse=True)
    unverified_cards = []
    for project in unverified[:3]:
        source = next((item for item in project.get("sources", []) if item.get("url")), None)
        source_html = (
            f'<a href="{html.escape(source["url"], quote=True)}" rel="noopener">'
            f'{html.escape(source.get("name") or "Original public source")}</a>'
            if source else ""
        )
        unverified_cards.append(
            '<article class="unverified-project-row"><div class="project-row-top">'
            f'<span class="project-category">{html.escape(project.get("category") or "Community Project")}</span>'
            '<span class="unverified-label">Unverified</span></div>'
            f'<h4>{html.escape(project["name"])}</h4><p>{html.escape(project.get("discussionSummary") or "")}</p>'
            f'<p class="unverified-reason"><strong>Why unverified:</strong> {html.escape(project.get("whyUnverified") or "")}</p>'
            f'<div class="project-sources"><strong>Public signal:</strong>{source_html}</div></article>'
        )
    unverified_content = (
        f'<div class="unverified-project-list">{"".join(unverified_cards)}</div>'
        if unverified_cards else
        '<div class="unverified-empty">No source-linked unverified project discussion was indexed in the current public-source scan.</div>'
    )
    unverified_section = (
        '<section class="unverified-projects"><div class="unverified-heading"><div>'
        '<h3>Unverified Projects &amp; Community Discussion</h3>'
        '<p>Source-linked proposals or discussion that are not confirmed projects.</p></div></div>'
        '<div class="unverified-warning"><strong>Not confirmed:</strong> Inclusion here does not mean funding, approval, construction or delivery is secured.</div>'
        f'{unverified_content}</section>'
    )
    return (
        '<section class="profile-projects" aria-labelledby="projectsPrerenderHeading">'
        '<div class="section-head"><div><h3 id="projectsPrerenderHeading">Community Projects</h3>'
        '<p>Housing, infrastructure, facilities, environmental work and other developments found in public sources and audited statements.</p></div></div>'
        f'{content}{disclosure_section}{unverified_section}</section>'
    )


def jobs_for_band(band: dict, listings: list[dict]) -> list[dict]:
    public_statuses = {"Open", "Closing soon", "Date unavailable"}
    rows = [
        row for row in listings
        if (
            str(row.get("communityId")) == str(band["id"])
            or str(band["id"]) in {str(value) for value in row.get("firstNationIds", [])}
        )
        and row.get("status") in public_statuses
        and row.get("verifiedOfficialSource")
        and row.get("sourceUrl")
    ]
    return sorted(rows, key=lambda row: (str(row.get("postedDate") or row.get("lastChecked") or ""), row.get("title") or ""), reverse=True)


def jobs_prerender(band: dict, listings: list[dict]) -> str:
    rows = jobs_for_band(band, listings)
    if not rows:
        return (
            '<section class="profile-jobs-prerender"><h3>Jobs &amp; Employment</h3>'
            '<p>No current opportunities have been indexed from public sources.</p></section>'
        )
    items = "".join(
        '<li>'
        f'<a href="{html.escape(row["sourceUrl"], quote=True)}">{html.escape(row["title"])}</a>'
        f'<span>{html.escape(row.get("employer") or "Employer")} · '
        f'{html.escape(row.get("location") or "Location not published")}</span></li>'
        for row in rows[:6]
    )
    return (
        '<section class="profile-jobs-prerender"><h3>Jobs &amp; Employment</h3>'
        f'<p>{len(rows)} source-linked opportunit{"y" if len(rows) == 1 else "ies"} currently indexed.</p>'
        f'<ul>{items}</ul></section>'
    )


def job_posting_schema(band: dict, listings: list[dict]) -> list[dict]:
    schemas = []
    for row in jobs_for_band(band, listings):
        if row.get("status") not in {"Open", "Closing soon"}:
            continue
        if not all(row.get(field) for field in ("title", "description", "employer", "postedDate", "location")):
            continue
        location = str(row["location"]).split(",", 1)[0].strip()
        schema = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": row["title"],
            "description": row["description"],
            "datePosted": row["postedDate"],
            "employmentType": row.get("employmentType") or "OTHER",
            "hiringOrganization": {"@type": "Organization", "name": row["employer"]},
            "jobLocation": {
                "@type": "Place",
                "address": {"@type": "PostalAddress", "addressLocality": location, "addressRegion": "SK", "addressCountry": "CA"},
            },
            "url": row.get("applicationUrl") or row["sourceUrl"],
        }
        if row.get("closingDate"):
            schema["validThrough"] = f'{row["closingDate"]}T23:59:59-06:00'
        schemas.append(schema)
    return schemas


def profile_prerender(
    band: dict,
    election_records: list[dict],
    projects: list[dict],
    financial_disclosures: list[dict],
    unverified_projects: list[dict],
    jobs: list[dict],
) -> str:
    filings = remuneration_filings(band)
    parsed = [filing for filing in filings if is_parsed(filing)]
    latest = filings[0].get("year") if filings else None
    latest_parsed = parsed[0].get("year") if parsed else None
    isc_url = (
        "https://fnp-ppn.aadnc-aandc.gc.ca/fnp/Main/Search/"
        f"FederalFundingMain.aspx?BAND_NUMBER={quote(str(band['id']))}&amp;lang=eng"
    )
    return (
        f'<div id="profilePrerender" class="profile-prerender">'
        f'<div class="profile-prerender-title"><h1>{html.escape(band["name"])} Financial Records</h1>{nation_logo_markup(band, "profile", eager=True)}</div>'
        "<p>Public FNFTA filing availability, parsed Chief and Council remuneration, "
        "audited financial statements, and original Indigenous Services Canada source documents.</p>"
        "<dl>"
        f"<div><dt>Latest fiscal year listed</dt><dd>{html.escape(latest or 'Not available')}</dd></div>"
        f"<div><dt>Latest parsed remuneration</dt><dd>{html.escape(latest_parsed or 'Pending extraction')}</dd></div>"
        f"<div><dt>Parsed years</dt><dd>{len(parsed)}</dd></div>"
        f'<div><dt>Authoritative source</dt><dd><a href="{isc_url}">ISC filing profile</a></dd></div>'
        f"</dl>{election_prerender(band, election_records)}"
        f"{projects_prerender(band, projects, financial_disclosures, unverified_projects)}"
        f"{jobs_prerender(band, jobs)}</div>"
    )


def directory_prerender(bands: list[dict], map_communities: list[dict]) -> str:
    map_by_id = {str(row.get("id")): row for row in map_communities}
    links = "".join(
        f'<a class="directory-community" href="/first-nations/{slugify(band["name"])}/">'
        f'<span class="directory-community-main">{nation_logo_markup(band, "medium")}<span><strong>{html.escape(band["name"])}</strong>'
        f"<small>{html.escape(band.get('treaty') or 'Treaty not listed')} · "
        f"{html.escape(map_by_id.get(str(band.get('id')), {}).get('tribalCouncil') or 'No council affiliation listed in current sources')}</small></span></span></a>"
        for band in sorted(bands, key=lambda item: item["name"])
    )
    return f'<div id="directoryList" class="directory-list static-directory-list">{links}</div>'


def news_prerender(articles: list[dict]) -> str:
    cards = []
    for article in sorted(articles, key=lambda item: str(item.get("publishedAt", "")), reverse=True)[:12]:
        if not article.get("title") or not article.get("url"):
            continue
        cards.append(
            '<article class="news-card"><div class="news-card-body">'
            f'<div class="news-meta">{html.escape(article.get("communityName") or "Saskatchewan First Nations")} · '
            f'{html.escape(article.get("sourceName") or article.get("publication") or "Source")} · '
            f'{html.escape(article.get("publishedAt") or "Undated")}</div>'
            f'<h2>{html.escape(article["title"])}</h2>'
            f'<p>{html.escape(article.get("summary") or "")}</p>'
            f'<a class="small-btn" href="{html.escape(article["url"], quote=True)}" rel="noopener">Original source</a>'
            "</div></article>"
        )
    return f'<div class="news-grid" id="newsGrid">{"".join(cards)}</div>'


def enterprise_prerender(band: dict, enterprise: dict, map_communities: list[dict]) -> str:
    profile = next(
        (row for row in enterprise.get("nationProfiles", []) if str(row.get("bandId")) == str(band.get("id"))),
        None,
    )
    organizations_by_id = {row["id"]: row for row in enterprise.get("organizations", [])}
    primary = organizations_by_id.get(profile.get("primaryOrganizationId")) if profile else None
    community = next(
        (row for row in map_communities if str(row.get("id")) == str(band.get("id"))),
        {},
    )
    council_mapping = next(
        (
            row for row in enterprise.get("tribalCouncilOrganizations", [])
            if row.get("tribalCouncil") == community.get("tribalCouncil")
        ),
        None,
    )
    collective = [
        organizations_by_id[organization_id]
        for organization_id in (council_mapping or {}).get("organizationIds", [])
        if organization_id in organizations_by_id
    ]
    organizations = []
    for organization in [primary, *collective]:
        if organization and organization["id"] not in {row["id"] for row in organizations}:
            organizations.append(organization)

    back = f"/first-nations/{slugify(band['name'])}/"
    if not organizations:
        return (
            '<section id="enterprisePage" class="enterprise-page static-enterprise-page">'
            '<div class="enterprise-page-head">'
            f'<a href="{back}">Back to {html.escape(band["name"])}</a>'
            '<span class="enterprise-kicker">Community Enterprise</span>'
            f'<h1>{html.escape(band["name"])}</h1>'
            '<p>Publicly reported organizations, ownership interests, businesses and projects connected to this First Nation.</p>'
            '</div><section class="enterprise-section enterprise-empty-state">'
            '<h2>Enterprise data not yet verified</h2>'
            '<p>Missing information is not treated as zero or as evidence that no enterprise activity exists.</p>'
            '</section></section>'
        )

    organization = primary or organizations[0]
    relationship = next(
        (
            row for row in enterprise.get("organizationRelationships", [])
            if row.get("parentId") == f'band-{band["id"]}' and row.get("childId") == organization["id"]
        ),
        None,
    )
    relationship_label = (
        (relationship or {}).get("relationshipType")
        or (council_mapping or {}).get("relationshipType")
        or "Publicly reported relationship"
    )
    interests = [
        row for row in enterprise.get("ownershipInterests", [])
        if profile and row.get("ownerId") == profile.get("primaryOrganizationId")
    ]
    industries = "".join(
        f'<span>{html.escape(value)}</span>' for value in (profile or {}).get("industries", [])[:4]
    )
    website = organization.get("website")
    website_link = (
        f'<a class="small-btn" href="{html.escape(website, quote=True)}" target="_blank" rel="noopener">Official website</a>'
        if website else ""
    )
    related_cards = "".join(
        '<article class="enterprise-affiliation-card"><div>'
        f'<span>{"Collective organization" if row.get("scope") == "Tribal council" else "Nation organization"}</span>'
        f'<strong>{html.escape(row["name"])}</strong>'
        f'<small>{html.escape(row.get("organizationType") or "")}</small></div>'
        + (
            f'<a href="{html.escape(row["website"], quote=True)}" target="_blank" rel="noopener">Official website</a>'
            if row.get("website") else ""
        )
        + '</article>'
        for row in organizations
    )
    return (
        '<section id="enterprisePage" class="enterprise-page static-enterprise-page">'
        '<div class="enterprise-page-head">'
        f'<a href="{back}">Back to {html.escape(band["name"])}</a>'
        '<span class="enterprise-kicker">Community Enterprise</span>'
        f'<h1>{html.escape(band["name"])}</h1>'
        '<p>Publicly reported organizations, ownership interests, businesses and projects connected to this First Nation.</p>'
        f'<div class="enterprise-tags">{industries}</div>'
        '</div><section class="enterprise-section enterprise-hero-summary"><div>'
        f'<h2>{html.escape(organization["name"])}</h2>'
        f'<p>{html.escape(organization.get("description") or "")}</p>'
        f'<p>{len(interests)} known businesses and investments. '
        f'Relationship: {html.escape(relationship_label)}.</p>'
        f'</div><div>{website_link}</div></section>'
        '<section class="enterprise-section"><div class="section-head"><div>'
        '<h2>Economic Organizations</h2>'
        '<p>Nation-specific and tribal-council organizations are kept distinct.</p>'
        f'</div></div><div class="enterprise-affiliation-list">{related_cards}</div></section></section>'
    )

def write_page(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def legacy_enterprise_redirect(band: dict) -> str:
    target = f"/first-nations/{slugify(band['name'])}/?tab=capital"
    title = f"{band['name']} Community Capital | OpenBand"
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="robots" content="noindex,follow">'
        f'<title>{html.escape(title)}</title>'
        f'<link rel="canonical" href="{ORIGIN}{target}">'
        f'<meta http-equiv="refresh" content="0; url={html.escape(target, quote=True)}">'
        f'<script>location.replace({json.dumps(target)});</script></head><body>'
        f'<p>Community enterprise is now included within the main public-records profile. '
        f'<a href="{html.escape(target, quote=True)}">Continue to {html.escape(band["name"])}</a>.</p>'
        '<footer>&copy; <span data-current-year>2026</span> OpenBand. All rights reserved. A product of SevenGenStudios.</footer>'
        '<script>document.querySelector("[data-current-year]").textContent=new Date().getFullYear();</script>'
        '</body></html>'
    )


def build() -> None:
    data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
    news = json.loads((ROOT / "news-data.json").read_text(encoding="utf-8"))
    elections = json.loads((ROOT / "elections-data.json").read_text(encoding="utf-8"))
    map_data = json.loads((ROOT / "map-data.json").read_text(encoding="utf-8"))
    projects = json.loads((ROOT / "projects-data.json").read_text(encoding="utf-8"))
    jobs = json.loads((ROOT / "jobs-data.json").read_text(encoding="utf-8"))
    bands = sorted(data.get("bands", []), key=lambda item: item["name"])
    base = (ROOT / "index.html").read_text(encoding="utf-8")
    slugs = [slugify(band["name"]) for band in bands]
    if len(slugs) != len(set(slugs)):
        raise RuntimeError("Community slugs are not unique")

    # Profile directories may be published through sync providers that disallow
    # deleting the root directory. Rewriting each generated route is sufficient
    # and keeps the build safe to run in those workspaces.
    profile_root = ROOT / "first-nations"
    profile_root.mkdir(parents=True, exist_ok=True)

    for band in bands:
        slug = slugify(band["name"])
        path = f"/first-nations/{slug}/"
        title = f"{band['name']} Financial Records | OpenBand"
        description = (
            f"Review {band['name']} public FNFTA filing availability, parsed Chief and Council "
            "remuneration, audited statements, and original ISC source documents."
        )
        structured = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": title,
            "url": f"{ORIGIN}{path}",
            "description": description,
            "isPartOf": {"@type": "WebSite", "name": "OpenBand", "url": f"{ORIGIN}/"},
            "about": {"@type": "Organization", "name": band["name"]},
        }
        if band.get("logo_verified") and band.get("logo_url"):
            structured["about"]["logo"] = f'{ORIGIN}{band["logo_url"]}'
        page = set_meta(base, title=title, description=description, path=path, structured=structured)
        page = page.replace('<body data-page="home">', f'<body data-page="profile" data-band-id="{band["id"]}">', 1)
        page = page.replace(
            '<div id="profilePrerender" class="profile-prerender" hidden></div>',
            profile_prerender(
                band,
                elections.get("records", []),
                projects.get("projects", []),
                projects.get("financialDisclosures", []),
                projects.get("unverifiedProjects", []),
                jobs.get("listings", []),
            ),
            1,
        )
        job_schemas = job_posting_schema(band, jobs.get("listings", []))
        if job_schemas:
            page = page.replace("</head>", '<script type="application/ld+json" id="openbandJobPostingData">' + json.dumps({"@context": "https://schema.org", "@graph": job_schemas}, ensure_ascii=False, separators=(",", ":")) + "</script></head>", 1)
        page = page.replace(
            '<script src="/assets/openband.js?v=20260903b" defer></script>',
            f'<script>window.OPENBAND_BOOT={{"page":"profile","bandId":"{band["id"]}","slug":"{slug}"}};</script><script src="/assets/openband.js?v=20260903b" defer></script>',
            1,
        )
        write_page(profile_root / slug / "index.html", page)

        write_page(
            profile_root / slug / "community-enterprise" / "index.html",
            legacy_enterprise_redirect(band),
        )

    directory_title = "Explore Saskatchewan First Nations | OpenBand"
    directory_description = "Explore Saskatchewan First Nations on an interactive map with red First Nation and reserve land boundaries, organized by Treaty and tribal-council affiliation."
    directory = set_meta(
        base,
        title=directory_title,
        description=directory_description,
        path="/browse/",
        structured={
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": directory_title,
            "url": f"{ORIGIN}/browse/",
            "numberOfItems": len(bands),
        },
    ).replace('<body data-page="home">', '<body data-page="directory">', 1)
    directory = directory.replace('<div id="directoryList" class="directory-list"></div>', directory_prerender(bands, map_data.get("communities", [])), 1)
    write_page(ROOT / "browse" / "index.html", directory)

    news_title = "Saskatchewan First Nations News | OpenBand"
    news_description = "Recent public updates connected to Saskatchewan First Nations from original community, organization, government, and news sources."
    news_page = set_meta(
        base,
        title=news_title,
        description=news_description,
        path="/news/",
        structured={
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": news_title,
            "url": f"{ORIGIN}/news/",
            "description": news_description,
        },
    ).replace('<body data-page="home">', '<body data-page="news">', 1)
    news_page = news_page.replace('<div class="news-grid" id="newsGrid"></div>', news_prerender(news.get("articles", [])), 1)
    write_page(ROOT / "news" / "index.html", news_page)

    lastmod = str(data.get("generated") or "")[:10]
    paths = ["/", "/browse/", "/news/"] + [f"/first-nations/{slug}/" for slug in slugs]
    urls = "".join(
        f"<url><loc>{ORIGIN}{path}</loc>{f'<lastmod>{lastmod}</lastmod>' if lastmod else ''}</url>"
        for path in paths
    )
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{urls}</urlset>\n",
        encoding="utf-8",
    )
    (ROOT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nDisallow: /admin/\nSitemap: {ORIGIN}/sitemap.xml\n", encoding="utf-8"
    )
    (ROOT / ".nojekyll").touch()
    print(f"Generated {len(bands)} profile pages, legacy redirects, browse, news, robots.txt, and sitemap.xml")


if __name__ == "__main__":
    build()
