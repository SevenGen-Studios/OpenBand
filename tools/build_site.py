"""Generate OpenBand's GitHub Pages routes and search-engine metadata."""

from __future__ import annotations

import html
import json
import re
import shutil
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


def profile_prerender(band: dict) -> str:
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
        f"<h1>{html.escape(band['name'])} Financial Records</h1>"
        "<p>Public FNFTA filing availability, parsed Chief and Council remuneration, "
        "audited financial statements, and original Indigenous Services Canada source documents.</p>"
        "<dl>"
        f"<div><dt>Latest fiscal year listed</dt><dd>{html.escape(latest or 'Not available')}</dd></div>"
        f"<div><dt>Latest parsed remuneration</dt><dd>{html.escape(latest_parsed or 'Pending extraction')}</dd></div>"
        f"<div><dt>Parsed years</dt><dd>{len(parsed)}</dd></div>"
        f'<div><dt>Authoritative source</dt><dd><a href="{isc_url}">ISC filing profile</a></dd></div>'
        "</dl></div>"
    )


def directory_prerender(bands: list[dict]) -> str:
    links = "".join(
        f'<a class="directory-community" href="/first-nations/{slugify(band["name"])}/">'
        f"<span><strong>{html.escape(band['name'])}</strong>"
        f"<small>{html.escape(band.get('treaty') or 'Treaty not listed')}</small></span></a>"
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


def write_page(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build() -> None:
    data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
    news = json.loads((ROOT / "news-data.json").read_text(encoding="utf-8"))
    bands = sorted(data.get("bands", []), key=lambda item: item["name"])
    base = (ROOT / "index.html").read_text(encoding="utf-8")
    slugs = [slugify(band["name"]) for band in bands]
    if len(slugs) != len(set(slugs)):
        raise RuntimeError("Community slugs are not unique")

    profile_root = ROOT / "first-nations"
    if profile_root.exists():
        shutil.rmtree(profile_root)

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
        page = set_meta(base, title=title, description=description, path=path, structured=structured)
        page = page.replace('<body data-page="home">', f'<body data-page="profile" data-band-id="{band["id"]}">', 1)
        page = page.replace('<div id="profilePrerender" class="profile-prerender" hidden></div>', profile_prerender(band), 1)
        page = page.replace(
            '<script src="/assets/openband.js?v=20260801d" defer></script>',
            f'<script>window.OPENBAND_BOOT={{"page":"profile","bandId":"{band["id"]}","slug":"{slug}"}};</script><script src="/assets/openband.js?v=20260801d" defer></script>',
            1,
        )
        write_page(profile_root / slug / "index.html", page)

    directory_title = "Browse Saskatchewan First Nations | OpenBand"
    directory_description = "Browse Saskatchewan First Nations public financial record profiles by name, Treaty, filing status, and Community Capital availability."
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
    directory = directory.replace('<div id="directoryList" class="directory-list"></div>', directory_prerender(bands), 1)
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
        f"User-agent: *\nAllow: /\nSitemap: {ORIGIN}/sitemap.xml\n", encoding="utf-8"
    )
    (ROOT / ".nojekyll").touch()
    print(f"Generated {len(bands)} profile pages, browse, news, robots.txt, and sitemap.xml")


if __name__ == "__main__":
    build()
