"""Refresh public Band Office contacts from ISC and official community sites.

The ISC First Nation profile is the baseline source for the office phone,
mailing address, and community website.  Official websites are scanned only
for clearly generic office mailboxes; named/personal addresses are ignored.
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from lxml import html as lxml_html


ROOT = Path(__file__).resolve().parents[1]
ISC_PROFILE = (
    "https://fnp-ppn.aadnc-aandc.gc.ca/fnp/Main/Search/"
    "FNMain.aspx?BAND_NUMBER={band_id}&lang=eng"
)
USER_AGENT = "OpenBand contact verifier/1.0 (+https://openband.ca/)"
GENERIC_MAILBOXES = {
    "admin",
    "administration",
    "administrator",
    "bandadmin",
    "bandoffice",
    "band-office",
    "communications",
    "contact",
    "enquiries",
    "general",
    "info",
    "inquiries",
    "office",
    "reception",
}
EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
CONTACT_LINK_RE = re.compile(r"contact|administration|band[-_ ]?office|governance|about", re.I)
NON_COMMUNITY_WEBSITE_HOSTS = {
    "batc.ca",
    "www.batc.ca",
    "fhqtc.com",
    "www.fhqtc.com",
    "fnpa.ca",
    "www.fnpa.ca",
    "mltc.net",
    "www.mltc.net",
    "pagc.sk.ca",
    "www.pagc.sk.ca",
    "sktc.sk.ca",
    "www.sktc.sk.ca",
}


def fetch(url: str, timeout: int = 12) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"})
    context = ssl.create_default_context()
    with urlopen(request, timeout=timeout, context=context) as response:
        return response.read(), response.geturl()


def clean_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip(" ,")
    return cleaned or None


def text_after(lines: list[str], label: str) -> str | None:
    try:
        index = lines.index(label)
    except ValueError:
        return None
    return lines[index + 1] if index + 1 < len(lines) else None


def format_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return clean_text(value)


def parse_isc_profile(content: bytes, final_url: str) -> dict:
    document = lxml_html.fromstring(content, base_url=final_url)
    lines = [clean_text(value) for value in document.itertext()]
    lines = [value for value in lines if value]
    address = text_after(lines, "Address")
    postal_code = text_after(lines, "Postal code")
    mailing_address = ", ".join(value for value in (address, postal_code) if value) or None

    website_url = None
    website_label = text_after(lines, "Web Site")
    if website_label:
        for anchor in document.xpath("//a[@href]"):
            if clean_text(anchor.text_content()) == website_label:
                candidate = urljoin(final_url, anchor.get("href"))
                if urlparse(candidate).scheme in {"http", "https"}:
                    website_url = candidate
                    break
    if website_url and urlparse(website_url).netloc.lower() in NON_COMMUNITY_WEBSITE_HOSTS:
        website_url = None

    return {
        "official_name": text_after(lines, "Official Name"),
        "office_phone": format_phone(text_after(lines, "Phone")),
        "website_url": website_url,
        "mailing_address": mailing_address,
    }


def normalized_email(value: str) -> str | None:
    email = value.strip().strip(".,;:()[]<>").lower()
    if not EMAIL_RE.fullmatch(email):
        return None
    local = email.split("@", 1)[0]
    compact = re.sub(r"[^a-z]", "", local)
    allowed = local in GENERIC_MAILBOXES or compact in {
        re.sub(r"[^a-z]", "", item) for item in GENERIC_MAILBOXES
    }
    return email if allowed else None


def emails_in_document(content: bytes, final_url: str) -> tuple[list[str], object]:
    document = lxml_html.fromstring(content, base_url=final_url)
    values: set[str] = set()
    for anchor in document.xpath("//a[starts-with(translate(@href, 'MAILTO', 'mailto'), 'mailto:')]"):
        raw = anchor.get("href", "").split(":", 1)[-1].split("?", 1)[0]
        if email := normalized_email(raw):
            values.add(email)
    rendered = " ".join(document.itertext())
    for raw in EMAIL_RE.findall(rendered):
        if email := normalized_email(raw):
            values.add(email)
    return sorted(values), document


def candidate_contact_pages(document: object, final_url: str, limit: int = 3) -> list[str]:
    origin = urlparse(final_url)
    candidates: list[str] = []
    for anchor in document.xpath("//a[@href]"):
        href = anchor.get("href", "")
        if not href or re.search(r"[\x00-\x20]", href) or href.count(",") > 1:
            continue
        label = f"{anchor.text_content()} {href}"
        if not CONTACT_LINK_RE.search(label):
            continue
        target = urljoin(final_url, href).split("#", 1)[0]
        parsed = urlparse(target)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != origin.netloc:
            continue
        if target not in candidates and target != final_url:
            candidates.append(target)
        if len(candidates) >= limit:
            break
    return candidates


def find_official_email(website_url: str | None) -> tuple[str | None, str | None, list[str]]:
    if not website_url:
        return None, None, []
    errors: list[str] = []
    try:
        content, final_url = fetch(website_url)
        emails, document = emails_in_document(content, final_url)
        if emails:
            return emails[0], final_url, errors
        for page_url in candidate_contact_pages(document, final_url):
            try:
                page, page_final_url = fetch(page_url)
                page_emails, _ = emails_in_document(page, page_final_url)
                if page_emails:
                    return page_emails[0], page_final_url, errors
            except (HTTPError, URLError, TimeoutError, ValueError, http.client.HTTPException) as exc:
                errors.append(f"{page_url}: {type(exc).__name__}")
    except (HTTPError, URLError, TimeoutError, ValueError, http.client.HTTPException) as exc:
        errors.append(f"{website_url}: {type(exc).__name__}")
    return None, None, errors


def load_overrides() -> dict[str, dict]:
    path = ROOT / "manual_overrides" / "contacts.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(key): value for key, value in payload.get("bands", {}).items()}


def build_record(band: dict, *, scan_emails: bool, overrides: dict[str, dict]) -> tuple[dict, list[str]]:
    band_id = str(band["id"])
    source_url = ISC_PROFILE.format(band_id=band_id)
    content, final_url = fetch(source_url)
    isc = parse_isc_profile(content, final_url)
    email = email_source_url = None
    errors: list[str] = []
    if scan_emails:
        email, email_source_url, errors = find_official_email(isc["website_url"])

    override = overrides.get(band_id, {})
    for field in ("office_phone", "office_email", "website_url", "mailing_address"):
        if field in override:
            if field == "office_phone":
                isc[field] = format_phone(override[field])
            elif field == "office_email":
                email = override[field]
            else:
                isc[field] = override[field]
    if override.get("email_source_url"):
        email_source_url = override["email_source_url"]
    if override.get("source_url"):
        source_url = override["source_url"]

    field_sources = {
        "office_phone": source_url if isc.get("office_phone") else None,
        "website_url": source_url if isc.get("website_url") else None,
        "mailing_address": source_url if isc.get("mailing_address") else None,
        "office_email": email_source_url if email else None,
    }
    record = {
        "nation_id": int(band["id"]),
        "nation_name": band["name"],
        "office_phone": isc.get("office_phone"),
        "office_email": email,
        "website_url": isc.get("website_url"),
        "mailing_address": isc.get("mailing_address"),
        "source_url": source_url,
        "field_sources": field_sources,
        "last_verified": date.today().isoformat(),
    }
    return record, errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-email-scan", action="store_true", help="Only refresh ISC fields")
    parser.add_argument("--workers", type=int, default=6, help="Concurrent public-source checks")
    args = parser.parse_args()

    data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
    bands = sorted(data.get("bands", []), key=lambda row: str(row["name"]))
    overrides = load_overrides()
    records: list[dict] = []
    failures: list[dict] = []
    completed: list[tuple[int, dict, dict, list[str]]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as executor:
        futures = {
            executor.submit(
                build_record,
                band,
                scan_emails=not args.no_email_scan,
                overrides=overrides,
            ): (index, band)
            for index, band in enumerate(bands, start=1)
        }
        for future in as_completed(futures):
            index, band = futures[future]
            try:
                record, errors = future.result()
                completed.append((index, band, record, errors))
                print(f"[{len(completed)}/{len(bands)}] {band['name']}: phone={'yes' if record['office_phone'] else 'no'}, email={'yes' if record['office_email'] else 'no'}", flush=True)
            except (HTTPError, URLError, TimeoutError, ValueError, http.client.HTTPException) as exc:
                completed.append((index, band, {}, [repr(exc)]))
                print(f"[{len(completed)}/{len(bands)}] {band['name']}: FAILED ({type(exc).__name__})", flush=True)

    for index, band, record, errors in sorted(completed):
        try:
            if not record:
                raise ValueError(errors[0])
            records.append(record)
            if errors:
                failures.append({"nation_id": band["id"], "nation_name": band["name"], "errors": errors})
        except (HTTPError, URLError, TimeoutError, ValueError, http.client.HTTPException) as exc:
            failures.append({"nation_id": band["id"], "nation_name": band["name"], "errors": [repr(exc)]})

    output = {
        "schemaVersion": 1,
        "generated": date.today().isoformat(),
        "recordCount": len(records),
        "emailCount": sum(bool(row["office_email"]) for row in records),
        "phoneCount": sum(bool(row["office_phone"]) for row in records),
        "websiteCount": sum(bool(row["website_url"]) for row in records),
        "mailingAddressCount": sum(bool(row["mailing_address"]) for row in records),
        "sourcePriority": [
            "Official First Nation website",
            "Indigenous Services Canada First Nation Profiles",
        ],
        "contacts": records,
        "failures": failures,
    }
    (ROOT / "contacts-data.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {len(records)} contacts: {output['phoneCount']} phones, "
        f"{output['emailCount']} general emails, {output['websiteCount']} websites, "
        f"{output['mailingAddressCount']} mailing addresses."
    )


if __name__ == "__main__":
    main()
