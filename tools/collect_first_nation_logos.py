"""Collect, verify, and optimize First Nation logos from official websites.

The collector deliberately accepts only logo-like assets published by an
official Nation or an explicitly recorded authoritative partner.  It never
promotes generic page photography, flags, or search-engine thumbnails.
Every database Nation receives a record in ``first-nation-logos.json``; a
record stays unverified when no suitably attributable mark can be found.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import ssl
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from PIL import Image, ImageOps, UnidentifiedImageError


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "public" / "first-nation-logos"
REGISTRY_PATH = ROOT / "first-nation-logos.json"
USER_AGENT = "Mozilla/5.0 (compatible; OpenBandLogoResearch/1.0; +https://openband.ca/)"
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
MAX_EDGE = 512

# Sites located during the 2026-08-12 web verification pass.  Entries here are
# official Nation sites unless the source kind explicitly says otherwise.
DISCOVERED_SITES = {
    "404": ("https://www.bigriverfirstnation.ca/", "Official First Nation website"),
    "369": ("https://bocn.ca/", "Official First Nation website"),
    "403": ("https://www.mltc.net/nations/bndn/", "Official Tribal Council website"),
    "378": ("https://cegakin.org/", "Official First Nation website"),
    "401": ("https://www.crdn.co/", "Official First Nation website"),
    "396": ("https://www.msfn.co/", "Official First Nation website"),
    "397": ("https://www.mltc.net/nations/mlcn/", "Official Tribal Council website"),
    "408": ("https://www.oceanman1990.com/", "Official First Nation website"),
    "382": ("https://www.okanesefirstnation.ca/", "Official First Nation website"),
    "373": ("https://onearrow.ca/", "Official First Nation website"),
    "346": ("https://redpheasantcreenation.ca/", "Official First Nation website"),
    "356": ("https://www.redearthcreenation.ca/", "Official First Nation website"),
    "357": ("https://www.slcn.ca/", "Official First Nation website"),
    "362": ("https://fnpa.ca/project/kahkewistahaw-first-nation/", "First Nations Power Authority partner profile"),
    "405": ("https://www.fncias.ca/about-us/our-member-nations-tribal-councils/", "First Nations Capital and Infrastructure Agency member profile"),
    "387": ("https://www.fncias.ca/about-us/our-member-nations-tribal-councils/", "First Nations Capital and Infrastructure Agency member profile"),
    "360": ("https://slfn.ca/", "Official First Nation website"),
    "358": ("https://pagc.sk.ca/wahpeton-dakota-nation/", "Official Tribal Council website"),
    "402": ("https://www.waterhen.net/", "Official First Nation website"),
    "376": ("https://yqfn.ca/yellow-quill-first-nation/", "Official First Nation website"),
    "345": ("https://poundmakercn.ca/", "Official First Nation website"),
    "352": ("https://www.adeask.ca/apps/pages/index.jsp?pREC_ID=1371397&type=d&uREC_ID=1097930", "Official Athabasca Denesuline Education Authority profile"),
    "365": ("https://fnpa.ca/project/white-bear-first-nations/", "First Nations Power Authority partner profile"),
    "370": ("https://apps.apple.com/ca/app/james-smith-cree-nation/id6747688434", "Official Nation communications app listing"),
    "379": ("https://littleblackbear.ca/", "Official First Nation website"),
    "385": ("https://piapotnation.com/", "Official First Nation website"),
    "392": ("https://www.muskowekwan.com/meetings", "Official First Nation website"),
    "407": ("https://witchekanlake.ca/", "Official First Nation website"),
    "409": ("https://fnpa.ca/project/pheasant-rump-nakota-first-nation/", "First Nations Power Authority partner profile"),
}

# Browser-verified header marks for sites whose anti-bot configuration blocks
# urllib or whose logo is not labelled in the raw HTML.  Both the page and the
# exact asset URL are retained so the attribution remains auditable.
MANUAL_ASSETS = {
    "404": ("https://www.bigriverfirstnation.ca/", "https://www.bigriverfirstnation.ca/wp-content/uploads/2023/01/Picture1.png"),
    "340": ("https://littlepine.ca/", "https://littlepine.ca/wp-content/uploads/2019/11/75640635_403497117261065_6849500598258106368_n-1.png"),
    "381": ("https://muscowpetung.com/", "https://muscowpetung.com/storage/2023/01/Muscowpetung-80-Color.pdf-2-scaled.png"),
    "375": ("https://muskeglake.com/", "https://muskeglake.com/wp-content/uploads/2026/02/MLCN-Logo-605x377.jpg"),
    "382": ("https://www.okanesefirstnation.ca/", "https://static.wixstatic.com/media/82de0a_85fe50d3d31642f68ad5c04fcdcca965~mv2.png"),
    "385": ("https://piapotnation.com/", "https://piapotnation.com/wp-content/uploads/2021/11/cropped-cropped-PFN-Logo-Final-e1637802772994.png"),
    "345": ("https://poundmakercn.ca/", "https://poundmakercn.ca/images/logo.png"),
    "353": ("https://llrib.com/", "https://llrib.com/wp-content/uploads/2021/10/cropped-cropped-llrib-website-icon_02.png"),
    "362": ("https://fnpa.ca/project/kahkewistahaw-first-nation/", "https://i0.wp.com/fnpa.ca/wp-content/uploads/2024/12/kahkewistahan_logo_500.jpg?w=500&ssl=1"),
    "405": ("https://www.fncias.ca/about-us/our-member-nations-tribal-councils/", "https://www.fncias.ca/wp-content/uploads/2024/08/Pelican_Lake-logo.jpg"),
    "386": ("https://www.standingbuffalodakotanation.com/", "https://static.wixstatic.com/media/07d501_fa7dc0b999f548fdb90aa147b20bbdc5~mv2.png/v1/fill/w_236,h_264,al_c,q_85,usm_0.66_1.00_0.01,enc_avif,quality_auto/Standing-Buffalo-Logo--253x300.png"),
    "387": ("https://www.fncias.ca/about-us/our-member-nations-tribal-councils/", "https://www.fncias.ca/wp-content/uploads/2024/08/star-blanket-first-nation-logo.png"),
    "406": ("https://www.ahtahkakoop.ca/", "https://www.ahtahkakoop.ca/uploads/1/4/5/9/145936684/ahtahkakoop-icon_2.png"),
    "398": ("https://www.brdn.ca/", "https://www.brdn.ca/wp-content/uploads/2022/07/buffalo-river-logo-clr.svg"),
    "361": ("https://cowessessfn.com/", "https://cowessessfn.com/wp-content/uploads/2022/05/Cowessess-FN-Logo.png"),
    "390": ("https://www.fishinglakefirstnation.com/", "https://static.wixstatic.com/media/247b6c_84fb2b9feb2048e2bf03b33990fc2bb5~mv2.png/v1/fill/w_131,h_102,al_c,q_85,usm_0.66_1.00_0.01,enc_avif,quality_auto/247b6c_84fb2b9feb2048e2bf03b33990fc2bb5~mv2.png"),
    "351": ("https://www.fonddulac.ca/", "https://www.fonddulac.ca/public/uploads/setting_photo/logo_1.png"),
    "374": ("https://mistawasis.ca/", "https://mistawasis.ca/wp-content/uploads/2023/03/MistawasisLogo2023-sm.png"),
    "344": ("https://onionlake.ca/", "https://onionlake.ca/wp-content/uploads/2025/12/ONION-LAKE-LOGO-2025-scaled.png"),
    "357": ("https://www.slcn.ca/", "https://slcn.ca/wp-content/uploads/2024/06/slcn-logo2.png"),
    "360": ("https://slfn.ca/", "https://slfn.ca/wp-content/uploads/2023/02/Sturgeon-Lake-First-Nation.png"),
    "368": ("https://keyband.com/", "https://keyband.com/wp-content/uploads/2018/10/key-first-nation-logo.png"),
    "388": ("https://www.woodmountainlakotafn.ca/", "https://images.squarespace-cdn.com/content/v1/681a3f1e1023425e48148ac3/a62f6b32-2797-437f-b5b8-55a3c6653716/Untitled+design-Photoroom.png?format=1500w"),
    "365": ("https://fnpa.ca/project/white-bear-first-nations/", "https://i0.wp.com/fnpa.ca/wp-content/uploads/2024/10/whitebear_500.jpg?fit=500%2C500&ssl=1"),
    "370": ("https://apps.apple.com/ca/app/james-smith-cree-nation/id6747688434", "https://is1-ssl.mzstatic.com/image/thumb/Purple221/v4/08/8f/a4/088fa499-5f7b-6a5c-1183-6e16033192c2/AppIcon-0-0-1x_U007emarketing-0-8-0-85-220.png/1200x630wa.png"),
    "392": ("https://www.muskowekwan.com/meetings", "https://images.squarespace-cdn.com/content/v1/618860b2011ecd51f00b8fda/5cefa80a-7314-4c10-b41a-c270e0fc907a/New%2BMuskow%2BLogo.png"),
    "401": ("https://www.crdn.co/", "https://www.crdn.co/images/avion_logo.png"),
    "403": ("https://www.mltc.net/nations/bndn/", "https://mltc.net/wp-content/uploads/2019/12/BNDN.jpg"),
}

# Visually reviewed false positives.  These are intentionally kept unverified:
# the automatic candidate was another organization's mark, a flag, or a photo.
REJECTED_AUTOMATIC_IDS = {
    "397": "The selected asset was the Meadow Lake Tribal Council logo, not the Nation logo.",
}

INLINE_SVG_CLASSES = {
    # English River publishes its official wordmark directly in the page DOM.
    "400": "w-64",
}


def slugify(value: str) -> str:
    value = value.lower().replace("&", " and ").replace("’", "").replace("'", "")
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", value))


def request_bytes(url: str, *, timeout: int = 20) -> tuple[bytes, str, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,image/*;q=0.9,*/*;q=0.8"})
    context = ssl.create_default_context()
    with urlopen(request, timeout=timeout, context=context) as response:
        content_type = response.headers.get_content_type()
        final_url = response.geturl()
        payload = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(payload) > MAX_DOWNLOAD_BYTES:
        raise ValueError("asset exceeds download limit")
    return payload, content_type, final_url


class LogoHTMLParser(HTMLParser):
    def __init__(self, page_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.in_title = False
        self.candidates: list[dict] = []

    @staticmethod
    def attrs_dict(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key.lower(): value or "" for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = self.attrs_dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "img":
            src = values.get("src") or values.get("data-src") or values.get("data-lazy-src")
            if src:
                self.candidates.append({
                    "url": urljoin(self.page_url, src),
                    "alt": values.get("alt", ""),
                    "context": " ".join((values.get("id", ""), values.get("class", ""), values.get("itemprop", ""))),
                    "kind": "image",
                })
        elif tag == "meta":
            prop = (values.get("property") or values.get("name") or "").lower()
            content = values.get("content", "")
            if content and prop in {"og:logo", "twitter:logo"}:
                self.candidates.append({"url": urljoin(self.page_url, content), "alt": prop, "context": prop, "kind": "meta"})
        elif tag == "link":
            rel = values.get("rel", "").lower()
            href = values.get("href", "")
            sizes = values.get("sizes", "")
            if href and "icon" in rel and ("192" in sizes or "512" in sizes or "apple-touch" in rel):
                self.candidates.append({"url": urljoin(self.page_url, href), "alt": rel, "context": sizes, "kind": "icon"})

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        clean = data.strip()
        if clean:
            self.text_parts.append(clean)
            if self.in_title:
                self.title_parts.append(clean)


def candidate_score(candidate: dict, nation_name: str) -> int:
    haystack = " ".join((candidate["url"], candidate.get("alt", ""), candidate.get("context", ""))).lower()
    score = 0
    if re.search(r"(?:^|[-_/])(logo|crest|emblem|brand)(?:[-_.?/]|$)", haystack):
        score += 80
    elif re.search(r"logo|crest|emblem|brand", haystack):
        score += 55
    if candidate.get("kind") == "meta":
        score += 30
    if candidate.get("kind") == "icon":
        score -= 35
    tokens = [token for token in slugify(nation_name).split("-") if token not in {"first", "nation", "cree", "dene"}]
    score += min(24, sum(8 for token in tokens[:4] if len(token) > 3 and token in haystack))
    if re.search(r"banner|hero|slider|slide|photo|gallery|background|header-image|social|facebook|instagram", haystack):
        score -= 70
    if re.search(r"white|light", haystack):
        score -= 4
    return score


def official_site_matches(parser: LogoHTMLParser, nation_name: str) -> bool:
    page_text = " ".join(parser.title_parts + parser.text_parts[:300]).lower()
    meaningful = [token for token in slugify(nation_name).split("-") if token not in {"first", "nation"} and len(token) > 3]
    return bool(meaningful) and sum(token in page_text for token in meaningful[:4]) >= min(2, len(meaningful))


def rasterize_and_optimize(payload: bytes, output: Path) -> tuple[int, int, int]:
    with Image.open(io.BytesIO(payload)) as source:
        image = ImageOps.exif_transpose(source)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA")
        image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
        if image.mode == "RGBA":
            alpha = image.getchannel("A")
            if alpha.getextrema() == (255, 255):
                image = image.convert("RGB")
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output, "WEBP", quality=84, method=6, lossless=image.mode == "RGBA")
        return image.width, image.height, output.stat().st_size


def save_asset_payload(band: dict, page_url: str, asset_url: str, source_kind: str, asset: bytes, asset_type: str) -> dict:
    slug = slugify(band["name"])
    if "svg" in asset_type or asset.lstrip().startswith(b"<svg"):
        if len(asset) > 512_000 or b"<script" in asset.lower():
            raise ValueError("unsafe or oversized SVG")
        target = OUTPUT_DIR / f"{slug}.svg"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(asset)
        dimensions = (None, None, target.stat().st_size)
    else:
        target = OUTPUT_DIR / f"{slug}.webp"
        dimensions = rasterize_and_optimize(asset, target)
        if min(dimensions[:2]) < 32:
            target.unlink(missing_ok=True)
            raise ValueError("logo asset is too small")
    return {
        "nation_id": band["id"],
        "nation_name": band["name"],
        "slug": slug,
        "logo_url": "/" + target.relative_to(ROOT).as_posix(),
        "logo_source": page_url,
        "logo_asset_source": asset_url,
        "logo_verified": True,
        "logo_status": "verified",
        "source_kind": source_kind,
        "verification_note": "Logo/brand asset visually verified in the header of the named Nation's official site.",
        "verified_at": date.today().isoformat(),
        "width": dimensions[0],
        "height": dimensions[1],
        "bytes": dimensions[2],
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }


def save_asset(band: dict, page_url: str, asset_url: str, source_kind: str) -> dict:
    asset, asset_type, final_asset_url = request_bytes(asset_url)
    return save_asset_payload(band, page_url, final_asset_url, source_kind, asset, asset_type)


def site_sources() -> tuple[dict[str, tuple[str, str]], dict[str, dict]]:
    contacts = json.loads((ROOT / "contacts-data.json").read_text(encoding="utf-8"))
    sources: dict[str, tuple[str, str]] = {}
    contacts_by_id: dict[str, dict] = {}
    for row in contacts.get("contacts", []):
        band_id = str(row["nation_id"])
        contacts_by_id[band_id] = row
        if row.get("website_url"):
            sources[band_id] = (row["website_url"], "Official First Nation website")
    sources.update(DISCOVERED_SITES)
    return sources, contacts_by_id


def unverified_record(band: dict, site_url: str | None, source_kind: str | None, reason: str) -> dict:
    return {
        "nation_id": band["id"],
        "nation_name": band["name"],
        "slug": slugify(band["name"]),
        "logo_url": None,
        "logo_source": site_url,
        "logo_asset_source": None,
        "logo_verified": False,
        "logo_status": "logo_unverified",
        "source_kind": source_kind,
        "verification_note": reason,
        "verified_at": None,
    }


def collect_band(band: dict, site_url: str, source_kind: str) -> tuple[dict, list[dict]]:
    payload, content_type, final_url = request_bytes(site_url)
    if content_type not in {"text/html", "application/xhtml+xml"}:
        raise ValueError(f"official source returned {content_type}, not HTML")
    html_text = payload.decode("utf-8", errors="replace")
    parser = LogoHTMLParser(final_url)
    parser.feed(html_text)
    if not official_site_matches(parser, band["name"]):
        raise ValueError("official site identity could not be matched to this Nation")

    inline_class = INLINE_SVG_CLASSES.get(str(band["id"]))
    if inline_class:
        match = re.search(
            rf'(<svg\b[^>]*class=["\'][^"\']*\b{re.escape(inline_class)}\b[^"\']*["\'][^>]*>.*?</svg>)',
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            asset_url = f"{final_url}#inline-official-logo"
            record = save_asset_payload(band, final_url, asset_url, source_kind, match.group(1).encode("utf-8"), "image/svg+xml")
            return record, [{"url": asset_url, "selected": True, "review": "official-site inline SVG wordmark"}]

    unique: dict[str, dict] = {}
    for candidate in parser.candidates:
        if candidate["url"].startswith("data:"):
            continue
        candidate["score"] = candidate_score(candidate, band["name"])
        if candidate["score"] >= 35:
            previous = unique.get(candidate["url"])
            if not previous or candidate["score"] > previous["score"]:
                unique[candidate["url"]] = candidate

    attempts = []
    for candidate in sorted(unique.values(), key=lambda item: item["score"], reverse=True)[:8]:
        try:
            asset, asset_type, asset_url = request_bytes(candidate["url"])
            if "svg" in asset_type or asset.lstrip().startswith(b"<svg"):
                # Keep original SVGs; they are already compact and infinitely scalable.
                if len(asset) > 512_000 or b"<script" in asset.lower():
                    raise ValueError("unsafe or oversized SVG")
                target = OUTPUT_DIR / f"{slugify(band['name'])}.svg"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(asset)
                dimensions = (None, None, target.stat().st_size)
            else:
                target = OUTPUT_DIR / f"{slugify(band['name'])}.webp"
                dimensions = rasterize_and_optimize(asset, target)
                if min(dimensions[:2]) < 72:
                    target.unlink(missing_ok=True)
                    raise ValueError("candidate is too small to verify as the Nation logo")
                ratio = max(dimensions[:2]) / max(1, min(dimensions[:2]))
                if ratio > 5.5:
                    target.unlink(missing_ok=True)
                    raise ValueError("candidate is a banner rather than a compact logo")
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            record = {
                "nation_id": band["id"],
                "nation_name": band["name"],
                "slug": slugify(band["name"]),
                "logo_url": "/" + target.relative_to(ROOT).as_posix(),
                "logo_source": final_url,
                "logo_asset_source": asset_url,
                "logo_verified": True,
                "logo_status": "verified",
                "source_kind": source_kind,
                "verification_note": "Logo/brand asset published by the named Nation's official site.",
                "verified_at": date.today().isoformat(),
                "width": dimensions[0],
                "height": dimensions[1],
                "bytes": dimensions[2],
                "sha256": digest,
            }
            candidate["selected"] = True
            candidate["asset_url"] = asset_url
            candidate["output"] = record["logo_url"]
            attempts.append(candidate)
            return record, attempts
        except (HTTPError, URLError, TimeoutError, ValueError, UnidentifiedImageError, OSError) as exc:
            attempts.append({**candidate, "error": str(exc)})
    raise ValueError("no attributable logo/crest asset passed validation")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--band-id", action="append", help="Limit collection to one or more band IDs")
    parser.add_argument("--local-asset", action="append", default=[], metavar="BAND_ID=PATH", help="Import a browser-downloaded official asset")
    args = parser.parse_args()
    local_assets = dict(value.split("=", 1) for value in args.local_asset)
    selected_ids = set(args.band_id or []) | set(local_assets)
    data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
    sources, _ = site_sources()
    records = []
    report = []
    existing = {}
    if REGISTRY_PATH.exists() and selected_ids:
        existing_data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        existing = {str(row["nation_id"]): row for row in existing_data.get("logos", [])}

    for band in sorted(data.get("bands", []), key=lambda row: row["name"]):
        band_id = str(band["id"])
        if selected_ids and band_id not in selected_ids:
            if band_id in existing:
                records.append(existing[band_id])
            continue
        source = sources.get(band_id)
        if band_id in REJECTED_AUTOMATIC_IDS:
            for suffix in (".webp", ".svg"):
                (OUTPUT_DIR / f"{slugify(band['name'])}{suffix}").unlink(missing_ok=True)
            site_url, source_kind = source if source else (None, None)
            records.append(unverified_record(band, site_url, source_kind, REJECTED_AUTOMATIC_IDS[band_id]))
            report.append({"nation_id": band["id"], "nation_name": band["name"], "status": "logo_unverified", "source": site_url, "reason": REJECTED_AUTOMATIC_IDS[band_id]})
            continue
        if not source:
            records.append(unverified_record(band, None, None, "No official logo source could be confidently verified."))
            report.append({"nation_id": band["id"], "nation_name": band["name"], "status": "logo_unverified", "reason": "no official source"})
            continue
        site_url, source_kind = source
        try:
            if band_id in local_assets:
                page_url, asset_url = MANUAL_ASSETS[band_id]
                local_path = Path(local_assets[band_id])
                asset_type = "image/svg+xml" if local_path.suffix.lower() == ".svg" else "image/png"
                record = save_asset_payload(band, page_url, asset_url, source_kind, local_path.read_bytes(), asset_type)
                attempts = [{"url": asset_url, "selected": True, "review": "browser-downloaded and visually verified official-site header"}]
            elif band_id in MANUAL_ASSETS:
                page_url, asset_url = MANUAL_ASSETS[band_id]
                record = save_asset(band, page_url, asset_url, source_kind)
                attempts = [{"url": asset_url, "selected": True, "review": "browser-verified official-site header"}]
            else:
                record, attempts = collect_band(band, site_url, source_kind)
            records.append(record)
            report.append({"nation_id": band["id"], "nation_name": band["name"], "status": "verified", "source": record["logo_source"], "asset": record["logo_asset_source"], "attempts": attempts})
            print(f"VERIFIED {band['id']} {band['name']} -> {record['logo_url']}")
        except Exception as exc:  # keep one broken community site from aborting the national pass
            records.append(unverified_record(band, site_url, source_kind, str(exc)))
            report.append({"nation_id": band["id"], "nation_name": band["name"], "status": "logo_unverified", "source": site_url, "reason": str(exc)})
            print(f"UNVERIFIED {band['id']} {band['name']}: {exc}")

    records.sort(key=lambda row: row["nation_name"])
    registry = {
        "schemaVersion": 1,
        "generated": date.today().isoformat(),
        "recordCount": len(records),
        "verifiedCount": sum(bool(row["logo_verified"]) for row in records),
        "unverifiedCount": sum(not row["logo_verified"] for row in records),
        "methodology": "Official Nation sites first; authoritative partner sources only when explicitly identified. Generic photos, flags, and unverified recreations are rejected.",
        "logos": records,
    }
    REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_by_id = {str(row["nation_id"]): row for row in report}
    full_report = []
    for record in records:
        band_id = str(record["nation_id"])
        detail = report_by_id.get(band_id)
        if detail:
            full_report.append(detail)
            continue
        summary = {
            "nation_id": record["nation_id"],
            "nation_name": record["nation_name"],
            "status": record["logo_status"],
            "source": record.get("logo_source"),
        }
        if record.get("logo_verified"):
            summary["asset"] = record.get("logo_asset_source")
        else:
            summary["reason"] = record.get("verification_note")
        full_report.append(summary)
    (ROOT / "first-nation-logo-report.json").write_text(json.dumps(full_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    by_id = {str(row["nation_id"]): row for row in records}
    for band in data.get("bands", []):
        logo = by_id.get(str(band["id"]))
        if not logo:
            continue
        band["logo_url"] = logo["logo_url"]
        band["logo_source"] = logo["logo_source"]
        band["logo_asset_source"] = logo["logo_asset_source"]
        band["logo_verified"] = logo["logo_verified"]
        band["logo_status"] = logo["logo_status"]
    (ROOT / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(records)} records: {registry['verifiedCount']} verified, {registry['unverifiedCount']} unverified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
