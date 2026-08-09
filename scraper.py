"""
OpenBand Scraper

Runs nightly via GitHub Actions.
Fetches FNFTA filing listings from Indigenous Services Canada and saves the
results to data.json for the website to read.

Band numbers sourced from:
  - ISC Saskatchewan First Nations map (February 2020, GCdocs #60929202)
  - Wikipedia First Nation infoboxes (cross-referenced against ISC Band Governance
    Management System numbers)

IMPORTANT: ISC uses its own "Band Number" system (BGMS IDs) which differs from
reserve numbers. Always use the BGMS ID in BAND_NUMBER_FF query parameters.
"""

import base64
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime
from html.parser import HTMLParser

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


BANDS = [
    # Treaty 4 Nations
    {"id": 378, "name": "Carry the Kettle Nakoda Nation", "province": "SK", "treaty": "Treaty 4"},
    {"id": 361, "name": "Cowessess First Nation",          "province": "SK", "treaty": "Treaty 4"},
    {"id": 366, "name": "Cote First Nation",               "province": "SK", "treaty": "Treaty 4"},
    {"id": 389, "name": "Day Star First Nation",           "province": "SK", "treaty": "Treaty 4"},
    {"id": 391, "name": "George Gordon First Nation",      "province": "SK", "treaty": "Treaty 4"},
    {"id": 362, "name": "Kahkewistahaw First Nation",      "province": "SK", "treaty": "Treaty 4"},
    {"id": 367, "name": "Keeseekoose First Nation",        "province": "SK", "treaty": "Treaty 4"},
    {"id": 377, "name": "Kinistin Saulteaux Nation",       "province": "SK", "treaty": "Treaty 4"},
    {"id": 379, "name": "Little Black Bear First Nation",  "province": "SK", "treaty": "Treaty 4"},
    {"id": 341, "name": "Lucky Man Cree Nation",           "province": "SK", "treaty": "Treaty 6"},
    {"id": 396, "name": "Makwa Sahgaiehcan First Nation",  "province": "SK", "treaty": "Treaty 6"},
    {"id": 374, "name": "Mistawasis Nehiyawak",            "province": "SK", "treaty": "Treaty 6"},
    {"id": 371, "name": "Muskoday First Nation",           "province": "SK", "treaty": "Treaty 6"},
    {"id": 363, "name": "Ochapowace First Nation",         "province": "SK", "treaty": "Treaty 4"},
    {"id": 344, "name": "Onion Lake Cree Nation",          "province": "SK", "treaty": "Treaty 6"},
    {"id": 383, "name": "Pasqua First Nation",             "province": "SK", "treaty": "Treaty 4"},
    {"id": 384, "name": "Peepeekisis Cree Nation",         "province": "SK", "treaty": "Treaty 4"},
    {"id": 405, "name": "Pelican Lake First Nation",       "province": "SK", "treaty": "Treaty 6"},
    {"id": 355, "name": "Peter Ballantyne Cree Nation",    "province": "SK", "treaty": "Treaty 6"},
    {"id": 409, "name": "Pheasant Rump Nakota Nation",     "province": "SK", "treaty": "Treaty 4"},
    {"id": 345, "name": "Poundmaker Cree Nation",          "province": "SK", "treaty": "Treaty 6"},
    {"id": 356, "name": "Red Earth Cree Nation",           "province": "SK", "treaty": "Treaty 6"},
    {"id": 346, "name": "Red Pheasant Cree Nation",        "province": "SK", "treaty": "Treaty 6"},
    {"id": 364, "name": "Sakimay First Nations",           "province": "SK", "treaty": "Treaty 4"},
    {"id": 357, "name": "Shoal Lake Cree Nation",          "province": "SK", "treaty": "Treaty 6"},
    {"id": 348, "name": "Sweetgrass First Nation",         "province": "SK", "treaty": "Treaty 6"},
    {"id": 368, "name": "The Key First Nation",            "province": "SK", "treaty": "Treaty 4"},
    {"id": 349, "name": "Thunderchild First Nation",       "province": "SK", "treaty": "Treaty 6"},
    {"id": 358, "name": "Wahpeton Dakota Nation",          "province": "SK", "treaty": "Treaty 4"},
    {"id": 402, "name": "Waterhen Lake First Nation",      "province": "SK", "treaty": "Treaty 6"},
    {"id": 365, "name": "White Bear First Nations",        "province": "SK", "treaty": "Treaty 4"},
    {"id": 372, "name": "Whitecap Dakota First Nation",    "province": "SK", "treaty": "Treaty 4"},
    {"id": 388, "name": "Wood Mountain First Nation",      "province": "SK", "treaty": "Treaty 4"},
    {"id": 376, "name": "Yellow Quill First Nation",       "province": "SK", "treaty": "Treaty 4"},
    # Treaty 6 / Northern
    {"id": 406, "name": "Ahtahkakoop Cree Nation",         "province": "SK", "treaty": "Treaty 6"},
    {"id": 369, "name": "Beardy's and Okemasis' Cree Nation", "province": "SK", "treaty": "Treaty 6"},
    {"id": 398, "name": "Buffalo River Dene Nation",       "province": "SK", "treaty": "Treaty 10"},
    {"id": 394, "name": "Canoe Lake Cree First Nation",    "province": "SK", "treaty": "Treaty 10"},
    {"id": 401, "name": "Clearwater River Dene Nation",    "province": "SK", "treaty": "Treaty 10"},
    {"id": 350, "name": "Cumberland House Cree Nation",    "province": "SK", "treaty": "Treaty 5"},
    {"id": 400, "name": "English River Dene Nation",       "province": "SK", "treaty": "Treaty 10"},
    {"id": 390, "name": "Fishing Lake First Nation",       "province": "SK", "treaty": "Treaty 4"},
    {"id": 395, "name": "Flying Dust First Nation",        "province": "SK", "treaty": "Treaty 6"},
    {"id": 352, "name": "Hatchet Lake Denesuline",         "province": "SK", "treaty": "Treaty 10"},
    {"id": 353, "name": "Lac La Ronge Indian Band",        "province": "SK", "treaty": "Treaty 6"},
    {"id": 340, "name": "Little Pine First Nation",        "province": "SK", "treaty": "Treaty 6"},
    {"id": 397, "name": "Ministikwan Lake Cree Nation",    "province": "SK", "treaty": "Treaty 6"},
    {"id": 354, "name": "Montreal Lake Cree Nation",       "province": "SK", "treaty": "Treaty 6"},
    {"id": 342, "name": "Moosomin First Nation",           "province": "SK", "treaty": "Treaty 6"},
    {"id": 343, "name": "Mosquito, Grizzly Bear's Head, Lean Man", "province": "SK", "treaty": "Treaty 6"},
    {"id": 381, "name": "Muscowpetung First Nation",       "province": "SK", "treaty": "Treaty 4"},
    {"id": 375, "name": "Muskeg Lake Cree Nation",         "province": "SK", "treaty": "Treaty 6"},
    {"id": 392, "name": "Muskowekwan First Nation",        "province": "SK", "treaty": "Treaty 4"},
    {"id": 380, "name": "Nekaneet Cree Nation",            "province": "SK", "treaty": "Treaty 4"},
    {"id": 408, "name": "Ocean Man First Nation",          "province": "SK", "treaty": "Treaty 4"},
    {"id": 382, "name": "Okanese First Nation",            "province": "SK", "treaty": "Treaty 4"},
    {"id": 373, "name": "One Arrow First Nation",          "province": "SK", "treaty": "Treaty 6"},
    {"id": 385, "name": "Piapot First Nation",             "province": "SK", "treaty": "Treaty 4"},
    {"id": 347, "name": "Saulteaux First Nation",          "province": "SK", "treaty": "Treaty 6"},
    {"id": 386, "name": "Standing Buffalo Dakota Nation",  "province": "SK", "treaty": "Treaty 4"},
    {"id": 387, "name": "Star Blanket Cree Nation",        "province": "SK", "treaty": "Treaty 4"},
    {"id": 360, "name": "Sturgeon Lake First Nation",      "province": "SK", "treaty": "Treaty 6"},
]

ISC_HOST = "https://fnp-ppn.aadnc-aandc.gc.ca"
ISC_BASE = f"{ISC_HOST}/fnp/Main/Search"
USER_AGENT = "OpenBand/1.0 (transparency research; nightly GitHub Action)"


def utc_now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def normalize_pdf_url(url):
    """Ensure query params are URL-encoded before requesting ISC PDFs."""
    if not url:
        return url
    parts = urllib.parse.urlsplit(url)
    query_pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    safe_query = urllib.parse.urlencode(query_pairs, quote_via=urllib.parse.quote)
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, safe_query, parts.fragment)
    )


class FilingParser(HTMLParser):
    """Extract rows from ISC filing-listing tables."""

    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_td = False
        self.current_row = []
        self.current_cell = ""
        self.current_href = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.current_row = []
        elif self.in_table and tag == "td":
            self.in_td = True
            self.current_cell = ""
            self.current_href = None
        elif self.in_td and tag == "a":
            self.current_href = attrs.get("href", "")

    def handle_endtag(self, tag):
        if tag == "td" and self.in_td:
            self.current_row.append(
                {"text": " ".join(self.current_cell.split()), "href": self.current_href}
            )
            self.in_td = False
        elif tag == "tr" and self.in_table and len(self.current_row) >= 3:
            self.rows.append(self.current_row)
        elif tag == "table":
            self.in_table = False

    def handle_data(self, data):
        if self.in_td:
            self.current_cell += data


def fetch_url(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_band_filings(band_id):
    """Fetch the FNFTA filing page for one band and return parsed rows."""
    url = f"{ISC_BASE}/FederalFundingMain.aspx?BAND_NUMBER={band_id}&lang=eng"
    try:
        html = fetch_url(url, timeout=15).decode("utf-8", errors="replace")
        parser = FilingParser()
        parser.feed(html)

        filings = []
        for row in parser.rows:
            year_text = row[0]["text"]
            doc_text = row[1]["text"]
            date_text = row[2]["text"]
            href = row[1]["href"]

            if not re.match(r"\d{4}-\d{4}", year_text):
                continue

            if href and not href.startswith("http"):
                href = f"{ISC_BASE}/{href.lstrip('/')}"

            posted = date_text not in ("", "Not yet posted", "-", "—", "N/A")
            filings.append(
                {
                    "year": year_text,
                    "docType": doc_text,
                    "date": date_text,
                    "href": href if posted else None,
                    "posted": posted,
                }
            )

        return filings
    except Exception as exc:
        print(f"  ERROR band {band_id}: {exc}")
        return None


def build_direct_pdf_urls(band_id):
    """Build direct ISC DisplayBinaryData PDF links as a fallback."""
    fiscal_years = [
        "2023-2024",
        "2022-2023",
        "2021-2022",
        "2020-2021",
        "2019-2020",
        "2018-2019",
        "2017-2018",
        "2016-2017",
        "2015-2016",
    ]
    doc_types = [
        "Audited consolidated financial statements",
        "Schedule of Remuneration and Expenses",
    ]

    filings = []
    for fy in fiscal_years:
        for doc in doc_types:
            params = urllib.parse.urlencode(
                {"BAND_NUMBER_FF": band_id, "FY": fy, "DOC": doc, "lang": "eng"},
                quote_via=urllib.parse.quote,
            )
            href = f"{ISC_BASE}/DisplayBinaryData.aspx?{params}"
            filings.append(
                {
                    "year": fy,
                    "docType": doc,
                    "date": "See ISC",
                    "href": href,
                    "posted": True,
                    "fallback": True,
                }
            )
    return filings


def parse_money(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "—", "N/A"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if not cleaned or cleaned in {"-", "."}:
        return None
    try:
        amount = float(cleaned)
        return -amount if negative and amount > 0 else amount
    except ValueError:
        return None


def response_output_text(response_json):
    if response_json.get("output_text"):
        return response_json["output_text"]
    chunks = []
    for item in response_json.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def extract_with_openai_vision(pdf_bytes):
    if os.getenv("OPENBAND_ALLOW_OPENAI", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return {
            "parse_status": "skipped_openai_disabled",
            "warnings": ["OpenAI fallback requires explicit OPENBAND_ALLOW_OPENAI opt-in"],
            "people": [],
        }
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "parse_status": "skipped_openai_no_key",
            "warnings": ["OPENAI_API_KEY not set"],
            "people": [],
        }

    prompt = (
        "Extract the Chief and Council remuneration table from this PDF. "
        "Return only JSON with this shape: "
        '{"people":[{"name":str,"role":str,"months":number|null,'
        '"remuneration":number|null,"travel":number|null,"expenses":number|null,'
        '"creditCard":number|null,"otherPayments":number|null,"total":number|null}]}. '
        'If no table is present, return {"people":[]}.'
    )
    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "max_tokens": 1000,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_file",
                        "filename": "filing.pdf",
                        "file_data": "data:application/pdf;base64,"
                        + base64.b64encode(pdf_bytes).decode("ascii"),
                    },
                ],
            }
        ],
    }

    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = json.loads(resp.read().decode("utf-8"))

        text = response_output_text(raw)
        if not text:
            return {
                "parse_status": "error_openai_empty",
                "warnings": ["OpenAI returned empty output"],
                "people": [],
            }

        data = json.loads(text)
        rows = data.get("people", []) if isinstance(data, dict) else []
        people = []
        for row in rows:
            people.append(
                {
                    "name": str(row.get("name", "")).strip(),
                    "role": str(row.get("role", "")).strip() or "Council",
                    "months": parse_money(row.get("months")),
                    "remuneration": parse_money(row.get("remuneration")),
                    "travel": parse_money(row.get("travel")),
                    "expenses": parse_money(row.get("expenses")),
                    "creditCard": parse_money(row.get("creditCard")),
                    "otherPayments": parse_money(row.get("otherPayments")),
                    "total": parse_money(row.get("total")),
                }
            )
        return {
            "parse_status": "ok_openai",
            "warnings": [],
            "people": [p for p in people if p["name"]],
        }
    except Exception as exc:
        return {
            "parse_status": "error_openai",
            "warnings": [f"OpenAI parse failed: {exc}"],
            "people": [],
        }


def role_from_cells(cells):
    joined = " ".join(cells).lower()
    if re.search(r"\bchief\b", joined):
        return "Chief"
    if re.search(r"\bcouncillor\b|\bcouncil\b", joined):
        return "Councillor"
    return "Council"


def header_key(cell):
    text = re.sub(r"\s+", " ", str(cell or "").strip().lower())
    if not text:
        return None
    if "credit" in text and "card" in text:
        return "creditCard"
    if "other" in text and ("payment" in text or "payments" in text):
        return "otherPayments"
    if "travel" in text or "per diem" in text:
        return "travel"
    if "expense" in text and "remuneration" not in text:
        return "expenses"
    if "remuneration" in text or "salary" in text or "honoraria" in text:
        return "remuneration"
    if "month" in text:
        return "months"
    if "position" in text or text == "chief and council":
        return "role"
    if text.startswith("name"):
        return "name"
    if text == "total":
        return "total"
    return None


def clean_person_name(name):
    name = re.sub(r"\*+$", "", str(name or "").strip())
    name = re.sub(r"\s+", " ", name)
    return name


def value_by_key(cells, keys, key):
    if key not in keys:
        return None
    index = keys.index(key)
    if index >= len(cells):
        return None
    return cells[index]


def extract_people_from_table(table):
    people = []
    keys = []

    for row in table:
        if not row:
            continue

        cells = [" ".join(str(cell or "").split()) for cell in row]
        joined = " ".join(cells).lower()
        if not joined:
            continue

        possible_keys = [header_key(cell) for cell in cells]
        if "remuneration" in possible_keys and (
            "months" in possible_keys
            or "travel" in possible_keys
            or "expenses" in possible_keys
            or "otherPayments" in possible_keys
            or "total" in possible_keys
        ):
            keys = possible_keys
            continue

        amounts = [parse_money(cell) for cell in cells]
        amounts_present = [a for a in amounts if a is not None]
        if not amounts_present:
            continue
        if re.match(r"^\s*total\b", cells[0], re.I):
            continue

        name = clean_person_name(value_by_key(cells, keys, "name"))
        role = value_by_key(cells, keys, "role") or ""

        if not name and cells and re.search(r"chief|councillor|council", cells[0], re.I):
            role = role or cells[0]
            name = clean_person_name(cells[1] if len(cells) > 1 else "")

        if not name:
            for cell in cells:
                if parse_money(cell) is not None:
                    continue
                if re.search(r"chief|councillor|council|months?|position", cell, re.I):
                    continue
                if len(cell) >= 2:
                    name = clean_person_name(cell)
                    break
        if not name:
            continue

        months = parse_money(value_by_key(cells, keys, "months"))
        remuneration = parse_money(value_by_key(cells, keys, "remuneration"))
        travel = parse_money(value_by_key(cells, keys, "travel"))
        expenses = parse_money(value_by_key(cells, keys, "expenses"))
        credit_card = parse_money(value_by_key(cells, keys, "creditCard"))
        other_payments = parse_money(value_by_key(cells, keys, "otherPayments"))
        total = parse_money(value_by_key(cells, keys, "total"))

        if remuneration is None:
            remuneration = amounts_present[0]
        if total is None:
            total = sum(
                v or 0 for v in [remuneration, travel, expenses, credit_card, other_payments]
            )

        people.append(
            {
                "name": name,
                "role": role_from_cells([role] + cells),
                "months": months,
                "remuneration": remuneration,
                "travel": travel,
                "expenses": expenses,
                "creditCard": credit_card,
                "otherPayments": other_payments,
                "total": total,
            }
        )
    return people


def extract_remuneration_rows(pdf_url):
    if not pdf_url:
        return {"parse_status": "no_pdf_url", "warnings": ["No PDF URL available"], "people": []}

    warnings = []
    try:
        pdf_bytes = fetch_url(normalize_pdf_url(pdf_url), timeout=30)
    except Exception as exc:
        return {
            "parse_status": "error_pdf_download",
            "warnings": [f"PDF download failed: {exc}"],
            "people": [],
        }

    if pdfplumber is None:
        ai_result = extract_with_openai_vision(pdf_bytes)
        ai_result["warnings"] = ["pdfplumber unavailable"] + ai_result.get("warnings", [])
        return ai_result

    try:
        people = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables() or []:
                    people.extend(extract_people_from_table(table))

        if people:
            return {"parse_status": "ok_pdfplumber", "warnings": warnings, "people": people}

        ai_result = extract_with_openai_vision(pdf_bytes)
        if ai_result.get("people"):
            ai_result["warnings"] = ["Parsed via OpenAI fallback"] + ai_result.get("warnings", [])
            return ai_result

        warnings.append("No remuneration rows detected from PDF table extraction")
        warnings.extend(ai_result.get("warnings", []))
        return {
            "parse_status": ai_result.get("parse_status", "no_rows"),
            "warnings": warnings,
            "people": [],
        }
    except Exception as exc:
        return {"parse_status": "error", "warnings": [f"PDF parse failed: {exc}"], "people": []}


def should_parse_people(filing):
    return filing.get("posted") and "remuneration" in filing.get("docType", "").lower()


def successful_filing_index(path="data.json"):
    """Index completed filings so routine retries never pay to parse them again."""
    try:
        with open(path, encoding="utf-8") as handle:
            existing = json.load(handle)
    except (OSError, ValueError, TypeError):
        return {}

    indexed = {}
    for band in existing.get("bands", []):
        for filing in band.get("filings", []):
            if not filing.get("people"):
                continue
            key = (
                str(band.get("id")),
                str(filing.get("year") or ""),
                str(filing.get("docType") or "").strip().lower(),
            )
            indexed[key] = filing
    return indexed


def metric_for_result(result):
    status = str(result.get("parse_status") or "")
    if result.get("people") and status == "ok_ocr":
        return "ocr_success"
    if result.get("people") and status == "ok_openai":
        return "ai_success"
    if result.get("people") and status.startswith("ok_"):
        return "local_success"
    return "still_pending"


def main():
    print(f"OpenBand scraper starting - {utc_now()}")
    print(f"Scraping {len(BANDS)} bands...\n")

    results = []
    errors = 0
    successful = successful_filing_index()
    parse_metrics = {
        "local_success": 0,
        "ocr_success": 0,
        "ai_success": 0,
        "reused_success": 0,
        "still_pending": 0,
    }

    for index, band in enumerate(BANDS, start=1):
        print(f"[{index}/{len(BANDS)}] {band['name']} (ISC #{band['id']})")
        filings = fetch_band_filings(band["id"])

        if filings is None:
            filings = build_direct_pdf_urls(band["id"])
            errors += 1
            status = "fallback"
        elif not filings:
            filings = build_direct_pdf_urls(band["id"])
            status = "no-filings-found"
        else:
            status = "ok"

        enriched = []
        for filing in filings:
            enriched_filing = dict(filing)
            enriched_filing["people"] = []
            enriched_filing["parse_status"] = "not_applicable"
            enriched_filing["warnings"] = []

            if should_parse_people(enriched_filing):
                existing_key = (
                    str(band.get("id")),
                    str(enriched_filing.get("year") or ""),
                    str(enriched_filing.get("docType") or "").strip().lower(),
                )
                prior = successful.get(existing_key)
                if prior:
                    for key in (
                        "people",
                        "parse_status",
                        "warnings",
                        "parse_confidence",
                        "manual_review_required",
                        "parse_stages",
                    ):
                        if key in prior:
                            enriched_filing[key] = prior[key]
                    parse_metrics["reused_success"] += 1
                else:
                    parsed = extract_remuneration_rows(enriched_filing.get("href"))
                    for key in (
                        "people",
                        "parse_status",
                        "warnings",
                        "parse_confidence",
                        "manual_review_required",
                        "parse_stages",
                    ):
                        if key in parsed:
                            enriched_filing[key] = parsed[key]
                    parse_metrics[metric_for_result(parsed)] += 1

            enriched.append(enriched_filing)

        print(f"  -> {len(enriched)} filings ({status})")
        results.append(
            {
                "id": band["id"],
                "name": band["name"],
                "province": band["province"],
                "treaty": band.get("treaty", ""),
                "filings": enriched,
                "status": status,
                "scraped": utc_now(),
            }
        )

        time.sleep(float(os.getenv("OPENBAND_REQUEST_DELAY", "1")))

    output = {
        "generated": utc_now(),
        "band_count": len(results),
        "error_count": errors,
        "parse_metrics": parse_metrics,
        "bands": results,
    }

    with open("data.json", "w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)

    print(f"\nDone. {len(results)} bands scraped, {errors} errors.")
    print(
        "Parse metrics: "
        + ", ".join(f"{key}={value}" for key, value in parse_metrics.items())
    )
    print("Saved to data.json")


if __name__ == "__main__":
    main()
