"""Bounded, read-only financial enrichment and source-backed research exports.

Reuses Community Capital's statement parser and validation. No production merge
or AI fallback is provided. Coordinate-confirmed actual columns are projected
one at a time so the existing parser can also read comparative years safely.
"""

import argparse
from collections import defaultdict
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sqlite3
from urllib.parse import parse_qs, urlparse

from tools.capital_parser import (
    FINAL_SURPLUS_RE, POSITION_RE, clean_text, expected_fiscal_year, fetch_pdf,
    is_primary_operations_page, parse_money, parse_page_texts, pdfplumber,
)

PARSER_VERSION = "bandy_financial_v1"
AMOUNT = re.compile(r"(?:\(?-?\d[\d,]*(?:\.\d{1,2})?\)?|-)")
METRICS = (
    "totalRevenue", "totalExpenses", "annualSurplusDeficit", "cash",
    "restrictedCash", "investments", "portfolioInvestments",
    "guaranteedInvestmentCertificates", "businessInvestments",
    "jointVentureInvestments", "accountsReceivable", "totalFinancialAssets",
    "totalNonFinancialAssets", "totalAssets", "tangibleCapitalAssets",
    "accountsPayable", "deferredRevenue", "longTermDebt",
    "currentPortionLongTermDebt", "termLoansSubjectToRefinancing",
    "loansPayable", "bankIndebtedness", "capitalLeaseObligations",
    "currentCapitalLeaseObligations", "assetRetirementObligations",
    "contaminatedSiteLiability", "totalLiabilities", "accumulatedSurplus",
    "netFinancialAssetsDebt", "administrativeExpenses", "programExpenses",
    "governmentRevenue", "ownSourceRevenue", "businessRevenue",
    "investmentIncome", "saskatchewanGovernmentRevenue",
)
NEW_METRICS = {
    "portfolioInvestments", "guaranteedInvestmentCertificates",
    "businessInvestments", "jointVentureInvestments", "totalNonFinancialAssets",
    "currentPortionLongTermDebt", "termLoansSubjectToRefinancing",
    "loansPayable", "bankIndebtedness", "capitalLeaseObligations",
    "currentCapitalLeaseObligations", "assetRetirementObligations",
    "contaminatedSiteLiability", "administrativeExpenses", "programExpenses",
    "saskatchewanGovernmentRevenue",
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def lines_from_words(words):
    lines = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if not lines or abs(word["top"] - lines[-1][0]["top"]) > 2.5:
            lines.append([word])
        else:
            lines[-1].append(word)
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def is_statement(page):
    text = page["text"]
    # Some auditors place the date caption beside a two-line statement title.
    # Remove only that caption for title detection; original text/word boxes
    # remain the evidence used for amounts and page references.
    title_lines = [re.sub(r"\s+(?:for the year ended|as at)\b.*$", "", clean_text(line), flags=re.I)
                   for line in text.splitlines()[:8] if line.strip()]
    title_lines = [re.sub(r"\s+(?:March|April|June|September|December)\s+\d{1,2}(?:,?\s+20\d{2})?$", "", line, flags=re.I)
                   for line in title_lines]
    detection_text = "\n".join(title_lines + [a + " " + b for a, b in zip(title_lines, title_lines[1:])])
    header = "\n".join(text.splitlines()[:8])
    position_title = any(re.fullmatch(
        r"(?:consolidated\s+)?statement of financial position(?:\s*\(continued\))?",
        clean_text(line), re.I) for line in detection_text.splitlines())
    return is_primary_operations_page(text) or is_primary_operations_page(detection_text) or bool(
        position_title and not re.search(r"contents|notes to", header, re.I))


def column_layout(page, fiscal_year):
    """Require explicit year columns; budget and blank cells never shift values."""
    lines = lines_from_words(page.get("words", []))
    for line in lines:
        years = [w for w in line if re.fullmatch(r"20\d{2}", w["text"])]
        if len(years) < 2 or line[0]["top"] > 240:
            continue
        spacing = min(b["x1"]-a["x1"] for a, b in zip(years, years[1:]))
        others = [w for w in line if w not in years]
        # A date caption can share the year-heading baseline if it stays entirely
        # to the left of the numeric columns. Table-of-contents rows cannot pass.
        if spacing < 30 or any(w["x1"] >= years[0]["x0"]-spacing*.1
                              and not re.fullmatch(r"\$|budget|actual|schedules?|notes?|\(?unaudited\)?|\(?audited\)?", w["text"], re.I)
                              for w in others):
            continue
        if expected_fiscal_year(fiscal_year) not in {w["text"] for w in years}:
            return [], "year_header_mismatch"
        columns = []
        for year in years:
            nearby = [w["text"].lower() for row in lines for w in row
                      if -17 < w["top"] - year["top"] < 17
                      and abs(w["x1"] - year["x1"]) < 28]
            role = "budget" if "budget" in nearby else "actual"
            columns.append({"year": int(year["text"]), "right": year["x1"],
                            "top": year["top"], "role": role,
                            "unaudited": "unaudited" in nearby})
        actual = [c["year"] for c in columns if c["role"] == "actual"]
        if len(set(actual)) != len(actual):
            return [], "ambiguous_actual_columns"
        # Some statements print an unnumbered budget column before the two
        # actual years. Its explicit label supplies a discard-only column.
        for row in lines:
            for word in row:
                if (word["text"].lower() == "budget" and abs(word["top"]-years[0]["top"]) < 20
                        and all(abs(word["x1"]-c["right"]) > 28 for c in columns)):
                    columns.append({"year": None, "right": word["x1"], "top": years[0]["top"],
                                    "role": "budget", "unaudited": True})
        return columns, None
    return [], "missing_explicit_year_columns"


def project_page(page, fiscal_year, target_year):
    columns, issue = column_layout(page, fiscal_year)
    selected = [c for c in columns if c["year"] == target_year and c["role"] == "actual"]
    if issue or len(selected) != 1:
        return "", [], issue or "missing_actual_column"
    selected = selected[0]
    # Scaled statements are quarantined until explicitly supported. Never silently
    # interpret a figure printed in thousands as dollars.
    if re.search(r"in thousands|in millions|\$\s*000|\$\s*millions", page["text"], re.I):
        return "", [], "unsupported_scaled_units"
    rows, projected = [], []
    header = "\n".join(page["text"].splitlines()[:3])
    header = re.sub(r"(?:As at|For the year ended).*", "", header, flags=re.I)
    header = re.sub(r"(statement of)\s*\n\s*", r"\1 ", header, flags=re.I)
    header = re.sub(r"\s+March\s+31\s*$", "", header, flags=re.I)
    projected.extend([header, str(target_year)])
    section = None
    revenue_parent = None
    for line in lines_from_words(page["words"]):
        if line[0]["top"] <= selected["top"] + 12:
            continue
        assigned = defaultdict(list)
        label_words = []
        for word in line:
            closest = min(columns, key=lambda c: abs(c["right"] - word["x1"]))
            if abs(closest["right"] - word["x1"]) <= 24 and AMOUNT.fullmatch(word["text"]):
                assigned[closest["right"]].append(word)
            else:
                # Other year cells and dollar symbols are not statement labels.
                if word["text"] != "$":
                    label_words.append(word)
        label = clean_text(" ".join(w["text"] for w in label_words))
        if re.fullmatch(r"[A-Za-z -]+", label) and re.search(r"(?:[A-Za-z] ){5}", label):
            compact = re.sub(r"\s", "", label).upper()
            label = {"FINANCIALASSETS": "Financial assets", "LIABILITIES": "Liabilities",
                     "NON-FINANCIALASSETS": "Non-financial assets"}.get(compact, label)
        if re.fullmatch(r"\(?Note\s+\d+\)?", label, re.I):
            continue
        label = re.sub(r"\(Note\s+\d+\)", "", label, flags=re.I).strip()
        label = re.sub(r"[,]?\s*\(Note\s+\d+\)", "", label, flags=re.I).strip()
        if re.fullmatch(r"revenues?", label, re.I):
            section = "revenue"
            revenue_parent = None
        elif re.fullmatch(r"(?:program )?expenses?", label, re.I):
            section = "expenses"
            revenue_parent = None
        elif re.fullmatch(r"(?:financial assets|liabilities|non.financial assets)", label, re.I):
            section = label.lower()
        elif re.match(r"other items?", label, re.I):
            section = "adjustments"
        # Printed schedule numbers are labels, never money columns.
        if section == "expenses":
            label = re.sub(r"\s+\d{1,2}$", "", label)
        cell = assigned[selected["right"]]
        raw = cell[0]["text"] if len(cell) == 1 else None
        value = 0 if raw == "-" else parse_money(raw)
        if len(cell) > 1:
            issue = "multiple_values_in_actual_cell"
        reference = {
            "pdfPage": page["page"], "sourceLabel": label,
            "rawText": clean_text(" ".join(w["text"] for w in line)),
            "rawValue": raw, "selectedYear": target_year,
            "selectedColumn": "actual", "yearValidated": True,
            "columnRight": round(selected["right"], 3),
            "bbox": [round(min(w["x0"] for w in line), 3),
                     round(min(w["top"] for w in line), 3),
                     round(max(w["x1"] for w in line), 3),
                     round(max(w["bottom"] for w in line), 3)],
            "noteNumbers": re.findall(r"\(Note\s+(\d+)\)", " ".join(w["text"] for w in line), re.I),
            "section": section, "unaudited": selected["unaudited"],
        }
        if section == "revenue":
            if value is None and re.search(r"indigenous services|government of|province of", label, re.I):
                revenue_parent = (label, line[0]["x0"], deepcopy(reference))
            elif revenue_parent and label and line[0]["x0"] > revenue_parent[1] + 5:
                reference["parentLabel"] = revenue_parent[0]
                reference["parentSource"] = revenue_parent[2]
            elif value is not None:
                revenue_parent = None
        rows.append({"label": label, "value": value, "reference": reference})
        projected.append(f"{label} {'0' if raw == '-' else raw or ''}".strip())
    for index in range(len(rows)-1, 0, -1):
        previous, current = rows[index-1], rows[index]
        if (previous["value"] is None and len(previous["label"]) > 60
                and current["value"] is not None and 0 < len(current["label"]) < 20
                and 0 < current["reference"]["bbox"][1]-previous["reference"]["bbox"][1] < 14):
            current["label"] = previous["label"] + " " + current["label"]
            current["reference"]["sourceLabel"] = current["label"]
            current["reference"]["rawText"] = previous["reference"]["rawText"] + "\n" + current["reference"]["rawText"]
            current["reference"]["bbox"][1] = previous["reference"]["bbox"][1]
            del rows[index-1]
    projected = projected[:2] + [f"{r['label']} {r['value'] if r['value'] is not None else ''}".strip() for r in rows]
    return "\n".join(projected), rows, issue


def read_pdf(raw, document):
    if pdfplumber is None:
        raise RuntimeError("pdfplumber is required")
    # PDFium obtains narrative pages without laying out every vector object in
    # large audited reports. Retain pdfplumber's exact word geometry on primary
    # statements, where actual-column selection depends on it.
    try:
        import pypdfium2
    except ImportError:
        pypdfium2 = None
    native_texts = None
    if pypdfium2 is not None:
        native_texts = []
        with pypdfium2.PdfDocument(raw) as fast_pdf:
            for fast_page in fast_pdf:
                with closing(fast_page):
                    with closing(fast_page.get_textpage()) as textpage:
                        native_texts.append(textpage.get_text_range())
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        pages = []
        for number, page in enumerate(pdf.pages, 1):
            entry = {"page": number, "text": native_texts[number-1] if native_texts is not None
                     else page.extract_text(x_tolerance=1, y_tolerance=3) or ""}
            if is_statement(entry):
                if native_texts is not None:
                    entry["text"] = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                entry["words"] = [{k: w[k] for k in ("text", "x0", "x1", "top", "bottom")}
                                  for w in page.extract_words(x_tolerance=1, y_tolerance=3)]
            pages.append(entry)
    return {"document": document, "pages": pages}


def identity_issues(document, pages):
    issues = []
    query = {k.lower(): v for k, v in parse_qs(urlparse(document["sourceUrl"]).query).items()}
    if query.get("band_number_ff", [str(document["bandId"])])[0] != str(document["bandId"]):
        issues.append("source_band_identifier_mismatch")
    if query.get("fy", [document["fiscalYear"]])[0] != document["fiscalYear"]:
        issues.append("source_fiscal_year_mismatch")
    title = " ".join(p["text"] for p in pages[:6]).casefold()
    compact_name = re.sub(r"\W", "", document["bandName"]).casefold()
    if compact_name not in re.sub(r"\W", "", title):
        issues.append("document_identity_unconfirmed")
    if not any(re.search(r"independent auditors?[\u2019']?s?\s+report", p["text"], re.I) for p in pages):
        issues.append("auditor_report_unconfirmed")
    if not re.fullmatch(r"[0-9a-f]{64}", document.get("sha256", "")):
        issues.append("missing_document_hash")
    if any(re.search(r"\b(?:US|U\.S\.|USD)\s*(?:dollars|\$)|\bUnited States dollars", p["text"], re.I) for p in pages if is_statement(p)):
        issues.append("unsupported_currency")
    return issues


def make_record(document, year, metric, value, references, *, dimension="", basis="reported", flags=()):
    if value is None or not isinstance(value, (float, int)) or not math.isfinite(value):
        return None
    references = deepcopy(references)
    flags = list(flags)
    if not references:
        flags.append("missing_source_evidence")
    if any(r.get("rawValue") is None or r.get("selectedYear") != year or r.get("unaudited")
           for r in references):
        flags.append("unconfirmed_actual_cell")
    record = {
        "bandId": str(document["bandId"]), "bandName": document["bandName"],
        "fiscalYear": f"{year-1}-{year}", "metric": metric, "value": value,
        "dimension": dimension, "currency": "CAD", "unit": "dollars",
        "sourceDocument": document["sourceUrl"], "sourceDocumentSha256": document["sha256"],
        "sourceFiscalYear": document["fiscalYear"],
        "sourcePage": references[0]["pdfPage"] if references else None,
        "sourceReferences": references, "extractionBasis": basis,
        "comparative": str(year) != expected_fiscal_year(document["fiscalYear"]),
        "validationStatus": "manual_review" if flags else "machine_checked",
        "validationFlags": sorted(set(flags)), "parser": PARSER_VERSION,
    }
    record["recordId"] = digest([record[k] for k in (
        "bandId", "fiscalYear", "metric", "dimension", "sourceDocumentSha256")]
        + [references])
    return record


def evidence_for(value, reference, rows, label=None):
    matches = [r for r in rows if r["value"] == value
               and (not reference or r["reference"]["pdfPage"] == reference.get("pdfPage"))
               and (label is None or r["label"].casefold() == label.casefold())]
    # A unique original row is mandatory, even when several rows have the same value.
    return [matches[0]["reference"]] if len(matches) == 1 else []


def extract_year(document, pages, year):
    projected = [""] * max(p["page"] for p in pages)
    rows, issues = [], []
    for page in pages:
        if not is_statement(page):
            continue
        text, page_rows, issue = project_page(page, document["fiscalYear"], year)
        projected[page["page"]-1] = text
        rows.extend(page_rows)
        if issue:
            issues.append(f"page_{page['page']}:{issue}")
    fiscal_year = f"{year-1}-{year}"
    summary = parse_page_texts(projected, document["sourceUrl"], fiscal_year)
    records = []

    def add(metric, value, refs, **kwargs):
        record = make_record(document, year, metric, value, refs, **kwargs)
        if record:
            records.append(record)

    for metric in METRICS:
        if metric not in summary or summary[metric] is None:
            continue
        ref = (summary.get("sourceReferences") or {}).get(metric)
        refs = evidence_for(summary[metric], ref, rows,
                            ref.get("sourceLabel") if ref else None)
        if metric == "annualSurplusDeficit" and not refs:
            candidates = [r for r in rows if r["value"] == summary[metric]
                          and FINAL_SURPLUS_RE.fullmatch(r["label"])
                          and (not ref or r["reference"]["pdfPage"] == ref.get("pdfPage"))]
            refs = [candidates[0]["reference"]] if len(candidates) == 1 else []
        if metric in ("totalRevenue", "totalExpenses") and not refs:
            section = "revenue" if metric == "totalRevenue" else "expenses"
            candidates = [r for r in rows if r["value"] == summary[metric]
                          and r["reference"]["section"] == section and not r["label"]]
            refs = [candidates[0]["reference"]] if len(candidates) == 1 else []
        add(metric, summary[metric], refs)

    for field, metric in (("sourceRevenueRows", "revenueComponent"),
                          ("sourceExpenseRows", "expenseProgram"),
                          ("surplusAdjustments", "surplusAdjustment")):
        for component in summary.get(field) or []:
            label = component.get("originalLabel") or component.get("label") or component.get("sourceLabel")
            value = component["amount"]
            refs = evidence_for(value, component.get("sourceReference"), rows, label)
            dimension = label or ""
            if metric == "revenueComponent" and refs and refs[0].get("parentLabel"):
                dimension = refs[0]["parentLabel"] + " - " + dimension
            add(metric, value, refs, dimension=dimension)

    def get(metric):
        return next((r for r in records if r["metric"] == metric), None)

    # Some PSAS statements leave the financial-assets total unlabelled. It is
    # accepted only at the explicit section boundary and checked against assets.
    if not get("totalFinancialAssets"):
        financial_rows = [r for r in rows if r["reference"]["section"] == "financial assets"]
        candidates = [r for r in financial_rows if not r["label"] and r["value"] is not None]
        components = [r for r in financial_rows if r["label"] and r["value"] is not None]
        if candidates and components and abs(candidates[-1]["value"] - sum(r["value"] for r in components)) <= 2:
            add("totalFinancialAssets", candidates[-1]["value"], [candidates[-1]["reference"]], basis="section_total")

    financial, nonfinancial = get("totalFinancialAssets"), get("totalNonFinancialAssets")
    if not get("totalAssets") and financial and nonfinancial:
        add("totalAssets", financial["value"] + nonfinancial["value"],
            financial["sourceReferences"] + nonfinancial["sourceReferences"], basis="derived_sum")

    # Explicit components only. These identified subtotals are not claims of
    # complete government/own-source revenue and are never residual estimates.
    revenue = [r for r in records if r["metric"] == "revenueComponent"]
    for metric, pattern in {
        "governmentRevenue": r"indigenous services|government of|province of|canada mortgage|canadian heritage|^saskatchewan (?:government|health|education)",
        "saskatchewanGovernmentRevenue": r"(?:government|province) of saskatchewan|^saskatchewan (?:government|health|education)",
        "ownSourceRevenue": r"^(?:own.source revenue|rent|interest)$|rental|land lease|lease (?:revenue|income)|interest income|investment income|dividend|(?:restaurant|gravel|retail) sales|^sales -|business (?:income|revenue)|(?:earnings|loss) from (?:investment|.*joint venture)",
        "businessRevenue": r"(?:restaurant|gravel|retail) sales|^sales -|business (?:income|revenue)|(?:earnings|loss) from (?:investment|.*joint venture)",
        "investmentIncome": r"^interest$|interest income|investment income|dividend",
    }.items():
        selected = [r for r in revenue if re.search(pattern, r["dimension"], re.I)]
        if metric == "ownSourceRevenue":
            explicit = [r for r in selected if re.fullmatch(r"own.source revenue", r["dimension"], re.I)]
            selected = explicit or selected
        if selected:
            # Replace the parser's unreferenced identified subtotal inside this
            # trial result only, never the stored Community Capital summary.
            records[:] = [r for r in records if r["metric"] != metric]
            add(metric, sum(r["value"] for r in selected),
                [ref for r in selected for ref in r["sourceReferences"]], basis="identified_components_only")

    programs = [r for r in records if r["metric"] == "expenseProgram"]
    explicit_program_heading = any(re.search(r"^Program expenses\s*$", p["text"], re.I | re.M) for p in pages if is_statement(p))
    if programs and explicit_program_heading:
        add("programExpenses", sum(r["value"] for r in programs),
            [ref for r in programs for ref in r["sourceReferences"]], basis="derived_sum")
    admin = [r for r in programs if re.fullmatch(r"administration|administrative expenses", r["dimension"], re.I)]
    if admin:
        add("administrativeExpenses", sum(r["value"] for r in admin),
            [ref for r in admin for ref in r["sourceReferences"]], basis="identified_components_only")

    issues += identity_issues(document, pages)
    if summary.get("publishable") is not True:
        issues.append("existing_capital_validation_failed")
    return records, issues


def extract_disclosures(document, pages):
    """Retain relevant original notes; entities are qualitative, not dollar rows."""
    notes, entities = [], []
    for page in pages:
        text = page["text"]
        if not re.search(r"notes to (?:the )?consolidated financial statements", text[:220], re.I):
            continue
        if not re.search(r"reporting entity|investments?|long.term debt|claim loan|contingen|related parties", text, re.I):
            continue
        base = {"bandId": str(document["bandId"]), "fiscalYear": document["fiscalYear"],
                "sourceDocument": document["sourceUrl"], "sourceDocumentSha256": document["sha256"],
                "sourcePage": page["page"], "validationStatus": "manual_review"}
        notes.append({**base, "text": text, "reason": "Narrative context retained; numeric note tables require separate verification."})
        mode = None
        pending = None
        for line in text.splitlines():
            if re.search(r"following entities and departments:|wholly owned subsidiaries:", line, re.I):
                mode = "consolidated_reporting_entity"
            elif re.search(r"modified equity basis include:", line, re.I):
                mode = "modified_equity_investee"
            elif re.search(r"not owned, controlled, or influenced", line, re.I):
                mode = "portfolio_investee"
            elif re.match(r"[\u2022\uf0b7]", line) and mode:
                if pending:
                    entities.append(pending)
                pending = {**base, "entityName": line[1:].strip().rstrip(";,."), "relationship": mode,
                           "sourceText": line}
            elif pending:
                # Wrapped bullet items remain intact; narrative ends the list.
                if re.match(r"interest in |Limited Partnership|Holdings", line):
                    pending["entityName"] += " " + line.strip()
                    pending["sourceText"] += "\n" + line
                else:
                    entities.append(pending)
                    pending = None
                    mode = None
        if pending:
            entities.append(pending)
    return notes, entities


def validate_records(records, document_issues=None):
    """Strict absolute accounting checks; flags never repair a source value."""
    records = deepcopy(records)
    groups = defaultdict(list)
    for record in records:
        if (not record.get("bandId") or not re.fullmatch(r"20\d{2}-20\d{2}", record.get("fiscalYear", ""))
                or not record.get("sourceDocument") or not record.get("sourceDocumentSha256")
                or not record.get("sourceReferences") or not record.get("sourcePage")):
            record["validationFlags"] = sorted(set(record["validationFlags"] + ["missing_required_provenance"]))
        groups[(record["bandId"], record["fiscalYear"], record["sourceDocumentSha256"])].append(record)
    findings = []
    for key, group in groups.items():
        by_metric = defaultdict(list)
        for r in group:
            by_metric[(r["metric"], r["dimension"])].append(r)
        flags = list((document_issues or {}).get(key, []))
        for rows in by_metric.values():
            if len(rows) > 1:
                flags.append("conflicting_duplicate" if len({r["value"] for r in rows}) > 1 else "duplicate_record")

        def scalar(metric):
            matches = by_metric.get((metric, ""), [])
            return matches[0]["value"] if len(matches) == 1 else None

        for metric in ("totalRevenue", "totalExpenses", "annualSurplusDeficit"):
            if scalar(metric) is None:
                flags.append(f"missing_required:{metric}")
        checks = []
        for component, total in (("revenueComponent", "totalRevenue"), ("expenseProgram", "totalExpenses")):
            values = [r["value"] for r in group if r["metric"] == component]
            checks.append((f"{component}_sum", sum(values) if values else None, scalar(total)))
        revenue, expenses, surplus = (scalar(m) for m in ("totalRevenue", "totalExpenses", "annualSurplusDeficit"))
        adjustments = sum(r["value"] for r in group if r["metric"] == "surplusAdjustment")
        checks.append(("annual_result", revenue-expenses+adjustments if revenue is not None and expenses is not None else None, surplus))
        financial, liabilities, net = (scalar(m) for m in ("totalFinancialAssets", "totalLiabilities", "netFinancialAssetsDebt"))
        checks.append(("net_financial_assets", financial-liabilities if financial is not None and liabilities is not None else None, net))
        nonfinancial, accumulated = scalar("totalNonFinancialAssets"), scalar("accumulatedSurplus")
        checks.append(("accumulated_surplus", net+nonfinancial if net is not None and nonfinancial is not None else None, accumulated))
        assets = scalar("totalAssets")
        checks.append(("balance_sheet", liabilities+accumulated if liabilities is not None and accumulated is not None else None, assets))
        for name, computed, reported in checks:
            if computed is None or reported is None:
                findings.append({"bandId": key[0], "fiscalYear": key[1], "check": name, "status": "unavailable"})
                flags.append(f"missing_check_inputs:{name}")
            else:
                ok = abs(computed-reported) <= 2
                findings.append({"bandId": key[0], "fiscalYear": key[1], "check": name,
                                 "status": "passed" if ok else "failed", "difference": computed-reported})
                if not ok:
                    flags.append(f"accounting_inconsistency:{name}")
        for r in group:
            if not math.isfinite(r["value"]) or abs(r["value"]) > 10_000_000_000:
                r["validationFlags"].append("suspicious_magnitude")
            if r["metric"] in ("cash", "accountsReceivable", "totalAssets", "totalExpenses") and r["value"] < 0:
                r["validationFlags"].append("unexpected_negative_value")
            r["validationFlags"] = sorted(set(r["validationFlags"] + flags))
            r["validationStatus"] = "manual_review" if r["validationFlags"] else "machine_checked"

    # Cross-document overlaps retain restatements but are excluded from checked
    # exports until resolved; conflicting observations are never silently chosen.
    observations = defaultdict(list)
    for r in records:
        observations[(r["bandId"], r["fiscalYear"], r["metric"], r["dimension"])].append(r)
    for matches in observations.values():
        if len({r["sourceDocumentSha256"] for r in matches}) > 1:
            flag = "cross_document_conflict" if len({r["value"] for r in matches}) > 1 else "cross_document_duplicate"
            for r in matches:
                r["validationFlags"] = sorted(set(r["validationFlags"] + [flag]))
                r["validationStatus"] = "manual_review"
    histories = defaultdict(list)
    for r in records:
        if not r["dimension"]:
            histories[(r["bandId"], r["metric"])].append(r)
    for series in histories.values():
        series.sort(key=lambda r: r["fiscalYear"])
        for previous, current in zip(series, series[1:]):
            if int(current["fiscalYear"][-4:]) - int(previous["fiscalYear"][-4:]) != 1:
                continue
            a, b = previous["value"], current["value"]
            if abs(b-a) >= 10_000_000 and (not a or abs(b/a) >= 3 or abs(b/a) <= 1/3):
                current["validationFlags"] = sorted(set(current["validationFlags"] + ["major_year_over_year_change"]))
                current["validationStatus"] = "manual_review"
    # Derived subtotals inherit component review flags (including unusual values).
    flagged_refs = {digest(ref) for r in records if r["validationStatus"] == "manual_review"
                    for ref in r["sourceReferences"]}
    for r in records:
        if r["extractionBasis"] != "reported" and any(digest(ref) in flagged_refs for ref in r["sourceReferences"]):
            r["validationFlags"] = sorted(set(r["validationFlags"] + ["component_requires_review"]))
            r["validationStatus"] = "manual_review"
    return records, findings


def extract_fixture(fixture):
    document, pages = fixture["document"], fixture["pages"]
    current_year = int(expected_fiscal_year(document["fiscalYear"]))
    records, issues = [], {}
    for year in (current_year, current_year-1):
        values, flags = extract_year(document, pages, year)
        records.extend(values)
        issues[(str(document["bandId"]), f"{year-1}-{year}", document["sha256"])] = flags
    notes, entities = extract_disclosures(document, pages)
    records, checks = validate_records(records, issues)
    return {"records": records, "checks": checks, "notes": notes, "entities": entities,
            "issues": {f"{k[0]}:{k[1]}": v for k, v in issues.items()}}


def safe_output_directory(output):
    root = Path("research/bandy-financial").resolve()
    output = Path(output).resolve()
    if output != root and root not in output.parents:
        raise ValueError("Outputs must stay under research/bandy-financial; production targets are forbidden")
    if output.is_symlink():
        raise ValueError("Symlink output directory is forbidden")
    output.mkdir(parents=True, exist_ok=True)
    return output


def write_exports(results, output, documents):
    output = safe_output_directory(output)
    # Exclusive creation also prevents accidental replacement of a reviewed export.
    records = [r for result in results for r in result["records"]]
    records, _ = validate_records(records)
    checked = [r for r in records if r["validationStatus"] == "machine_checked"]
    notes = [n for result in results for n in result["notes"]]
    entities = [n for result in results for n in result["entities"]]
    checks = [n for result in results for n in result["checks"]]
    payload = {"schemaVersion": 1, "purpose": "research_only", "parser": PARSER_VERSION,
               "generated": datetime.now(timezone.utc).isoformat(), "documents": documents,
               "records": records, "noteDisclosures": notes, "entityDisclosures": entities}
    coverage = []
    for document in documents:
        end = int(expected_fiscal_year(document["fiscalYear"]))
        for fiscal_year in (f"{end-2}-{end-1}", f"{end-1}-{end}"):
            group = [r for r in records if r["bandId"] == str(document["bandId"]) and r["fiscalYear"] == fiscal_year]
            present = {r["metric"] for r in group}
            coverage.append({"bandId": str(document["bandId"]), "fiscalYear": fiscal_year,
                             "extracted": sorted(present & set(METRICS)),
                             "additionalMetrics": sorted(present & NEW_METRICS),
                             "unavailable": sorted(set(METRICS) - present),
                             "manualReview": [{"metric": r["metric"], "dimension": r["dimension"],
                                               "value": r["value"], "flags": r["validationFlags"]}
                                              for r in group if r["validationStatus"] == "manual_review"]})
    report = {"documentCount": len(documents), "recordCount": len(records),
              "checkedRecordCount": len(checked), "reviewRecordCount": len(records)-len(checked),
              "noteCount": len(notes), "entityCount": len(entities), "coverage": coverage,
              "checks": checks, "documentIssues": [r["issues"] for r in results]}
    targets = [output / n for n in ("financial-records.json", "checked-records.jsonl", "review-report.json", "financial.sqlite")]
    if any(p.exists() or p.is_symlink() for p in targets):
        raise FileExistsError("Choose a new research output directory; existing exports are never overwritten")
    for target, content in ((targets[0], json.dumps(payload, ensure_ascii=False, indent=2)+"\n"),
                            (targets[1], "".join(json.dumps(r, ensure_ascii=False)+"\n" for r in checked)),
                            (targets[2], json.dumps(report, ensure_ascii=False, indent=2)+"\n")):
        with target.open("x", encoding="utf-8") as stream:
            stream.write(content)
    with closing(sqlite3.connect(targets[3])) as db:
        db.execute("CREATE TABLE financial_records (record_id TEXT PRIMARY KEY, band_id TEXT NOT NULL, fiscal_year TEXT NOT NULL, metric TEXT NOT NULL, dimension TEXT NOT NULL, value REAL NOT NULL, source_document TEXT NOT NULL, source_page INTEGER, validation_status TEXT NOT NULL, record_json TEXT NOT NULL)")
        # Exact duplicate IDs remain in the review JSON; SQL keeps one flagged observation.
        db.executemany("INSERT OR IGNORE INTO financial_records VALUES (?,?,?,?,?,?,?,?,?,?)", [
            (r["recordId"], r["bandId"], r["fiscalYear"], r["metric"], r["dimension"], r["value"],
             r["sourceDocument"], r["sourcePage"], r["validationStatus"], json.dumps(r)) for r in records])
        db.execute("CREATE INDEX financial_query ON financial_records(band_id, fiscal_year, metric)")
        db.execute("CREATE VIEW checked_financial_records AS SELECT * FROM financial_records WHERE validation_status = 'machine_checked'")
        db.commit()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="tests/fixtures/bandy-sk/manifest.json")
    parser.add_argument("--output", default="research/bandy-financial/milestone-1")
    parser.add_argument("--download", action="store_true", help="Fetch only the manifest's bounded public sample")
    parser.add_argument("--cache", default="tmp/bandy-sample")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    documents = json.loads(manifest_path.read_text(encoding="utf-8"))["documents"]
    if not 1 <= len(documents) <= min(args.limit, 10):
        parser.error("Manifest exceeds the bounded sample limit (maximum 10)")
    safe_output_directory(args.output)
    fixtures = []
    for document in documents:
        if args.download:
            cache = Path(args.cache).resolve()
            allowed = Path("tmp/bandy-sample").resolve()
            if cache != allowed and allowed not in cache.parents:
                raise ValueError("PDF cache must stay under tmp/bandy-sample")
            cache.mkdir(parents=True, exist_ok=True)
            target = cache / f"{document['bandId']}-{document['fiscalYear']}.pdf"
            raw = target.read_bytes() if target.exists() else fetch_pdf(document["sourceUrl"])
            if hashlib.sha256(raw).hexdigest() != document["sha256"]:
                raise ValueError(f"Document hash mismatch for band {document['bandId']}; refresh requires review")
            if not target.exists():
                with target.open("xb") as stream:
                    stream.write(raw)
            fixtures.append(read_pdf(raw, document))
        else:
            fixtures.append(json.loads((manifest_path.parent / document["fixture"]).read_text(encoding="utf-8")))
            if fixtures[-1]["document"] != document:
                raise ValueError("Fixture metadata differs from the source manifest")
    results = [extract_fixture(f) for f in fixtures]
    report = write_exports(results, args.output, documents)
    print(json.dumps({k: v for k, v in report.items() if k not in ("coverage", "checks", "documentIssues")}))


if __name__ == "__main__":
    main()
