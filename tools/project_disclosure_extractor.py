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
MONEY = r"(?:\(?[\d,]+\)?|-)"
USER_AGENT = "OpenBand/2.0 (https://openband.ca; public-records research)"


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
    }
    return aliases.get(cleaned.lower(), cleaned)


def disclosure_key(name: str) -> str:
    value = canonical_project_name(name).lower()
    replacements = {"elementary school": "elementary school repairs"}
    return slugify(replacements.get(value, value))


def source_record(url: str, band_name: str, fiscal_year: str, checked_at: str) -> dict:
    return {
        "name": f"{band_name} {fiscal_year} audited financial statement",
        "url": url,
        "checkedAt": checked_at,
    }


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
        return {**task, "status": "extracted" if rows else "no_disclosures", "records": rows}
    except Exception as exc:  # pragma: no cover - network behavior
        return {**task, "status": "failed", "reason": str(exc), "records": []}


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
            print(f"{result['bandName']} {result['fiscalYear']}: {result['status']} ({len(result['records'])})")

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
    projects["financialDisclosureAudit"] = {
        "description": "Project names and amounts explicitly disclosed in audited financial statements. These records do not infer approval, construction status, total project cost, or completion.",
        "lastReviewedAt": date.today().isoformat(),
        "sourcePriority": "Audited financial statement notes and schedules",
        "documentsAttempted": len(results),
        "documentsExtracted": sum(row["status"] == "extracted" for row in results),
        "recordsExtracted": len(extracted),
        "failures": sum(row["status"] == "failed" for row in results),
    }
    projects["generatedAt"] = date.today().isoformat()
    projects_path.write_text(json.dumps(projects, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "generatedAt": date.today().isoformat(),
        "mode": "all-years" if args.all_years else "latest-publishable-year",
        "documentsAttempted": len(results),
        "recordsExtracted": len(extracted),
        "results": sorted(results, key=lambda row: (row["bandName"], row["fiscalYear"])),
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
