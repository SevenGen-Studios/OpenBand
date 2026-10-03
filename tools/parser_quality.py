"""Parser validation helpers for OpenBand FNFTA remuneration data.

This module is deliberately conservative. It does not try to parse PDFs by
itself; it scores candidate tables and validates rows produced by the scraper so
uncertain extraction is flagged instead of published as clean data.
"""

import re

PAYMENT_KEYS = ("remuneration", "travel", "expenses", "creditCard", "otherPayments")
CANONICAL_KEYS = ("name", "role", "months", "remuneration", "travelExpenses", "other", "total")

POSITIVE_TABLE_RE = re.compile(
    r"\b("
    r"schedule\s+of\s+remuneration|remuneration\s+and\s+expenses|"
    r"chief\s+and\s+council|chief\s+and\s+councillors?|"
    r"elected\s+officials?|remuneration\s+paid|expenses?\s+reimbursed|"
    r"number\s+of\s+months|honou?raria|per\s*diems?"
    r")\b",
    re.IGNORECASE,
)

NEGATIVE_TABLE_RE = re.compile(
    r"\b("
    r"statement\s+of|consolidated|assets?|liabilit(?:y|ies)|revenue|"
    r"deficit|surplus|cash\s+flows?|program|project|contract|"
    r"construction|capital|accounts?\s+payable|accounts?\s+receivable|"
    r"tangible\s+capital|debt|loan|budget|department|administration"
    r")\b",
    re.IGNORECASE,
)

HEADER_RE = re.compile(
    r"\b(name|position|role|chief|councillors?|months?|remuneration|salary|"
    r"honou?raria|wages?|travel|expenses?|reimbursements?|per\s*diems?|"
    r"allowances?|credit\s*card|other|payments?|total)\b",
    re.IGNORECASE,
)

TOTAL_NAME_RE = re.compile(r"^\s*(totals?|subtotals?|grand\s+totals?)\b", re.IGNORECASE)
ROLE_RE = re.compile(r"\b(chief|councillor|councilor|council\s+member|council)\b", re.IGNORECASE)


def clean_text(value):
    return " ".join(str(value or "").replace("\u00a0", " ").split()).strip()


def number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = clean_text(value)
    if not text or text in {"-", "--", "---", "N/A", "n/a"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if cleaned in {"", "-", "."}:
        return None
    try:
        parsed = float(cleaned)
    except ValueError:
        return None
    return -parsed if negative and parsed > 0 else parsed


def nearly_equal(left, right, tolerance=0.04):
    if left is None or right is None:
        return False
    return abs(float(left) - float(right)) <= max(5.0, abs(float(right)) * tolerance)


def money_total(person):
    return sum(number(person.get(key)) or 0 for key in PAYMENT_KEYS)


def travel_expenses(person):
    existing = number(person.get("travelExpenses"))
    if existing is not None:
        return existing
    return sum(number(person.get(key)) or 0 for key in ("travel", "expenses", "creditCard"))


def other_amount(person):
    existing = number(person.get("other"))
    if existing is not None:
        return existing
    return number(person.get("otherPayments")) or 0


def normalize_person(person):
    """Add canonical fields while preserving the existing website fields."""
    cleaned = dict(person)
    cleaned["travelExpenses"] = travel_expenses(cleaned)
    cleaned["other"] = other_amount(cleaned)
    total = number(cleaned.get("total"))
    if total is None:
        total = (number(cleaned.get("remuneration")) or 0) + cleaned["travelExpenses"] + cleaned["other"]
    cleaned["total"] = int(total) if float(total).is_integer() else total
    return cleaned


def table_text(table, page_text=""):
    cells = []
    for row in table or []:
        for cell in row or []:
            text = clean_text(cell)
            if text:
                cells.append(text)
    return clean_text(" ".join([page_text or ""] + cells))


def score_candidate_table(table, page_text=""):
    """Return table quality metadata for deciding whether to parse a PDF table."""
    text = table_text(table, page_text)
    header_hits = len(HEADER_RE.findall(text))
    positive_hits = len(POSITIVE_TABLE_RE.findall(text))
    negative_hits = len(NEGATIVE_TABLE_RE.findall(text))
    rows = [row for row in (table or []) if any(clean_text(cell) for cell in (row or []))]
    moneyish_rows = 0
    role_rows = 0
    for row in rows:
        row_text = clean_text(" ".join(clean_text(cell) for cell in row or []))
        if re.search(r"\d{1,3}(?:,\d{3})", row_text):
            moneyish_rows += 1
        if ROLE_RE.search(row_text):
            role_rows += 1

    score = positive_hits * 3 + min(header_hits, 8) + min(role_rows, 6) + min(moneyish_rows, 8)
    score -= negative_hits * 4

    warnings = []
    if positive_hits == 0:
        warnings.append("No clear Chief and Council remuneration context found")
    if header_hits < 3:
        warnings.append("Column headers unclear")
    if negative_hits:
        warnings.append("Possible unrelated financial statement table")
    if moneyish_rows == 0:
        warnings.append("No money rows detected in candidate table")

    accepted = score >= 8 and positive_hits > 0 and moneyish_rows > 0 and negative_hits <= positive_hits + 1
    return {
        "score": score,
        "accepted": accepted,
        "warnings": warnings,
        "header_hits": header_hits,
        "positive_hits": positive_hits,
        "negative_hits": negative_hits,
        "moneyish_rows": moneyish_rows,
    }


def source_total_from_table(table, require_total_header=False):
    """Best-effort extraction of the PDF footer total for reconciliation."""
    total_column = None
    if require_total_header:
        for row in (table or [])[:6]:
            if any(ROLE_RE.search(clean_text(cell)) and number(cell) is not None for cell in row or []):
                break
            for column, cell in enumerate(row or []):
                if re.search(r'\btotal\b', clean_text(cell), re.I) and not TOTAL_NAME_RE.search(clean_text(cell)):
                    total_column = column
                elif clean_text(cell).lower() == 'total':
                    total_column = column
        if total_column is None:
            return None
    for row in reversed(table or []):
        cells = [clean_text(cell) for cell in row or []]
        row_text = " ".join(cells)
        if not TOTAL_NAME_RE.search(row_text):
            continue
        if require_total_header:
            return number(cells[total_column]) if total_column < len(cells) else None
        values = [number(cell) for cell in cells]
        values = [value for value in values if value is not None]
        if values:
            return values[-1]
    return None


def validate_people(people, source_total=None, table_quality=None, strict=False):
    warnings = []
    severe = []
    normalized = []

    if not people:
        return {
            "people": [],
            "confidence": "manual_review_required",
            "manual_review_required": True,
            "warnings": ["No official rows parsed"],
        }

    mismatch_count = 0
    inferred_count = 0
    chief_count = 0

    for index, person in enumerate(people, start=1):
        row_warnings = []
        normalized_person = normalize_person(person)
        name = clean_text(normalized_person.get("name"))
        role = clean_text(normalized_person.get("role"))
        months = number(normalized_person.get("months"))
        total = number(normalized_person.get("total"))
        component_total = (
            (number(normalized_person.get("remuneration")) or 0)
            + travel_expenses(normalized_person)
            + other_amount(normalized_person)
        )

        if not name:
            severe.append(f"Row {index}: missing official name")
        elif TOTAL_NAME_RE.search(name):
            severe.append(f"Row {index}: possible footer total parsed as official")
        elif len(re.sub(r'[^A-Za-z]', '', name)) < 3 or re.search(
                r'\b(year ended|schedule of|number of months)\b', name, re.I):
            severe.append(f"Row {index}: official name is a number or document heading")
        elif strict and (len(name) > 80 or re.search(r'\d|\bname of individual\b', name, re.I)):
            severe.append(f"Row {index}: official name contains merged columns or a table heading")

        if "chief" in role.lower():
            chief_count += 1
        elif not ROLE_RE.search(role):
            inferred_count += 1
            row_warnings.append(f"Row {index}: role unclear")

        if months is not None and not (0 < months <= 12):
            row_warnings.append(f"Row {index}: months outside 0-12")

        if total is None or total <= 0:
            severe.append(f"Row {index}: missing or zero total")
        elif component_total > 0 and not nearly_equal(total, component_total, tolerance=0 if strict else 0.04):
            mismatch_count += 1
            row_warnings.append(f"Row {index}: total does not equal remuneration + travel/expenses + other")

        if number(normalized_person.get("remuneration")) is None and (months is None or months >= 9):
            row_warnings.append(f"Row {index}: remuneration missing for apparent full-year official")

        for key in ("remuneration", "travelExpenses", "other", "total"):
            value = number(normalized_person.get(key))
            if strict and value is not None and abs(value * 100 - round(value * 100)) > 0.0001:
                severe.append(f"Row {index}: ambiguous decimal separator in {key}")
            if value is not None and value < 0:
                row_warnings.append(f"Row {index}: negative {key} amount")
            if value is not None and value > 1000000:
                row_warnings.append(f"Row {index}: unusually large {key} amount")
                if strict:
                    severe.append(f"Row {index}: unusually large {key} needs source review")

        warnings.extend(row_warnings)
        normalized.append(normalized_person)

    if chief_count == 0:
        warnings.append("No Chief row detected")
        if strict:
            severe.append("A complete Chief and Council schedule requires an identified Chief row")

    if len(normalized) == 1:
        warnings.append("Only one official row parsed")

    if strict:
        names = [re.sub(r'[^a-z]', '', clean_text(p.get('name')).lower()) for p in normalized]
        for index, name in enumerate(names):
            contained = {other for other in names if len(other) >= 8 and other != name and other in name}
            if len(contained) >= 2:
                severe.append(f"Row {index + 1}: possible merged official names")

    if mismatch_count and mismatch_count >= max(2, len(normalized) // 2):
        severe.append("Totals do not reconcile for many rows")
    elif strict and mismatch_count:
        severe.append("At least one official row does not reconcile")

    if source_total is not None:
        parsed_sum = sum(number(person.get("total")) or 0 for person in normalized)
        if not nearly_equal(parsed_sum, source_total, tolerance=0 if strict else 0.04):
            warnings.append("Parsed row totals do not match source total row")
            if strict:
                severe.append("Parsed officials do not reconcile with the source total row")

    if table_quality:
        warnings.extend(table_quality.get("warnings") or [])
        if not table_quality.get("accepted", True):
            severe.append("Candidate table did not meet Chief and Council confidence threshold")

    if severe:
        confidence = "low"
        manual_review_required = True
    elif mismatch_count or inferred_count or warnings:
        confidence = "medium"
        manual_review_required = False
    else:
        confidence = "high"
        manual_review_required = False

    deduped_warnings = []
    for warning in severe + warnings:
        if warning and warning not in deduped_warnings:
            deduped_warnings.append(warning)

    return {
        "people": normalized,
        "confidence": confidence,
        "manual_review_required": manual_review_required,
        "warnings": deduped_warnings,
    }


def apply_validation_metadata(result, source_total=None, table_quality=None, strict=False):
    validated = validate_people(result.get("people") or [], source_total, table_quality, strict)
    merged = dict(result)
    if source_total is not None:
        merged["sourceTotal"] = source_total
    merged["people"] = validated["people"]
    merged["parse_confidence"] = validated["confidence"]
    merged["manual_review_required"] = validated["manual_review_required"]
    warnings = []
    for warning in (result.get("warnings") or []) + validated["warnings"]:
        if warning and warning not in warnings:
            warnings.append(warning)
    merged["warnings"] = warnings
    return merged
