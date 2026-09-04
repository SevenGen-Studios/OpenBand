"""Extract project disclosures from audited financial statements without AI.

The output is deliberately evidence-limited: a project name or financial amount
reported in an audit does not establish construction status, approval, total cost,
or completion. Existing public-source project records are never overwritten.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MONEY = r"(?:(?:\$\s*)?\(?[\d,]+\)?|-)"
USER_AGENT = "OpenBand/2.0 (https://openband.ca; public-records research)"
LEAD_CONTEXTS = (
    ("investment", "Investments and business interests"),
    ("government business enterprise", "Government business enterprises"),
    ("limited partnership", "Partnership interests"),
    ("joint venture", "Joint ventures"),
    ("related part", "Related entities"),
    ("subsidiar", "Subsidiaries"),
    ("commitments", "Commitments and contingencies"),
    ("subsequent events", "Subsequent events"),
    ("loans receivable", "Loans and advances"),
    ("advances to", "Loans and advances"),
)
ENTITY_TERMS = re.compile(
    r"\b(?:limited partnership|l\.?p\.?|ltd\.?|limited|inc\.?|corporation|corp\.?|"
    r"company|enterprise|ventures?|development corporation|joint venture|associate|subsidiar|project)\b",
    re.I,
)
LEAD_PREFIX = re.compile(
    r"^(?:investment in|investments in|loan to|loans to|advance to|advances to|"
    r"interest in|equity in|share of income from|income from|commitment (?:to|for))\s+",
    re.I,
)
GENERIC_LEAD_LABEL = re.compile(
    r"^(?:total|subtotal|current|prior|balance|cash|accounts? receivable|"
    r"tangible capital assets?|portfolio investments?|investment income|"
    r"equity in (?:investments|capital assets|tangible capital assets|cmhc (?:operating |replacement )?reserves?|"
    r"funds held in trust|controlled business entities)|"
    r"investments? in (?:limited partnerships|government business enterprises|gbe|nation business entities)|"
    r"limited partnership (?:interests|earnings)|"
    r"earnings from (?:limited partnership|lp) interests|advances to members|"
    r"canada mortgage and housing corporation(?: \(cmhc\))?|community development corporation|corporation|less:.+)$",
    re.I,
)


def slugify(value: str) -> str:
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", value.lower()))


def parse_money(value: str) -> int | None:
    text = str(value or "").strip()
    if not text or text == "-":
        return None
    negative = text.startswith("(") and text.endswith(")")
    digits = re.sub(r"[^0-9]", "", text)
    if not digits:
        return None
    amount = int(digits)
    return -amount if negative else amount


def project_category(name: str) -> str:
    value = name.lower()
    if any(word in value for word in ("water", "sewage", "lagoon", "wastewater")):
        return "Water & Wastewater"
    if any(word in value for word in ("school", "education")):
        return "Education"
    if any(word in value for word in ("housing", "home", "residential")):
        return "Housing"
    if any(word in value for word in ("road", "drainage", "culvert", "bridge")):
        return "Roads & Drainage"
    if any(word in value for word in ("health", "wellness", "status")):
        return "Health Centre"
    if any(word in value for word in ("arena", "community centre", "community center")):
        return "Community Facilities"
    if any(word in value for word in ("connectivity", "broadband", "internet", "fibre", "fiber")):
        return "Connectivity"
    if any(word in value for word in ("contaminated", "remediation", "landfill")):
        return "Environment"
    if any(word in value for word in ("energy", "solar", "wind", "gasification")):
        return "Energy"
    return "Community Infrastructure"


def clean_project_name(value: str) -> str:
    value = re.sub(r"\s+-\s+ISC\s+Capital\s+Project\s*$", "", value, flags=re.I)
    value = re.sub(r"^Capital\s+project\s*-\s*", "", value, flags=re.I)
    return re.sub(r"\s+", " ", value).strip(" .:-")


def canonical_project_name(value: str) -> str:
    """Combine source-label variants only when they name the same known project."""
    cleaned = clean_project_name(value)
    aliases = {
        "sewage lagoon": "Sewage Pumping Station and Lagoon",
        "sewage pumping station": "Sewage Pumping Station and Lagoon",
        "wwaater treatment plant evaluation and upgrade": "Water Treatment Plant Evaluation and Upgrade",
    }
    return aliases.get(cleaned.lower(), cleaned)


def disclosure_key(name: str) -> str:
    value = canonical_project_name(name).lower()
    value = re.sub(r"\s+project$", "", value)
    replacements = {"elementary school": "elementary school repairs"}
    return slugify(replacements.get(value, value))


def source_record(url: str, band_name: str, fiscal_year: str, checked_at: str) -> dict:
    return {
        "name": f"{band_name} {fiscal_year} audited financial statement",
        "url": url,
        "checkedAt": checked_at,
    }


def lead_key(value: str) -> str:
    value = re.sub(r"\b(?:investment|investments|loan|loans|advance|advances|interest|equity)\s+(?:in|to)\s+", "", value, flags=re.I)
    value = re.sub(r"\s+", " ", value).strip(" .:-")
    return slugify(value)


def _lead_context(page_text: str) -> str | None:
    lower = page_text.lower()
    if "statement of operations" in lower:
        return "Statement of operations"
    for cue, label in LEAD_CONTEXTS:
        if cue in lower:
            return label
    return None


def _line_lead_context(label: str, page_context: str) -> str:
    lower = label.lower()
    if "limited partnership" in lower or re.search(r"\bl\.?p\.?\b", lower):
        return "Partnership interests"
    if "joint venture" in lower:
        return "Joint ventures"
    if any(value in lower for value in ("loan to", "loans to", "advance to", "advances to")):
        return "Loans and advances"
    if "commitment" in lower:
        return "Commitments and contingencies"
    return page_context


def _year_column_order(page_text: str, fiscal_year: str) -> str:
    """Return the current/comparative order when the audit states both years."""
    match = re.match(r"(\d{4})-(\d{4})", fiscal_year)
    if not match:
        return "current_first"
    current = match.group(2)
    prior = str(int(current) - 1)
    compact = re.sub(r"[^0-9]+", " ", page_text)
    current_first = re.search(rf"\b{current}\s+{prior}\b", compact)
    comparative_first = re.search(rf"\b{prior}\s+{current}\b", compact)
    return "comparative_first" if comparative_first and not current_first else "current_first"


def _amount_indexes(page_text: str, fiscal_year: str, value_count: int) -> tuple[int, int | None]:
    if value_count < 2:
        return 0, None
    if re.search(r"\bbudget\b", page_text, re.I) and value_count >= 3:
        return 1, 2
    return (1, 0) if _year_column_order(page_text, fiscal_year) == "comparative_first" else (0, 1)


def _split_label_values(line: str) -> tuple[str, list[int | None]]:
    protected = re.sub(r"\(Note\s+(\d+)\)", r"(Note_\1)", line, flags=re.I)
    tokens = re.sub(r"\$\s+", "$", protected).split()
    value_tokens: list[str] = []
    while tokens and re.fullmatch(MONEY, tokens[-1]):
        value_tokens.append(tokens.pop())
    value_tokens.reverse()
    label = " ".join(tokens).replace("(Note_", "(Note ").strip(" $ .:-")
    return label, [parse_money(value) for value in value_tokens]


def is_specific_research_lead_label(label: str) -> bool:
    """Reject generic accounting headings while retaining named entities/activity."""
    gate_label = re.sub(r"\s*\(Note\s+\d+\)\s*$", "", label, flags=re.I).strip()
    return len(gate_label) >= 4 and not GENERIC_LEAD_LABEL.match(gate_label)


def parse_audit_research_leads(page_texts: list[str], *, band_id: str,
                               band_name: str, fiscal_year: str,
                               source_url: str) -> list[dict]:
    """Extract non-public economic-activity leads from audit notes and schedules.

    A match is deliberately a research prompt, not evidence of an operating
    project. It stays non-publishable until external sources establish what the
    accounting entity represents and the Nation's relationship to it.
    """
    records: dict[str, dict] = {}
    for page_number, page_text in enumerate(page_texts, 1):
        context = _lead_context(page_text)
        if not context:
            continue
        raw_lines = [re.sub(r"\s+", " ", line).strip() for line in page_text.splitlines() if line.strip()]
        lines: list[str] = []
        index = 0
        while index < len(raw_lines):
            line = raw_lines[index]
            if (index + 1 < len(raw_lines)
                    and (LEAD_PREFIX.search(line) or ENTITY_TERMS.search(line))
                    and re.fullmatch(rf"{MONEY}(?:\s+{MONEY})?", raw_lines[index + 1])):
                line = f"{line} {raw_lines[index + 1]}"
                index += 1
            lines.append(line)
            index += 1
        for line in lines:
            label, values = _split_label_values(line)
            if not values:
                continue
            label = re.sub(r"^(?:note\s+\d+\s*[-:]?\s*)", "", label, flags=re.I).strip(" .:-")
            if not is_specific_research_lead_label(label):
                continue
            if not (LEAD_PREFIX.search(label) or ENTITY_TERMS.search(label)):
                continue
            if len(values) <= 2 and values and all(value is not None and 1900 <= value <= 2100 for value in values):
                continue
            current_index, comparative_index = _amount_indexes(page_text, fiscal_year, len(values))
            current = values[current_index] if current_index < len(values) else None
            comparative = values[comparative_index] if comparative_index is not None and comparative_index < len(values) else None
            if current is not None and comparative is not None and 1900 <= current <= 2100 and 1900 <= comparative <= 2100:
                continue
            if current is not None and 1900 <= current <= 2100 and re.search(r"\b(?:19|20)\d{2}\b", label):
                continue
            if current is None and comparative is None:
                continue
            key = lead_key(label)
            if not key:
                continue
            record = records.setdefault(key, {
                "id": f"audit-lead-{band_id}-{fiscal_year}-{key}",
                "firstNationIds": [str(band_id)],
                "community": band_name,
                "fiscalYear": fiscal_year,
                "originalLabel": label,
                "leadType": _line_lead_context(label, context),
                "currentYearAmount": current,
                "comparativeAmount": comparative,
                "sourceDocument": source_record(source_url, band_name, fiscal_year, date.today().isoformat()),
                "sourceReferences": [],
                "extractionConfidence": "medium",
                "researchStatus": "pending_external_verification",
                "publishable": False,
                "researchQuestions": [
                    "What project, business, asset, or activity does this accounting entity represent?",
                    "What is the First Nation's publicly documented involvement?",
                    "Are ownership, partners, status, and establishment date publicly disclosed?",
                ],
            })
            reference = {"pdfPage": page_number, "table": context, "originalText": line}
            if reference not in record["sourceReferences"]:
                record["sourceReferences"].append(reference)

        for ownership in re.finditer(
                r"(?:First Nation|Nation)\s+has\s+(?:an?\s+)?(?:(\d+(?:\.\d+)?)%\s+)?"
                r"(?:ownership\s+)?interest\s+in\s+(.+?)(?:\.|;|\n)", page_text, re.I | re.S):
            entities = re.split(r"\s+(?:and|&)\s+|,", re.sub(r"\s+", " ", ownership.group(2)))
            for entity in entities:
                entity = entity.strip(" .:-")
                if not ENTITY_TERMS.search(entity):
                    continue
                key = lead_key(entity)
                record = records.setdefault(key, {
                    "id": f"audit-lead-{band_id}-{fiscal_year}-{key}",
                    "firstNationIds": [str(band_id)], "community": band_name,
                    "fiscalYear": fiscal_year, "originalLabel": entity,
                    "leadType": _line_lead_context(entity, context),
                    "currentYearAmount": None, "comparativeAmount": None,
                    "sourceDocument": source_record(source_url, band_name, fiscal_year, date.today().isoformat()),
                    "sourceReferences": [], "extractionConfidence": "high",
                    "researchStatus": "pending_external_verification", "publishable": False,
                    "researchQuestions": [
                        "What project, business, asset, or activity does this accounting entity represent?",
                        "What is the First Nation's publicly documented involvement?",
                        "Are ownership, partners, status, and establishment date publicly disclosed?",
                    ],
                })
                if ownership.group(1):
                    record["ownershipPercentageReported"] = float(ownership.group(1))
                reference = {"pdfPage": page_number, "table": context,
                             "originalText": re.sub(r"\s+", " ", ownership.group(0)).strip()}
                if reference not in record["sourceReferences"]:
                    record["sourceReferences"].append(reference)
    return sorted(records.values(), key=lambda row: (row["leadType"], row["originalLabel"]))


def add_cross_year_analysis(leads: list[dict], scanned_years: dict[str, list[str]] | None = None) -> None:
    """Annotate audit leads without inferring why an accounting balance changed."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in leads:
        groups.setdefault((str(row["firstNationIds"][0]), lead_key(row["originalLabel"])), []).append(row)
    for rows in groups.values():
        rows.sort(key=lambda row: str(row["fiscalYear"]))
        for index, row in enumerate(rows):
            prior = rows[index - 1] if index else None
            current = row.get("currentYearAmount")
            previous = prior.get("currentYearAmount") if prior else None
            if prior is None:
                row["crossYearSignal"] = "first_detected_in_scanned_years"
            elif isinstance(current, int) and isinstance(previous, int):
                change = current - previous
                row["priorFiscalYear"] = prior["fiscalYear"]
                row["priorYearAmount"] = previous
                row["amountChange"] = change
                row["crossYearSignal"] = "increased" if change > 0 else "decreased" if change < 0 else "unchanged"
        band_id = str(rows[0]["firstNationIds"][0])
        observed = {str(row["fiscalYear"]) for row in rows}
        later_missing = [year for year in (scanned_years or {}).get(band_id, [])
                         if year > str(rows[-1]["fiscalYear"]) and year not in observed]
        if later_missing:
            rows[-1]["notDetectedInLaterScannedYears"] = sorted(later_missing)


def add_disclosure(records: dict[str, dict], *, band_id: str, band_name: str,
                   fiscal_year: str, source_url: str, page: int, table: str,
                   name: str, amounts: dict[str, int] | None = None) -> None:
    name = canonical_project_name(name)
    if not name or name.lower() in {"capital project", "capital projects"}:
        return
    key = disclosure_key(name)
    record = records.setdefault(key, {
        "id": f"{band_id}-{fiscal_year}-{key}",
        "firstNationIds": [str(band_id)],
        "fiscalYear": fiscal_year,
        "category": project_category(name),
        "name": name,
        "description": "Named as a capital project in the audited financial statement.",
        "amounts": {},
        "sourceReferences": [],
        "sources": [source_record(source_url, band_name, fiscal_year, date.today().isoformat())],
    })
    for amount_type, amount in (amounts or {}).items():
        # Parenthesized values in deferred-revenue schedules are accounting
        # adjustments, not a negative amount spent on or received by a project.
        if amount is not None and amount >= 0:
            record["amounts"][amount_type] = amount
    reference = {"pdfPage": page, "table": table}
    if reference not in record["sourceReferences"]:
        record["sourceReferences"].append(reference)


def parse_project_disclosures(page_texts: list[str], *, band_id: str,
                              band_name: str, fiscal_year: str,
                              source_url: str) -> list[dict]:
    records: dict[str, dict] = {}
    for page_number, page_text in enumerate(page_texts, 1):
        raw_lines = [re.sub(r"\s+", " ", line).strip() for line in page_text.splitlines() if line.strip()]
        lines: list[str] = []
        index = 0
        while index < len(raw_lines):
            line = raw_lines[index]
            if line.lower().endswith("- isc") and index + 1 < len(raw_lines) and re.match(r"Capital Project\b", raw_lines[index + 1], re.I):
                line = f"{line} {raw_lines[index + 1]}"
                index += 1
            lines.append(line)
            index += 1
        page_lower = page_text.lower()
        restricted_context = "restricted cash" in page_lower
        deferred_context = "deferred revenue" in page_lower
        for line in lines:
            restricted = re.match(
                rf"Capital\s+project\s*-\s*(.+?)\s+({MONEY})\s+({MONEY})$",
                line,
                flags=re.I,
            )
            if restricted and restricted_context:
                add_disclosure(
                    records,
                    band_id=band_id,
                    band_name=band_name,
                    fiscal_year=fiscal_year,
                    source_url=source_url,
                    page=page_number,
                    table="Restricted cash",
                    name=restricted.group(1),
                    amounts={"restrictedCash": parse_money(restricted.group(2))},
                )
                continue

            deferred = re.match(
                rf"(.+?\s+-\s+ISC\s+Capital\s+Project)\s+({MONEY})\s+({MONEY})\s+({MONEY})\s+({MONEY})$",
                line,
                flags=re.I,
            )
            if deferred and deferred_context:
                values = [parse_money(deferred.group(index)) for index in range(2, 6)]
                add_disclosure(
                    records,
                    band_id=band_id,
                    band_name=band_name,
                    fiscal_year=fiscal_year,
                    source_url=source_url,
                    page=page_number,
                    table="Deferred revenue",
                    name=deferred.group(1),
                    amounts={
                        "deferredRevenueOpening": values[0],
                        "fundingReceived": values[1],
                        "revenueRecognized": values[2],
                        "deferredRevenueClosing": values[3],
                    },
                )

        narrative = re.search(
            r"Recent capital projects include\s+(.+?)(?:\.|\n\n|Social development)",
            page_text,
            flags=re.I | re.S,
        )
        if narrative:
            names = re.sub(r"\s+", " ", narrative.group(1)).replace(" and ", ", ").split(",")
            for name in names:
                add_disclosure(
                    records,
                    band_id=band_id,
                    band_name=band_name,
                    fiscal_year=fiscal_year,
                    source_url=source_url,
                    page=page_number,
                    table="Segment disclosure",
                    name=name,
                )

    return sorted(records.values(), key=lambda row: (row["category"], row["name"]))


def normalized_pdf_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.urlencode(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def fetch_pdf(url: str, retries: int = 3) -> bytes:
    error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(normalized_pdf_url(url), headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=45) as response:
                data = response.read()
            if not data.startswith(b"%PDF"):
                raise ValueError("Source did not return a PDF")
            return data
        except Exception as exc:  # pragma: no cover - network behavior
            error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(str(error))


def extract_one(task: dict) -> dict:
    try:
        import pdfplumber

        data = fetch_pdf(task["sourceUrl"])
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = [page.extract_text(x_tolerance=2, y_tolerance=3) or "" for page in pdf.pages]
        rows = parse_project_disclosures(
            pages,
            band_id=task["bandId"],
            band_name=task["bandName"],
            fiscal_year=task["fiscalYear"],
            source_url=task["sourceUrl"],
        )
        leads = parse_audit_research_leads(
            pages,
            band_id=task["bandId"],
            band_name=task["bandName"],
            fiscal_year=task["fiscalYear"],
            source_url=task["sourceUrl"],
        )
        status = "extracted" if rows or leads else "no_disclosures"
        return {**task, "status": status, "records": rows, "researchLeads": leads}
    except Exception as exc:  # pragma: no cover - network behavior
        return {**task, "status": "failed", "reason": str(exc), "records": [], "researchLeads": []}


def scan_tasks(capital: dict, all_years: bool) -> list[dict]:
    tasks = []
    for band_id, band in capital.get("bands", {}).items():
        eligible = [
            (year, row) for year, row in band.get("years", {}).items()
            if row.get("parseStatus") in {"parsed", "manual_review"}
            and row.get("sourceUrl")
        ]
        eligible.sort(reverse=True)
        for fiscal_year, row in (eligible if all_years else eligible[:1]):
            tasks.append({
                "bandId": str(band_id),
                "bandName": band.get("name") or f"First Nation {band_id}",
                "fiscalYear": fiscal_year,
                "sourceUrl": row["sourceUrl"],
            })
    return tasks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capital", default=str(ROOT / "capital-data.json"))
    parser.add_argument("--projects", default=str(ROOT / "projects-data.json"))
    parser.add_argument("--research-leads", default=str(ROOT / "project-research-leads.json"))
    parser.add_argument("--report", default=str(ROOT / "project-disclosure-report.json"))
    parser.add_argument("--all-years", action="store_true")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    capital = json.loads(Path(args.capital).read_text(encoding="utf-8"))
    projects_path = Path(args.projects)
    projects = json.loads(projects_path.read_text(encoding="utf-8"))
    tasks = scan_tasks(capital, args.all_years)
    if args.limit:
        tasks = tasks[: args.limit]

    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(extract_one, task): task for task in tasks}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(
                f"{result['bandName']} {result['fiscalYear']}: {result['status']} "
                f"({len(result['records'])} disclosures, {len(result.get('researchLeads', []))} research leads)"
            )

    previous = projects.get("financialDisclosures", [])
    scanned = {(row["bandId"], row["fiscalYear"]) for row in results if row["status"] != "failed"}
    preserved = [
        row for row in previous
        if not any((str(band_id), str(row.get("fiscalYear"))) in scanned for band_id in row.get("firstNationIds", []))
    ]
    extracted = [record for result in results for record in result["records"]]
    by_id = {row["id"]: row for row in [*preserved, *extracted]}
    projects["financialDisclosures"] = sorted(
        by_id.values(), key=lambda row: (str(row.get("fiscalYear", "")), row["name"]), reverse=True
    )
    extracted_leads = [lead for result in results for lead in result.get("researchLeads", [])]
    scanned_years: dict[str, list[str]] = {}
    for result in results:
        if result["status"] != "failed":
            scanned_years.setdefault(str(result["bandId"]), []).append(str(result["fiscalYear"]))
    add_cross_year_analysis(extracted_leads, scanned_years)
    research_path = Path(args.research_leads)
    research_payload = (
        json.loads(research_path.read_text(encoding="utf-8"))
        if research_path.exists()
        else {"auditResearchLeads": []}
    )
    previous_leads = research_payload.get("auditResearchLeads", [])
    preserved_leads = [
        row for row in previous_leads
        if row.get("verificationStatus") == "verified"
        or not any((str(band_id), str(row.get("fiscalYear"))) in scanned for band_id in row.get("firstNationIds", []))
    ]
    leads_by_id = {row["id"]: row for row in [*extracted_leads, *preserved_leads]}
    research_payload["auditResearchLeads"] = sorted(
        leads_by_id.values(), key=lambda row: (str(row.get("fiscalYear", "")), row.get("originalLabel", "")), reverse=True
    )
    research_payload["auditResearchPolicy"] = {
        "description": "Accounting disclosures are research leads only. They are not public project entries until corroborating sources identify the underlying activity and the First Nation's involvement.",
        "publishableByDefault": False,
        "requiredCorroboration": ["Nation or EDC source", "government or corporate source", "credible public announcement"],
        "lastReviewedAt": date.today().isoformat(),
    }
    research_payload["generatedAt"] = date.today().isoformat()
    research_payload["leadCount"] = len(research_payload["auditResearchLeads"])
    projects.pop("auditResearchLeads", None)
    projects.pop("auditResearchPolicy", None)
    projects["financialDisclosureAudit"] = {
        "description": "Project names and amounts explicitly disclosed in audited financial statements. These records do not infer approval, construction status, total project cost, or completion.",
        "lastReviewedAt": date.today().isoformat(),
        "sourcePriority": "Audited financial statement notes and schedules",
        "documentsAttempted": len(results),
        "documentsExtracted": sum(row["status"] == "extracted" for row in results),
        "recordsExtracted": len(extracted),
        "researchLeadsGenerated": len(extracted_leads),
        "failures": sum(row["status"] == "failed" for row in results),
    }
    projects["generatedAt"] = date.today().isoformat()
    projects_path.write_text(json.dumps(projects, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    research_path.write_text(json.dumps(research_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "generatedAt": date.today().isoformat(),
        "mode": "all-years" if args.all_years else "latest-publishable-year",
        "documentsAttempted": len(results),
        "recordsExtracted": len(extracted),
        "researchLeadsGenerated": len(extracted_leads),
        "results": sorted(({
            key: value for key, value in row.items() if key not in {"records", "researchLeads"}
        } | {
            "recordsExtracted": len(row.get("records", [])),
            "researchLeadsGenerated": len(row.get("researchLeads", [])),
        } for row in results), key=lambda row: (row["bandName"], row["fiscalYear"])),
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
