"""Conservative, coordinate-aware PDF table extraction helpers.

This module intentionally stays inside the free local tier.  ``pdfplumber``
uses word coordinates and detected ruling lines to reconstruct cells; trying a
small set of table strategies is safer than flattening the whole PDF into one
text stream.  Callers still validate the returned rows before publishing them.
"""

from __future__ import annotations

import re


MONEY_RE = re.compile(r"\(?\$?\s*-?\d[\d,]*(?:\.\d+)?\)?")
ROLE_RE = re.compile(r"\bchief|councillor|councilor|council\s+member\b", re.I)
REMUNERATION_RE = re.compile(
    r"schedule\s+of\s+remuneration|remuneration\s+and\s+expenses|"
    r"chief\s+and\s+councillors?|elected\s+officials?|"
    r"number\s+of\s+months|honou?raria|per\s*diems?",
    re.I,
)
CAPITAL_RE = re.compile(
    r"statement\s+of|revenue|revenues|expense|expenses|expenditure|"
    r"surplus|deficit|assets?|liabilit|debt|capital|cash|operations|"
    r"financial position|financial activities|government|community|"
    r"economic|education|health|social|housing|membership|programs?",
    re.I,
)


TABLE_STRATEGIES = (
    ("lines", {}),
    (
        "text",
        {
            "vertical_strategy": "text",
            "horizontal_strategy": "text",
            "snap_tolerance": 4,
            "join_tolerance": 4,
            "intersection_tolerance": 4,
            "text_x_tolerance": 2,
            "text_y_tolerance": 3,
        },
    ),
    (
        "text_loose",
        {
            "vertical_strategy": "text",
            "horizontal_strategy": "text",
            "snap_tolerance": 7,
            "join_tolerance": 7,
            "intersection_tolerance": 7,
            "text_x_tolerance": 3,
            "text_y_tolerance": 4,
        },
    ),
)


def clean_cell(value):
    """Normalize cell whitespace while retaining an empty placeholder."""
    if value is None:
        return ""
    return " ".join(str(value).replace("\u00a0", " ").split()).strip()


def normalize_table(table):
    """Return rectangular-ish rows without deleting blank columns."""
    rows = []
    for row in table or []:
        if row is None:
            continue
        cells = [clean_cell(cell) for cell in row]
        if any(cells):
            rows.append(cells)
    return rows


def table_text(rows):
    return " ".join(cell for row in rows for cell in row if cell)


def _has_money(rows):
    return any(MONEY_RE.search(cell) for row in rows for cell in row)


def relevant_table(rows, page_text="", kind="generic"):
    """Reject obvious non-target tables before they enter a parser."""
    if not rows or not _has_money(rows):
        return False
    context = f"{page_text} {table_text(rows)}"
    if kind == "remuneration":
        return bool(REMUNERATION_RE.search(context) or ROLE_RE.search(table_text(rows)))
    if kind == "capital":
        return bool(CAPITAL_RE.search(context))
    return True


def _extract(page, settings):
    if settings:
        return page.extract_tables(settings) or []
    return page.extract_tables() or []


def extract_tables_for_page(page, page_text="", kind="generic"):
    """Try several coordinate-aware strategies and deduplicate their tables.

    The result keeps the strategy, page number, bounding box, and column count
    alongside rows so downstream diagnostics can explain where a value came
    from.  ``rows`` intentionally keeps empty cells because dropping them is a
    common cause of travel/expense column shifts.
    """
    results = []
    seen = set()
    page_number = getattr(page, "page_number", None)
    bbox = getattr(page, "bbox", None)
    for strategy_name, settings in TABLE_STRATEGIES:
        try:
            tables = _extract(page, settings)
        except (TypeError, ValueError):
            # Older pdfplumber versions may not recognize newer settings.
            continue
        for raw_table in tables:
            rows = normalize_table(raw_table)
            if not relevant_table(rows, page_text, kind):
                continue
            signature = tuple(tuple(row) for row in rows)
            if signature in seen:
                continue
            seen.add(signature)
            results.append(
                {
                    "rows": rows,
                    "strategy": strategy_name,
                    "page": page_number,
                    "bbox": list(bbox) if bbox else None,
                    "columns": max((len(row) for row in rows), default=0),
                }
            )
    return results


def extract_table_page_texts(pdf, kind="capital"):
    """Build page-preserving text from accepted table candidates.

    Empty placeholders preserve the original PDF page numbers used in source
    references.  A cell separator is retained so labels and numeric columns do
    not become one ambiguous string before the existing parser sees them.
    """
    pages = []
    found_table = False
    for page in pdf.pages:
        page_text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
        candidates = extract_tables_for_page(page, page_text, kind)
        if not candidates:
            pages.append("")
            continue
        found_table = True
        header = "\n".join(page_text.splitlines()[:10])
        lines = [header] if header else []
        for candidate in candidates:
            for row in candidate["rows"]:
                # Keep cell order without adding punctuation to labels.  The
                # existing parser uses exact labels for total-row detection.
                lines.append(" ".join(row))
        pages.append("\n".join(lines))
    return pages if found_table else []
