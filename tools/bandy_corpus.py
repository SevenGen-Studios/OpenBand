"""Resumable, research-only extraction of the complete OpenBand filing inventory.

Run with --all-nations to explicitly authorize the larger inventory. No commit,
website build, production merge, paid API, or source-figure correction is used.
"""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import json
import logging
from pathlib import Path
import re
import sqlite3
import time
import urllib.error

from tools import bandy_financial as financial
from tools.capital_parser import fetch_pdf, is_audited_statement, normalize_pdf_url

CORPUS_VERSION = "bandy_corpus_v1"


def atomic_json(path, value, compressed=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    opener = gzip.open if compressed else open
    with opener(temporary, "wt", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        stream.write("\n")
    # OneDrive/Windows scanners briefly hold the destination open without delete
    # sharing. A transient progress-file lock must not abort a full corpus run.
    for attempt in range(40):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(.05 * min(attempt+1, 5))


def read_checkpoint(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def inventory(data, capital):
    nations, documents = [], []
    seen = set()
    for band in data["bands"]:
        band_id = str(band["id"])
        audited = [f for f in band.get("filings", []) if is_audited_statement(f)]
        nation = {"bandId": band_id, "bandName": band["name"], "province": band.get("province"),
                  "missingFilingYears": [], "documentKeys": []}
        for filing in audited:
            source = filing.get("href")
            if not source or filing.get("posted") is False:
                nation["missingFilingYears"].append(filing["year"])
                continue
            if not re.fullmatch(r"20\d{2}-20\d{2}", filing["year"]):
                raise ValueError(f"Unsupported fiscal year: {filing['year']}")
            key = financial.digest([band_id, filing["year"], normalize_pdf_url(source)])
            if key in seen:
                continue
            seen.add(key)
            summary = capital.get("bands", {}).get(band_id, {}).get("years", {}).get(filing["year"], {})
            expected_hash = filing.get("sha256")
            if not expected_hash and summary.get("sourceUrl") == source:
                expected_hash = summary.get("sha256")
            document = {"documentKey": key, "bandId": band_id, "bandName": band["name"],
                        "province": band.get("province"), "fiscalYear": filing["year"],
                        "sourceUrl": source, "expectedSha256": expected_hash,
                        "documentType": filing["docType"]}
            documents.append(document)
            nation["documentKeys"].append(key)
        nation["missingFilingYears"] = sorted(set(nation["missingFilingYears"]))
        nations.append(nation)
    # Give every Nation its most recent filing first, then process history.
    documents.sort(key=lambda d: (-int(d["fiscalYear"][-4:]), d["bandId"]))
    return {"schemaVersion": 1, "scope": "all_nations_in_OpenBand_inventory",
            "nations": nations, "documents": documents}


def extraction_revision():
    paths = [Path(__file__), Path(financial.__file__), Path("tools/capital_parser.py")]
    return hashlib.sha256(b"".join(p.read_bytes() for p in paths)).hexdigest()


def mark_records(result, flag):
    for record in result["records"]:
        record["validationFlags"] = sorted(set(record["validationFlags"] + [flag]))
        record["validationStatus"] = "manual_review"


def process_document(document, output, revision):
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    output = Path(output)
    key = document["documentKey"]
    checkpoint = output / "document-results" / f"{key}.json.gz"
    cached = output / "pdf-cache" / f"{key}.pdf"
    started = time.monotonic()
    entry = {"document": deepcopy(document), "revision": revision, "status": "processing", "result": None}
    try:
        if cached.exists():
            raw = cached.read_bytes()
        else:
            sample = Path("tmp/bandy-sample") / f"{document['bandId']}-{document['fiscalYear']}.pdf"
            raw = sample.read_bytes() if sample.exists() else None
            if raw is None:
                for attempt in range(3):
                    try:
                        raw = fetch_pdf(document["sourceUrl"])
                        break
                    except (OSError, urllib.error.URLError):
                        if attempt == 2:
                            raise
                        time.sleep(2 * (attempt + 1))
            if not raw.lstrip().startswith(b"%PDF"):
                raise ValueError("Source returned non-PDF content")
            cached.parent.mkdir(parents=True, exist_ok=True)
            with cached.open("xb") as stream:
                stream.write(raw)
        actual_hash = hashlib.sha256(raw).hexdigest()
        entry["document"].update({"sha256": actual_hash, "byteSize": len(raw),
                                  "retrievedAt": datetime.now(timezone.utc).isoformat(),
                                  "hashStatus": "matches_previous" if document.get("expectedSha256") == actual_hash
                                  else "changed_since_previous" if document.get("expectedSha256") else "first_observation"})
        fixture = financial.read_pdf(raw, entry["document"])
        entry["nativePageCount"] = len(fixture["pages"])
        entry["nativeStatementPages"] = [p["page"] for p in fixture["pages"] if financial.is_statement(p)]
        entry["nativeCharacterCount"] = sum(len(p["text"]) for p in fixture["pages"])
        result = financial.extract_fixture(fixture)
        if entry["document"]["hashStatus"] == "changed_since_previous":
            mark_records(result, "source_hash_changed")
        entry["result"] = result
        count = len(result["records"])
        checked = sum(r["validationStatus"] == "machine_checked" for r in result["records"])
        entry["status"] = "extracted" if checked else "manual_review" if count else "no_structured_records"
        entry["requiresOcr"] = not entry["nativeStatementPages"] or entry["nativeCharacterCount"] < 400
        if entry["requiresOcr"]:
            entry["limitation"] = "No coordinate-confirmed native statement pages; scanned/layout recovery required"
    except Exception as exc:
        entry["status"] = "failed"
        entry["error"] = f"{type(exc).__name__}: {exc}"
    entry["elapsedSeconds"] = round(time.monotonic() - started, 2)
    atomic_json(checkpoint, entry, compressed=True)
    return {"documentKey": key, "bandId": document["bandId"], "fiscalYear": document["fiscalYear"],
            "status": entry["status"], "recordCount": len((entry["result"] or {}).get("records", [])),
            "checkedRecordCount": sum(r["validationStatus"] == "machine_checked"
                                      for r in (entry["result"] or {}).get("records", [])),
            "requiresOcr": entry.get("requiresOcr", False), "elapsedSeconds": entry["elapsedSeconds"],
            **({"error": entry["error"]} if entry.get("error") else {})}


def observation_key(record):
    return record["bandId"], record["fiscalYear"], record["metric"], record["dimension"]


def resolve_observations(records):
    """Corroborated equal values coalesce; conflicting values remain quarantined."""
    records = deepcopy(records)
    identifiers = Counter(r["recordId"] for r in records)
    for record in records:
        if identifiers[record["recordId"]] > 1:
            record["validationFlags"] = sorted(set(record["validationFlags"] + ["duplicate_observation_id"]))
            record["validationStatus"] = "manual_review"
    groups = defaultdict(list)
    for record in records:
        groups[observation_key(record)].append(record)
    conflicts = []
    for key, matches in groups.items():
        if len({r["value"] for r in matches}) > 1:
            conflicts.append({"bandId": key[0], "fiscalYear": key[1], "metric": key[2], "dimension": key[3],
                              "observations": [{"recordId": r["recordId"], "value": r["value"],
                                                "sourceDocument": r["sourceDocument"], "sourcePage": r["sourcePage"]}
                                               for r in matches]})
            for record in matches:
                record["validationFlags"] = sorted(set(record["validationFlags"] + ["cross_document_conflict"]))
                record["validationStatus"] = "manual_review"
    # A conflict in a component also quarantines its derived subtotals.
    flagged = {(r["sourceDocumentSha256"], r["fiscalYear"], financial.digest(ref))
               for r in records if r["validationStatus"] == "manual_review" for ref in r["sourceReferences"]}
    for record in records:
        if record["extractionBasis"] != "reported" and any(
            (record["sourceDocumentSha256"], record["fiscalYear"], financial.digest(ref)) in flagged
            for ref in record["sourceReferences"]
        ):
            record["validationFlags"] = sorted(set(record["validationFlags"] + ["component_requires_review"]))
            record["validationStatus"] = "manual_review"
    canonical, links = [], []
    for matches in groups.values():
        chosen = max(matches, key=lambda r: (
            bool(r["sourceReferences"] and r["sourcePage"]),
            r["validationStatus"] == "machine_checked", not r["comparative"],
            r["sourceFiscalYear"], r["recordId"]))
        canonical.append(chosen)
        links.extend({"recordId": chosen["recordId"], "observationId": r["recordId"],
                      "agrees": r["value"] == chosen["value"]} for r in matches)
    canonical.sort(key=observation_key)
    return records, canonical, links, conflicts


def write_jsonl(path, rows):
    with Path(path).open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")


def finalize(output, manifest):
    output = financial.safe_output_directory(output)
    final = output / "export"
    if final.exists():
        raise FileExistsError("Final export already exists; preserve it and choose another run directory")
    entries = [read_checkpoint(output / "document-results" / f"{d['documentKey']}.json.gz")
               for d in manifest["documents"]]
    raw_records = [r for e in entries for r in (e["result"] or {}).get("records", [])]
    # A PDF reused for different Nations is suspicious even if its tables balance.
    source_bands = defaultdict(set)
    for r in raw_records:
        source_bands[r["sourceDocumentSha256"]].add(r["bandId"])
    for r in raw_records:
        if len(source_bands[r["sourceDocumentSha256"]]) > 1:
            r["validationFlags"] = sorted(set(r["validationFlags"] + ["document_shared_across_nations"]))
            r["validationStatus"] = "manual_review"
    observations, records, links, conflicts = resolve_observations(raw_records)
    candidates = [r for r in records if not r["sourceReferences"] or not r["sourcePage"]]
    records = [r for r in records if r["sourceReferences"] and r["sourcePage"]]
    checked = [r for r in records if r["validationStatus"] == "machine_checked"]
    notes = [n for e in entries for n in (e["result"] or {}).get("notes", [])]
    entities = [n for e in entries for n in (e["result"] or {}).get("entities", [])]
    by_band, entries_by_band = defaultdict(list), defaultdict(list)
    for r in records:
        by_band[r["bandId"]].append(r)
    for e in entries:
        entries_by_band[e["document"]["bandId"]].append(e)
    coverage = []
    for nation in manifest["nations"]:
        group = by_band[nation["bandId"]]
        attempts = entries_by_band[nation["bandId"]]
        coverage.append({**nation, "availableDocuments": len(attempts),
                         "processedDocuments": sum(e["result"] is not None for e in attempts),
                         "failedDocuments": sum(e["status"] == "failed" for e in attempts),
                         "noRecordDocuments": sum(e["status"] == "no_structured_records" for e in attempts),
                         "requiresOcrDocuments": sum(e.get("requiresOcr", False) for e in attempts),
                         "ocrRecoveredDocuments": sum(bool(e.get("ocrAddedRecords")) for e in attempts),
                         "recordCount": len(group),
                         "checkedRecordCount": sum(r["validationStatus"] == "machine_checked" for r in group),
                         "yearsWithRecords": sorted({r["fiscalYear"] for r in group}),
                         "metrics": sorted({r["metric"] for r in group}),
                         "unavailableMetrics": sorted(set(financial.METRICS) - {r["metric"] for r in group}),
                         "yearCoverage": [{"fiscalYear": year,
                             "metrics": sorted({r["metric"] for r in group if r["fiscalYear"] == year}),
                             "unavailableMetrics": sorted(set(financial.METRICS) - {r["metric"] for r in group if r["fiscalYear"] == year}),
                             "checkedRecordCount": sum(r["validationStatus"] == "machine_checked" for r in group if r["fiscalYear"] == year)}
                             for year in sorted({r["fiscalYear"] for r in group} | {e["document"]["fiscalYear"] for e in attempts})],
                         "status": "no_posted_audited_source" if not attempts else
                                   "records_available" if group else "extraction_requires_recovery"})
    summary = {"schemaVersion": 1, "purpose": "research_only", "parser": CORPUS_VERSION,
               "generated": datetime.now(timezone.utc).isoformat(), "nationCount": len(coverage),
               "documentCount": len(entries), "documentStatuses": dict(Counter(e["status"] for e in entries)),
               "nationsWithRecords": sum(bool(n["recordCount"]) for n in coverage),
               "nationsWithCheckedRecords": sum(bool(n["checkedRecordCount"]) for n in coverage),
               "observationCount": len(observations), "recordCount": len(records),
               "checkedRecordCount": len(checked), "reviewRecordCount": len(records)-len(checked),
               "unbackedCandidateCount": len(candidates),
               "duplicateObservationCount": len(observations)-len({r["recordId"] for r in observations}),
               "conflictingMetricCount": len(conflicts), "noteCount": len(notes), "entityCount": len(entities),
               "requiresOcrDocuments": sum(e.get("requiresOcr", False) for e in entries),
               "ocrAttemptedDocuments": sum(bool(e.get("recovery", {}).get("ocr")) for e in entries),
               "ocrRecoveredDocuments": sum(bool(e.get("ocrAddedRecords")) for e in entries),
               "ocrAddedObservations": sum(e.get("ocrAddedRecords", 0) for e in entries),
               "metricCoverage": [{"metric": metric,
                    "recordCount": sum(r["metric"] == metric for r in records),
                    "checkedRecordCount": sum(r["metric"] == metric for r in checked),
                    "nationCount": len({r["bandId"] for r in records if r["metric"] == metric})}
                    for metric in sorted(set(financial.METRICS) | {r["metric"] for r in records})],
               "sourceHashChanges": sum(e["document"].get("hashStatus") == "changed_since_previous" for e in entries),
               "validationFlags": dict(Counter(flag for r in records for flag in r["validationFlags"]))}
    final.mkdir()
    write_jsonl(final / "observations.jsonl", observations)
    write_jsonl(final / "financial-records.jsonl", records)
    write_jsonl(final / "unbacked-candidates.jsonl", candidates)
    write_jsonl(final / "checked-records.jsonl", checked)
    write_jsonl(final / "review-records.jsonl", (r for r in records if r["validationStatus"] != "machine_checked"))
    write_jsonl(final / "note-disclosures.jsonl", notes)
    write_jsonl(final / "entity-disclosures.jsonl", entities)
    write_jsonl(final / "observation-links.jsonl", links)
    write_jsonl(final / "document-report.jsonl", ({k: v for k, v in e.items() if k != "result"} | {
        "recordCount": len((e["result"] or {}).get("records", [])),
        "checks": (e["result"] or {}).get("checks", []), "issues": (e["result"] or {}).get("issues", {})} for e in entries))
    atomic_json(final / "summary.json", summary)
    atomic_json(final / "nation-coverage.json", coverage)
    atomic_json(final / "conflicts.json", conflicts)
    with closing(sqlite3.connect(final / "financial.sqlite")) as db:
        for table in ("observations", "financial_records"):
            primary = " PRIMARY KEY" if table == "financial_records" else ""
            db.execute(f"CREATE TABLE {table} (record_id TEXT{primary}, band_id TEXT NOT NULL, fiscal_year TEXT NOT NULL, metric TEXT NOT NULL, dimension TEXT NOT NULL, value REAL NOT NULL, source_document TEXT NOT NULL, source_page INTEGER, validation_status TEXT NOT NULL, record_json TEXT NOT NULL)")
            values = observations if table == "observations" else records
            db.executemany(f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?)", [
                (r["recordId"], r["bandId"], r["fiscalYear"], r["metric"], r["dimension"], r["value"],
                 r["sourceDocument"], r["sourcePage"], r["validationStatus"], json.dumps(r, ensure_ascii=False)) for r in values])
            db.execute(f"CREATE INDEX {table}_query ON {table}(band_id, fiscal_year, metric)")
        db.execute("CREATE VIEW checked_financial_records AS SELECT * FROM financial_records WHERE validation_status='machine_checked'")
        db.execute("CREATE INDEX observations_record_id ON observations(record_id)")
        db.execute("CREATE TABLE observation_links (record_id TEXT, observation_id TEXT, agrees INTEGER)")
        db.executemany("INSERT INTO observation_links VALUES (?,?,?)", [(x["recordId"],x["observationId"],x["agrees"]) for x in links])
        db.execute("CREATE TABLE nation_coverage (band_id TEXT PRIMARY KEY, band_name TEXT, province TEXT, status TEXT, record_count INTEGER, checked_record_count INTEGER, coverage_json TEXT)")
        db.executemany("INSERT INTO nation_coverage VALUES (?,?,?,?,?,?,?)", [(n["bandId"],n["bandName"],n["province"],n["status"],n["recordCount"],n["checkedRecordCount"],json.dumps(n)) for n in coverage])
        db.commit()
    lines = ["# All-Nations financial extraction", "", f"Generated {summary['generated']}", "",
             "Research-only data. No production figures or website files were updated.", "",
             f"Attempted all {summary['documentCount']:,} posted audited statements for {summary['nationCount']} Nations in OpenBand's Saskatchewan/Alberta inventory.", "",
             f"{summary['nationsWithRecords']} Nations have structured financial records; {summary['nationsWithCheckedRecords']} have machine-checked records.", "",
             f"{summary['recordCount']:,} distinct metric observations: {summary['checkedRecordCount']:,} machine-checked and {summary['reviewRecordCount']:,} requiring review.",
             f"All {summary['observationCount']:,} original source observations are retained; exact agreements are linked and conflicting values stay flagged.", "",
             "Machine-checked describes automated extraction and accounting checks, not independent verification of every source value.", "",
             f"{summary['unbackedCandidateCount']:,} canonical candidates without coordinate-confirmed page evidence are excluded from financial records and saved separately in `unbacked-candidates.jsonl`.", "",
             "OCR recovery is limited to the first 16 pages of scanned statements. Later scanned notes remain unavailable. Every OCR figure requires manual verification, even when accounting checks pass.", "",
             "Scope is the 117 Nations currently listed in OpenBand (Saskatchewan and Alberta), not every First Nation in Canada.", "",
             "| Nation | Province | Posted audits | Records | Machine-checked | Native OCR candidates |", "| --- | --- | ---: | ---: | ---: | ---: |"]
    lines += [f"| {n['bandName']} | {n['province']} | {n['availableDocuments']} | {n['recordCount']} | {n['checkedRecordCount']} | {n['requiresOcrDocuments']} |" for n in coverage]
    lines += ["", "## Metric coverage", "", "| Metric | Records | Machine-checked | Nations |", "| --- | ---: | ---: | ---: |"]
    lines += [f"| {m['metric']} | {m['recordCount']} | {m['checkedRecordCount']} | {m['nationCount']} |" for m in summary["metricCoverage"]]
    lines += ["", "## Source gaps", ""]
    lines += [f"- {n['bandName']} ({n['bandId']}): {n['status']}" for n in coverage if n['status'] != 'records_available']
    lines += ["", "Use `checked_financial_records` in `financial.sqlite` or `checked-records.jsonl` for the checked subset.",
              "`financial-records.jsonl` includes review records. `observations.jsonl` retains every source version.",
              "`nation-coverage.json` lists every Nation, unavailable metrics, missing filings, and processing failures.",
              "`document-report.jsonl` retains source hashes, source changes, extraction limitations, and accounting checks.",
              "`conflicts.json` lists disagreeing source versions; no source values are overwritten or automatically corrected.",
              "Notes and reporting-entity disclosures remain qualitative records requiring interpretation.", ""]
    (final / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-nations", action="store_true", required=True)
    parser.add_argument("--data", default="data.json")
    parser.add_argument("--capital", default="capital-data.json")
    parser.add_argument("--output", default="research/bandy-financial/all-nations-2026-10-09")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--no-finalize", action="store_true")
    parser.add_argument("--finalize-only", action="store_true", help="Export saved native/OCR checkpoints without rerunning extraction")
    parser.add_argument("--limit", type=int, default=0, help="Diagnostic limit; final full export requires every document")
    args = parser.parse_args()
    if not 1 <= args.workers <= 6:
        parser.error("Use 1-6 local worker processes")
    output = financial.safe_output_directory(args.output)
    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    capital = json.loads(Path(args.capital).read_text(encoding="utf-8"))
    manifest = inventory(data, capital)
    manifest["inventorySha256"] = hashlib.sha256(Path(args.data).read_bytes()).hexdigest()
    manifest_path = output / "manifest.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
        raise ValueError("Inventory changed; preserve this run and select a new output directory")
    if not manifest_path.exists():
        atomic_json(manifest_path, manifest)
    if args.finalize_only:
        if args.limit or args.no_finalize:
            parser.error("--finalize-only cannot be combined with --limit or --no-finalize")
        print(json.dumps(finalize(output, manifest), ensure_ascii=False), flush=True)
        return
    revision = extraction_revision()
    documents = manifest["documents"]
    if args.limit:
        documents = documents[:args.limit]
    completed, pending = [], []
    for document in documents:
        checkpoint = output / "document-results" / f"{document['documentKey']}.json.gz"
        if checkpoint.exists():
            saved = read_checkpoint(checkpoint)
            if saved.get("revision") == revision and not (args.retry_failed and saved["status"] == "failed"):
                completed.append({"documentKey": document["documentKey"], "bandId": document["bandId"],
                                  "fiscalYear": document["fiscalYear"], "status": saved["status"],
                                  "recordCount": len((saved["result"] or {}).get("records", [])),
                                  "checkedRecordCount": sum(r["validationStatus"] == "machine_checked" for r in (saved["result"] or {}).get("records", [])),
                                  "requiresOcr": saved.get("requiresOcr", False)})
                continue
        pending.append(document)
    print(f"Inventory: {len(manifest['nations'])} Nations, {len(manifest['documents'])} posted audits; {len(completed)} completed, {len(pending)} pending", flush=True)
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process_document, document, str(output), revision): document for document in pending}
        for future in as_completed(futures):
            progress = future.result()
            completed.append(progress)
            summary = {"completedDocuments": len(completed), "totalDocuments": len(documents),
                       "recordCount": sum(p["recordCount"] for p in completed),
                       "checkedObservations": sum(p["checkedRecordCount"] for p in completed),
                       "statuses": dict(Counter(p["status"] for p in completed)),
                       "requiresOcrDocuments": sum(p["requiresOcr"] for p in completed),
                       "elapsedSeconds": round(time.monotonic()-started, 1), "latest": progress}
            atomic_json(output / "progress.json", summary)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
    if not args.no_finalize and not args.limit:
        print("Writing full research exports...", flush=True)
        print(json.dumps(finalize(output, manifest), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
