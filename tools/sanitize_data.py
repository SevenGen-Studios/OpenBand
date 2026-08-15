"""Clean parsed FNFTA remuneration rows before the website reads data.json.

The scraper has to handle many PDF layouts. Some layouts expose page headings,
dates, or project/accounting rows as text that can look like a person row. This
script is a conservative cleanup pass: it removes obvious non-person rows,
normalizes fields, deduplicates rows, recalculates broken totals, and converts
internal parser statuses into public-friendly data statuses.
"""

import json
import re
import sys
from pathlib import Path

try:
    from tools import parser_quality
except ImportError:  # pragma: no cover - supports running from tools/ directly
    import parser_quality

PAYMENT_KEYS = ("remuneration", "travel", "expenses", "creditCard", "otherPayments")
CANONICAL_MONEY_KEYS = ("travelExpenses", "other")
ALL_MONEY_KEYS = PAYMENT_KEYS + CANONICAL_MONEY_KEYS + ("total",)

PUBLIC_STATUS_MAP = {
    "": "pending_review",
    None: "pending_review",
    "error": "pending_review",
    "error_openai": "pending_ai_review",
    "error_openai_empty": "pending_ai_review",
    "error_openai_quota": "pending_ai_setup",
    "error_pdf_download": "source_download_failed",
    "no_pdf_url": "source_unavailable",
    "no_rows": "pending_review",
    "not_applicable": "not_required",
    "sanitized_no_valid_rows": "pending_manual_review",
    "skipped_openai_no_key": "pending_ai_setup",
    "skipped_pdfplumber": "pending_review",
    "skipped_run_limit": "pending_retry",
}

TECHNICAL_STATUS_MAP = {
    "error": "parser_failed",
    "error_openai": "openai_extraction_failed",
    "error_openai_empty": "openai_empty_response",
    "error_pdf_download": "pdf_download_failed",
    "sanitized_no_valid_rows": "rows_removed_by_sanitizer",
    "skipped_openai_no_key": "openai_key_missing",
}

BAD_NAME_RE = re.compile(
    r"\b("
    r"year\s+ended|schedule|remuneration|expenses?|unaudited|audited|"
    r"signature|signatures?|total|subtotal|page|note|notes?|"
    r"docusign|envelope|indigenous\s+services\s+canada|services\s+canada|"
    r"isc|aadnc|aandc|sac|government\s+of\s+canada|"
    r"chief\s+and\s+council|chief\s+and\s+councillors?|"
    r"number\s+of\s+months|travel|payments?|per\s+diems?|credit\s+card|"
    r"acknowledged|approved|accompanying|statement|financial|"
    r"project|program|contract|construction|maintenance|repair|renovation|"
    r"insurance|administration|audit|legal|professional|revenue|income|"
    r"asset|liability|payable|receivable|"
    r"director|manager|finance|post\s+secondary|lands\s+manager|"
    r"education|coordinator|administrator|employee"
    r")\b",
    re.IGNORECASE,
)

ROLE_RE = re.compile(r"\b(chief|councillor|councilor|council)\b", re.IGNORECASE)
ROLE_PREFIX_RE = re.compile(r"^(chief|councillor|councilor|council\s+member|council)\s+", re.IGNORECASE)
ROLE_SUFFIX_RE = re.compile(r"\s+(chief|councillor|councilor|council\s+member|council)$", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"\s+")
REVERSED_HEADER_RE = re.compile(r"(latoT|rehtO|yralaS|shtnoM|emaN|noitisoP|levarT)")


def clean_text(value):
    return WHITESPACE_RE.sub(" ", str(value or "").replace("\u00a0", " ")).strip()


def is_remuneration(filing):
    return "remuneration" in clean_text(filing.get("docType")).lower()


def clean_name(value):
    text = clean_text(value).strip(" -*:;,.	")
    text = re.sub(r"\*+$", "", text).strip()
    had_role_prefix = bool(ROLE_PREFIX_RE.search(text))
    text = ROLE_PREFIX_RE.sub("", text).strip()
    text = ROLE_SUFFIX_RE.sub("", text).strip()
    if had_role_prefix or is_uppercase_last_first_candidate(text):
        text = reorder_last_first_name(text)
    text = normalize_name_case(text)
    return text


def is_uppercase_last_first_candidate(text):
    tokens = text.split()
    if len(tokens) < 2 or len(tokens) > 4:
        return False
    comparable = "".join(tokens).replace(".", "").replace("-", "").replace("'", "")
    return comparable.isalpha() and comparable.isupper()


def normalize_name_case(text):
    if not text or not text.replace(".", "").replace("-", "").replace("'", "").replace(" ", "").isupper():
        return text

    def format_token(token):
        return "-".join(
            "'".join(piece[:1].upper() + piece[1:].lower() if piece else piece for piece in part.split("'"))
            for part in token.split("-")
        )

    return " ".join(format_token(token) for token in text.split())


def reorder_last_first_name(text):
    tokens = text.split()
    if len(tokens) < 2 or len(tokens) > 4:
        return text
    comparable = "".join(tokens).replace(".", "").replace("-", "").replace("'", "")
    if not comparable.isalpha() or not comparable.isupper():
        return text
    return " ".join(tokens[1:] + tokens[:1])


def normalize_role(value):
    text = clean_text(value).lower()
    if "chief" in text:
        return "Chief"
    if "councillor" in text or "councilor" in text or "council" in text:
        return "Councillor"
    return clean_text(value) or "Councillor"


def parse_money(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else float(value)

    text = clean_text(value)
    if not text or text in {"-", "--", "---", "N/A", "n/a"}:
        return None

    negative = text.startswith("(") and text.endswith(")")
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if cleaned in {"", "-", "."}:
        return None

    try:
        amount = float(cleaned)
    except ValueError:
        return None

    if negative and amount > 0:
        amount = -amount
    return int(amount) if amount.is_integer() else amount


def is_bad_name(name):
    text = clean_name(name)
    if not text or not re.search(r"[A-Za-z]", text):
        return True
    if REVERSED_HEADER_RE.search(text):
        return True
    if BAD_NAME_RE.search(text):
        return True
    if ROLE_RE.fullmatch(text):
        return True
    if len(text) > 90:
        return True
    tokens = text.split()
    if len(tokens) > 7:
        return True
    return False


def sane_months(value):
    amount = parse_money(value)
    if amount is None:
        return None
    if 0 < amount <= 24:
        return amount
    return None


def total_from_components(person):
    return sum(person.get(key) or 0 for key in PAYMENT_KEYS)


def repair_shifted_payment_columns(person):
    changed = False

    remuneration = person.get("remuneration") or 0
    travel = person.get("travel") or 0
    expenses = person.get("expenses") or 0
    credit_card = person.get("creditCard") or 0
    other = person.get("otherPayments") or 0
    total = person.get("total") or total_from_components(person)

    # Some text-extracted PDFs expose a subtotal column after travel. If that
    # subtotal is treated as expenses, totals are doubled. Keep the component
    # columns we can identify and recalculate the total below.
    if expenses and remuneration and nearly_equal(expenses, remuneration + travel):
        person["expenses"] = None
        expenses = 0
        changed = True

    base_without_other = remuneration + travel + expenses + credit_card
    if other and base_without_other and amounts_match_as_echo(other, base_without_other):
        person["otherPayments"] = None
        changed = True

    if total > 30000:
        for key in ("travel", "expenses", "creditCard", "otherPayments"):
            amount = person.get(key)
            if amount is not None and 0 < abs(amount) <= 24:
                person[key] = None
                changed = True

    return changed


def has_months_shift(person):
    remuneration = person.get("remuneration")
    total = person.get("total") or total_from_components(person)
    if remuneration is None:
        return False
    return 0 < remuneration <= 24 and total > 1000


def has_low_remuneration_shift(person):
    remuneration = person.get("remuneration")
    total = person.get("total") or total_from_components(person)
    if remuneration is None:
        return False
    return 0 < remuneration <= 1000 and total > 30000


def has_small_component_shift(person):
    total = person.get("total") or total_from_components(person)
    if total <= 30000:
        return False
    for key in ("travel", "expenses", "creditCard", "otherPayments"):
        amount = person.get(key)
        if amount is not None and 0 < abs(amount) <= 24:
            return True
    return False


def nearly_equal(left, right):
    if not left or not right:
        return False
    return abs(left - right) <= max(2, abs(right) * 0.02)


def amounts_match_as_echo(left, right):
    """Match duplicated extracted totals without collapsing nearby real amounts."""
    if not left or not right:
        return False
    return abs(left - right) <= max(2, abs(right) * 0.001)


def has_component_echo(person):
    remuneration = person.get("remuneration") or 0
    expenses = person.get("expenses") or 0
    total = person.get("total") or total_from_components(person)
    if total <= 1000:
        return False
    travel = person.get("travel") or 0
    if nearly_equal(expenses, remuneration + travel) and total > expenses + 10000:
        return True
    return False


def has_total_echo(person):
    """Detect rows where a total column was also treated as another payment."""
    remuneration = person.get("remuneration") or 0
    travel = person.get("travel") or 0
    expenses = person.get("expenses") or 0
    credit_card = person.get("creditCard") or 0
    other = person.get("otherPayments") or 0
    total = person.get("total") or 0
    base = remuneration + travel + expenses + credit_card
    if base <= 0 or other <= 0 or total <= 0:
        return False
    return amounts_match_as_echo(other, base) and nearly_equal(total, base + other)


def suspicious_filing_reasons(people):
    if not people:
        return []

    reasons = []
    if len(people) == 1:
        reasons.append("only one parsed row")

    month_shift_count = sum(1 for person in people if has_months_shift(person))
    if month_shift_count:
        reasons.append("month values appear in money columns")

    low_remuneration_count = sum(1 for person in people if has_low_remuneration_shift(person))
    if low_remuneration_count:
        reasons.append("implausibly small remuneration values appear in money columns")

    small_component_count = sum(1 for person in people if has_small_component_shift(person))
    if small_component_count:
        reasons.append("small month-like values appear in payment columns")

    component_echo_count = sum(1 for person in people if has_component_echo(person))
    if component_echo_count:
        reasons.append("payment columns appear duplicated or shifted")

    total_echo_count = sum(1 for person in people if has_total_echo(person))
    if total_echo_count:
        reasons.append("total column appears duplicated into payment columns")

    chief_count = sum(1 for person in people if normalize_role(person.get("role")) == "Chief")
    if chief_count == 0 and len(people) <= 3:
        reasons.append("no Chief row in a small parsed filing")

    return reasons


def add_warning(filing, note):
    warnings = filing.setdefault("warnings", [])
    if note not in warnings:
        warnings.append(note)


def set_technical_status(filing, status):
    if status in (None, "", "not_applicable", "not_required", "not_posted"):
        return
    filing["technical_status"] = TECHNICAL_STATUS_MAP.get(status, status)


def normalize_filing_status(filing):
    status = filing.get("parse_status")

    if not is_remuneration(filing):
        if status != "not_required":
            set_technical_status(filing, status)
            filing["parse_status"] = "not_required"
        return

    if not filing.get("posted"):
        if status != "not_posted":
            set_technical_status(filing, status)
            filing["parse_status"] = "not_posted"
        return

    people = filing.get("people") or []
    if people and str(status or "").startswith("ok_"):
        return

    public_status = PUBLIC_STATUS_MAP.get(status)
    if public_status and public_status != status:
        set_technical_status(filing, status)
        filing["parse_status"] = public_status
        if status == "error_openai":
            add_warning(filing, "OpenAI-assisted extraction needs review")


def sanitize_person(person):
    if not isinstance(person, dict):
        return None, "not_object"

    cleaned = dict(person)
    cleaned["name"] = clean_name(cleaned.get("name"))
    if is_bad_name(cleaned["name"]):
        return None, "bad_name"

    cleaned["role"] = normalize_role(cleaned.get("role"))
    cleaned["months"] = sane_months(cleaned.get("months"))

    for key in ALL_MONEY_KEYS:
        cleaned[key] = parse_money(cleaned.get(key))

    had_expense_components = any(
        cleaned.get(key) is not None for key in ("travel", "expenses", "creditCard")
    )
    had_other_component = cleaned.get("otherPayments") is not None
    shifted_columns_fixed = repair_shifted_payment_columns(cleaned)

    # Canonical fields may have been calculated before a shifted raw column was
    # repaired. Rebuild them from the repaired source components so stale
    # values cannot duplicate a subtotal or total during validation.
    if had_expense_components:
        cleaned["travelExpenses"] = sum(
            cleaned.get(key) or 0 for key in ("travel", "expenses", "creditCard")
        )
    if had_other_component:
        cleaned["other"] = cleaned.get("otherPayments") or 0

    component_total = total_from_components(cleaned)
    current_total = cleaned.get("total")
    max_component = max((cleaned.get(key) or 0 for key in PAYMENT_KEYS), default=0)

    changed_total = False
    if component_total > 0:
        # Keep a valid PDF total, but repair totals that are missing, date-like,
        # lower than a component, or far away from the visible component sum.
        if (
            current_total is None
            or current_total <= 31
            or current_total < max_component
            or abs(current_total - component_total) > max(5, component_total * 0.08)
        ):
            cleaned["total"] = int(component_total) if float(component_total).is_integer() else component_total
            changed_total = True
    elif not current_total or current_total <= 31:
        return None, "no_money"

    largest_money = max((abs(cleaned.get(key) or 0) for key in ALL_MONEY_KEYS), default=0)
    if largest_money <= 31:
        return None, "date_like_money"

    if changed_total and shifted_columns_fixed:
        cleaned = parser_quality.normalize_person(cleaned)
        return cleaned, "fixed_shifted_columns_and_total"
    if shifted_columns_fixed:
        cleaned = parser_quality.normalize_person(cleaned)
        return cleaned, "fixed_shifted_columns"
    cleaned = parser_quality.normalize_person(cleaned)
    return cleaned, "fixed_total" if changed_total else "ok"


def dedupe_people(people):
    chosen = {}
    removed = 0
    for person in people:
        key = (person.get("name", "").lower(), person.get("role", "").lower())
        previous = chosen.get(key)
        if previous is None:
            chosen[key] = person
            continue
        removed += 1
        if (person.get("total") or 0) > (previous.get("total") or 0):
            chosen[key] = person
    return list(chosen.values()), removed


def sanitize_filing(filing):
    normalize_filing_status(filing)

    people = filing.get("people") or []
    if not people:
        return 0, 0, 0

    cleaned_people = []
    removed = 0
    fixed = 0
    changed = 0
    for person in people:
        cleaned, status = sanitize_person(person)
        if cleaned is None:
            removed += 1
            continue
        if status == "fixed_total":
            fixed += 1
        if cleaned != person:
            changed += 1
        cleaned_people.append(cleaned)

    cleaned_people, duplicates = dedupe_people(cleaned_people)
    removed += duplicates

    reasons = suspicious_filing_reasons(cleaned_people)
    validation = parser_quality.validate_people(cleaned_people)
    filing["parse_confidence"] = validation["confidence"]
    filing["manual_review_required"] = validation["manual_review_required"]
    for warning in validation["warnings"]:
        add_warning(filing, warning)
    if validation["manual_review_required"]:
        reasons.append("parser confidence is low")
    else:
        cleaned_people = validation["people"]

    if reasons:
        removed += len(cleaned_people)
        cleaned_people = []
        add_warning(filing, "Quarantined parsed rows: " + "; ".join(reasons))

    if removed or fixed or changed or len(cleaned_people) != len(people):
        filing["people"] = cleaned_people
        add_warning(filing, f"Sanitized parsed rows: removed {removed}, fixed totals {fixed}")

    if people and not cleaned_people:
        set_technical_status(filing, filing.get("parse_status"))
        filing["parse_status"] = "pending_manual_review"

    normalize_filing_status(filing)
    return len(people), removed, fixed


def sanitize_data(data):
    inspected = 0
    removed = 0
    fixed = 0

    for band in data.get("bands", []):
        for filing in band.get("filings", []):
            before, filing_removed, filing_fixed = sanitize_filing(filing)
            if before:
                inspected += before
                removed += filing_removed
                fixed += filing_fixed

    data["band_count"] = len(data.get("bands", []))
    return inspected, removed, fixed


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "data.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    inspected, removed, fixed = sanitize_data(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"sanitized rows inspected: {inspected}")
    print(f"sanitized rows removed: {removed}")
    print(f"sanitized totals fixed: {fixed}")


if __name__ == "__main__":
    main()
