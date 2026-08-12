"""Compatibility launcher for the OpenBand scraper.

Keeps the nightly run bounded and adds a text-parser fallback for FNFTA PDFs.
Some ISC PDFs do not expose clean table grids to pdfplumber, but their visible
text still contains the Chief and Council rows. This launcher tries structured
text and free local OCR first. OpenAI is an explicit, disabled-by-default last
resort.
"""

import base64
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

_real_urlopen = urllib.request.urlopen


def _patched_urlopen(request, *args, **kwargs):
    return _real_urlopen(request, *args, **kwargs)


urllib.request.urlopen = _patched_urlopen

import scraper  # noqa: E402
from tools import local_ocr  # noqa: E402
from tools import parser_quality  # noqa: E402

scraper.urllib.request.urlopen = _patched_urlopen

_openai_blocked_reason = None


def openai_fallback_enabled():
    """Require an explicit opt-in before any paid parser request is made."""
    return os.getenv("OPENBAND_ALLOW_OPENAI", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _json_from_model_text(text):
    text = (text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I).strip()
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return None
        return json.loads(match.group(0))


def _openai_file_part(pdf_bytes, pdf_url=None):
    if pdf_url:
        return {"type": "input_file", "file_url": scraper.normalize_pdf_url(pdf_url)}
    return {
        "type": "input_file",
        "filename": "filing.pdf",
        "file_data": "data:application/pdf;base64," + base64.b64encode(pdf_bytes).decode("ascii"),
    }


def _extract_with_openai_vision_fixed(pdf_bytes, pdf_url=None):
    global _openai_blocked_reason

    if not openai_fallback_enabled():
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
    if _openai_blocked_reason:
        return {
            "parse_status": "error_openai_quota",
            "warnings": [_openai_blocked_reason],
            "people": [],
        }

    prompt = (
        "Extract only the Chief and Council remuneration schedule from this PDF. "
        "Ignore audited financial statement project tables, notes, signatures, and totals-only rows. "
        "Return only JSON with this exact shape: "
        '{"people":[{"name":str,"role":str,"months":number|null,'
        '"remuneration":number|null,"travel":number|null,"expenses":number|null,'
        '"creditCard":number|null,"otherPayments":number|null,"total":number|null}]}. '
        'If no Chief and Council remuneration table is present, return {"people":[]}.'
    )
    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "max_output_tokens": 1600,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    _openai_file_part(pdf_bytes, pdf_url),
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
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = json.loads(resp.read().decode("utf-8"))

        text = scraper.response_output_text(raw)
        data = _json_from_model_text(text)
        if not data:
            return {
                "parse_status": "error_openai_empty",
                "warnings": ["OpenAI returned no parseable JSON"],
                "people": [],
            }

        rows = data.get("people", []) if isinstance(data, dict) else []
        people = []
        for row in rows:
            people.append(
                {
                    "name": str(row.get("name", "")).strip(),
                    "role": str(row.get("role", "")).strip() or "Council",
                    "months": scraper.parse_money(row.get("months")),
                    "remuneration": scraper.parse_money(row.get("remuneration")),
                    "travel": scraper.parse_money(row.get("travel")),
                    "expenses": scraper.parse_money(row.get("expenses")),
                    "creditCard": scraper.parse_money(row.get("creditCard")),
                    "otherPayments": scraper.parse_money(row.get("otherPayments")),
                    "total": scraper.parse_money(row.get("total")),
                }
            )
        return {
            "parse_status": "ok_openai",
            "warnings": [],
            "people": [p for p in people if p["name"]],
        }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1200]
        quota_error = exc.code == 429 and (
            "insufficient_quota" in body.lower()
            or "exceeded your current quota" in body.lower()
        )
        auth_error = exc.code in {401, 403}
        if quota_error:
            _openai_blocked_reason = (
                "OpenAI API quota is unavailable; remaining AI fallbacks were skipped"
            )
        return {
            "parse_status": (
                "error_openai_quota"
                if quota_error
                else "error_openai_auth"
                if auth_error
                else "error_openai_http"
            ),
            "warnings": [f"OpenAI HTTP {exc.code}: {body}"],
            "people": [],
        }
    except Exception as exc:
        return {
            "parse_status": "error_openai_exception",
            "warnings": [f"OpenAI parse failed: {type(exc).__name__}: {exc}"],
            "people": [],
        }


scraper.extract_with_openai_vision = _extract_with_openai_vision_fixed

# Extra Saskatchewan First Nations flagged during OpenBand coverage review.
# IDs are ISC First Nation Profile band numbers used by the FNFTA filing pages.
_EXTRA_BANDS = [
    {"id": 404, "name": "Big River First Nation", "province": "SK", "treaty": "Treaty 6"},
    {"id": 403, "name": "Birch Narrows Dene Nation", "province": "SK", "treaty": "Treaty 10"},
    {"id": 359, "name": "Black Lake Denesuline First Nation", "province": "SK", "treaty": "Treaty 8"},
    {"id": 351, "name": "Fond du Lac Denesuline First Nation", "province": "SK", "treaty": "Treaty 8"},
    {"id": 370, "name": "James Smith Cree Nation", "province": "SK", "treaty": "Treaty 6"},
    {"id": 393, "name": "Kawacatoose First Nation", "province": "SK", "treaty": "Treaty 4"},
]
_existing_ids = {band.get("id") for band in scraper.BANDS}
scraper.BANDS.extend(band for band in _EXTRA_BANDS if band["id"] not in _existing_ids)


def _build_direct_pdf_urls_with_current_year(band_id):
    fiscal_years = [
        "2024-2025",
        "2023-2024",
        "2022-2023",
        "2021-2022",
        "2020-2021",
        "2019-2020",
        "2018-2019",
        "2017-2018",
        "2016-2017",
        "2015-2016",
        "2014-2015",
        "2013-2014",
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
            filings.append({
                "year": fy,
                "docType": doc,
                "date": "See ISC",
                "href": f"{scraper.ISC_BASE}/DisplayBinaryData.aspx?{params}",
                "posted": True,
                "fallback": True,
            })
    return filings


scraper.build_direct_pdf_urls = _build_direct_pdf_urls_with_current_year

_ALLOWED_YEARS = {
    y.strip()
    for y in os.getenv("OPENBAND_PARSE_YEARS", "2024-2025,2023-2024,2022-2023").split(",")
    if y.strip()
}
_MAX_PDF_ATTEMPTS = int(os.getenv("OPENBAND_MAX_PDF_ATTEMPTS", "180") or "180")
_attempts = {"count": 0}
_original_should_parse_people = scraper.should_parse_people

_MONEY_RE = re.compile(r"\(?\$?\s*-?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?|\(?\$?\s*-?\d+(?:\.\d+)?\)?")
_SKIP_LINE_RE = re.compile(
    r"\b(total|signature|schedule|unaudited|audited|note|acknowledged|approved|remuneration|expenses|payments|months|position|name)\b",
    re.I,
)
_PROJECT_LINE_RE = re.compile(
    r"\b(project|program|contract|consulting|construction|maintenance|repair|renovation|insurance|administration|audit|legal|professional|revenue|income|asset|liability|payable|receivable)\b",
    re.I,
)
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z'.,() -]{1,90}\*?$")

# --- Keyword-aware FNFTA table parsing ---
_ROLE_WORD_RE = re.compile(r"\b(chief|councillor|councilor)\b", re.I)
_ROLE_ONLY_RE = re.compile(r"^\s*(chief|councillor|councilor)\s*$", re.I)
_COLUMN_HEADER_RE = re.compile(
    r"\b(name|position|title|role|months?|remuneration|salary|honou?raria|travel|per\s*diems?|expenses?|reimbursements?|credit\s*card|visa|mastercard|other|payments?|benefits?|incentives?|total)\b",
    re.I,
)
_TOTAL_ROW_RE = re.compile(r"^\s*(total|subtotal|grand\s+total)\b", re.I)


def _clean_cell(value):
    return " ".join(str(value or "").replace("\u00a0", " ").split()).strip()


def _row_text(row):
    return " ".join(_clean_cell(cell) for cell in row if _clean_cell(cell))


def _is_column_header_line(line):
    line = _clean_cell(line)
    if not line:
        return False
    low = line.lower()
    if not _COLUMN_HEADER_RE.search(low):
        return False
    if re.search(r"\b(schedule|for the year ended|unaudited|audited)\b", low) and not re.search(
        r"\b(name|position|role|months?|travel|credit|other|total)\b", low
    ):
        return False
    header_hits = {match.lower() for match in _COLUMN_HEADER_RE.findall(line)}
    if (
        len(header_hits) >= 4
        and re.search(r"\bmonths?\b", low)
        and re.search(r"\b(remuneration|salary|honou?raria|wages?)\b", low)
        and not re.search(r"\d{1,3}(?:,\d{3})+", line)
    ):
        return True
    money_count = len(_MONEY_RE.findall(line))
    return money_count <= 1 and not re.search(r"\b(chief|councillor|councilor)\b.+\d{2,}", low)


def _is_header_row(row):
    cells = [_clean_cell(cell) for cell in row]
    nonempty = [cell for cell in cells if cell]
    if not nonempty:
        return False
    keys = [key for key in (_column_key(cell) for cell in cells) if key]
    if len(set(keys)) >= 2:
        return True
    if len(nonempty) <= 1:
        return False
    return _is_column_header_line(_row_text(cells))


def _column_key(text):
    t = _clean_cell(text).lower()
    if not t:
        return None
    if re.search(r"\b(schedule|for the year ended|unaudited|audited)\b", t) and len(t.split()) > 4:
        return None
    if re.search(r"\b(number\s+of\s+)?months?\b", t):
        return "months"
    if re.search(r"\b(chief\s+and\s+council|chief\s+and\s+councillors|council\s+member|position|title|role)\b", t):
        return "role"
    if re.search(r"\bname\b", t):
        return "name"
    if "credit" in t or "visa" in t or "mastercard" in t:
        return "creditCard"
    if re.search(r"\b(total\s+paid|total)$|^total\b", t) and "remuneration" not in t:
        return "total"
    if re.search(r"\b(other|benefits?|incentives?)\b", t):
        return "otherPayments"
    if re.search(r"\b(remuneration|salary|honou?raria|wages?)\b", t):
        return "remuneration"
    if re.search(r"\b(travel|per\s*diems?|mileage|accommodation)\b", t):
        return "travel"
    if re.search(r"\b(expenses?|reimbursements?|reimbursement|allowances?)\b", t):
        return "expenses"
    if re.search(r"\bpayments?\b", t):
        return "otherPayments"
    return None


def _build_column_map(table):
    header_rows = []
    for row in table[:8]:
        cells = [_clean_cell(cell) for cell in row]
        if _is_header_row(cells):
            header_rows.append(cells)
    if not header_rows:
        return {}, ""

    width = max(len(row) for row in header_rows)
    combined = []
    for idx in range(width):
        parts = []
        for row in header_rows:
            if idx < len(row) and row[idx]:
                parts.append(row[idx])
        combined.append(" ".join(parts))

    column_map = {}
    for idx, heading in enumerate(combined):
        key = _column_key(heading)
        if key:
            column_map[idx] = key
    return column_map, " ".join(combined)


def _first_amount_in_cell(cell):
    cell = _clean_cell(cell)
    if not cell or cell in {"-", "--", "---"}:
        return None
    match = _MONEY_RE.search(cell.replace("$", " $ "))
    if not match:
        return None
    return _parse_amount(match.group(0).replace("$", "").strip())


def _looks_like_total(candidate, parts):
    if candidate is None or not parts:
        return False
    visible_sum = sum(value or 0 for value in parts)
    if visible_sum <= 0:
        return False
    return abs(candidate - visible_sum) <= max(5, visible_sum * 0.05)


def _assign_money_values(amounts, header_hint=""):
    amounts = [amount for amount in amounts if amount is not None]
    result = {
        "remuneration": None,
        "travel": None,
        "expenses": None,
        "creditCard": None,
        "otherPayments": None,
        "total": None,
    }
    if not amounts:
        return result

    hint = _clean_cell(header_hint).lower()
    has_total = bool(re.search(r"\btotal\b", hint))
    has_credit = bool(re.search(r"\b(credit|visa|mastercard)\b", hint))
    has_other = bool(re.search(r"\b(other|benefits?|incentives?)\b", hint))
    has_expense = bool(re.search(r"\b(expenses?|reimbursements?|allowances?)\b", hint))

    result["remuneration"] = amounts[0]
    if len(amounts) > 1:
        result["travel"] = amounts[1]

    if len(amounts) >= 6:
        result.update({
            "expenses": amounts[2],
            "creditCard": amounts[3],
            "otherPayments": amounts[4],
            "total": amounts[5],
        })
    elif len(amounts) == 5:
        result["expenses"] = amounts[2]
        if has_other and not has_credit:
            result["otherPayments"] = amounts[3]
        else:
            result["creditCard"] = amounts[3]
        result["total"] = amounts[4]
    elif len(amounts) == 4:
        if has_total or _looks_like_total(amounts[3], amounts[:3]):
            if has_other and not has_expense:
                result["otherPayments"] = amounts[2]
            else:
                result["expenses"] = amounts[2]
            result["total"] = amounts[3]
        else:
            result["expenses"] = amounts[2]
            result["otherPayments"] = amounts[3]
    elif len(amounts) == 3:
        if has_total or _looks_like_total(amounts[2], amounts[:2]):
            result["total"] = amounts[2]
        elif has_other and not has_expense:
            result["otherPayments"] = amounts[2]
        else:
            result["expenses"] = amounts[2]
    elif len(amounts) == 2 and has_total:
        result["travel"] = None
        result["total"] = amounts[1]

    if result["total"] is None:
        result["total"] = sum(result.get(key) or 0 for key in ["remuneration", "travel", "expenses", "creditCard", "otherPayments"])
    return result


def _assign_text_money_values(amounts, header_hint=""):
    """Map flattened text values using the wording of the visible PDF header."""
    amounts = [amount for amount in amounts if amount is not None]
    hint = _clean_cell(header_hint).lower()

    # Some schedules report honouraria, two separate "other remuneration"
    # columns, travel, and expenses. PDF text extraction flattens those five
    # headings, so preserve the travel/expense columns and combine only the
    # two remuneration columns into Other Payments.
    if (
        re.search(r"\bhonou?raria\b", hint)
        and "travel" in hint
        and "expense" in hint
        and len(re.findall(r"\bother\b", hint)) >= 2
        and len(re.findall(r"\bremuneration\b", hint)) >= 2
        and len(amounts) >= 5
    ):
        return {
            "remuneration": amounts[0],
            "travel": amounts[2],
            "expenses": amounts[3],
            "creditCard": None,
            "otherPayments": amounts[1] + amounts[4],
            "total": sum(amounts[:5]),
        }

    # Salary | Other Remuneration | Subtotal | Expenses | Total
    if (
        "salary" in hint
        and "subtotal" in hint
        and "expense" in hint
        and "total" in hint
        and len(amounts) >= 4
    ):
        remuneration = amounts[0]
        total = amounts[-1]
        expenses = amounts[-2]
        middle = amounts[1:-2]
        other = None
        if len(middle) >= 2:
            other = middle[0]
        elif len(middle) == 1 and not _looks_like_total(middle[0], [remuneration]):
            other = middle[0]
        return {
            "remuneration": remuneration,
            "travel": None,
            "expenses": expenses,
            "creditCard": None,
            "otherPayments": other,
            "total": total,
        }

    # Remuneration | Other Remuneration | Expenses | Other Entities
    if "other entities" in hint and "other remuneration" in hint and len(amounts) >= 4:
        return {
            "remuneration": amounts[0],
            "travel": None,
            "expenses": amounts[2],
            "creditCard": None,
            "otherPayments": amounts[1] + amounts[3],
            "total": sum(amounts[:4]),
        }

    # Remuneration | Travel and Per Diems | Other Payments
    if (
        re.search(r"\btravel\b|\bper\s*diems?\b", hint)
        and "other" in hint
        and "payment" in hint
        and len(amounts) >= 3
        and "total" not in hint
    ):
        return {
            "remuneration": amounts[0],
            "travel": amounts[1],
            "expenses": None,
            "creditCard": None,
            "otherPayments": amounts[2],
            "total": sum(amounts[:3]),
        }

    return _assign_money_values(amounts, header_hint)


def _strip_role_words(value):
    return scraper.clean_person_name(_ROLE_WORD_RE.sub(" ", _clean_cell(value)).strip(" -:\t")).replace("\u2019", "'")


def _extract_role_from_cells(cells):
    for cell in cells:
        match = _ROLE_WORD_RE.search(cell)
        if match:
            word = match.group(1).lower()
            return "Chief" if word == "chief" else "Councillor"
    return None


def _parse_keyword_table_row(row, column_map, header_hint):
    cells = [_clean_cell(cell) for cell in row]
    joined = _row_text(cells)
    if not joined or _is_header_row(cells) or _TOTAL_ROW_RE.search(joined):
        return None
    if _PROJECT_LINE_RE.search(joined) and not _ROLE_WORD_RE.search(joined):
        return None

    amounts_by_col = {idx: _first_amount_in_cell(cell) for idx, cell in enumerate(cells)}
    numeric_cols = [idx for idx, value in amounts_by_col.items() if value is not None]
    if len(numeric_cols) < 2:
        return None

    role = None
    for idx, key in column_map.items():
        if key == "role" and idx < len(cells):
            role = _extract_role_from_cells([cells[idx]]) or role
    role = role or _extract_role_from_cells(cells[: max(numeric_cols[0], 1)])

    name = None
    for idx, key in column_map.items():
        if key == "name" and idx < len(cells):
            candidate = _strip_role_words(cells[idx])
            if _looks_like_person_name(candidate):
                name = candidate
                break

    if not name:
        before_numbers = cells[: numeric_cols[0]]
        candidates = []
        for cell in before_numbers:
            if _ROLE_ONLY_RE.match(cell):
                continue
            candidate = _strip_role_words(cell)
            if _looks_like_person_name(candidate):
                candidates.append(candidate)
        if candidates:
            name = max(candidates, key=len)

    if not name:
        return None
    if not role:
        role = "Chief" if re.search(r"\bchief\b", joined, re.I) else "Councillor"

    months = None
    months_cols = [idx for idx, key in column_map.items() if key == "months"]
    for idx in months_cols:
        if idx < len(cells):
            amount = amounts_by_col.get(idx)
            if amount is not None and 0 < amount <= 24:
                months = amount
                break
    if months is None:
        for idx in numeric_cols:
            amount = amounts_by_col[idx]
            if amount is not None and 0 < amount <= 24 and idx <= numeric_cols[0] + 1:
                months = amount
                break

    mapped_money = {"remuneration": None, "travel": None, "expenses": None, "creditCard": None, "otherPayments": None, "total": None}
    for idx, key in column_map.items():
        if key in mapped_money and idx < len(cells):
            value = amounts_by_col.get(idx)
            if value is not None:
                mapped_money[key] = value

    if mapped_money["remuneration"] is not None or sum(1 for value in mapped_money.values() if value is not None) >= 2:
        if mapped_money["total"] is None:
            mapped_money["total"] = sum(mapped_money.get(key) or 0 for key in ["remuneration", "travel", "expenses", "creditCard", "otherPayments"])
        money = mapped_money
    else:
        money_amounts = []
        for idx in numeric_cols:
            value = amounts_by_col[idx]
            if value is None:
                continue
            if months is not None and idx in months_cols:
                continue
            if value <= 24 and idx <= numeric_cols[0] + 1:
                continue
            money_amounts.append(value)
        money = _assign_money_values(money_amounts, header_hint)

    if not any(money.get(key) for key in ["remuneration", "travel", "expenses", "creditCard", "otherPayments", "total"]):
        return None

    return {
        "name": name,
        "role": role,
        "months": months,
        **money,
    }


def _extract_people_from_keyword_table(table):
    if not table:
        return []
    column_map, header_hint = _build_column_map(table)
    people = []
    for row in table:
        person = _parse_keyword_table_row(row, column_map, header_hint)
        if person:
            people.append(person)
    return _dedupe_people(people)


def _parse_amount(value):
    return scraper.parse_money(value)


def _looks_like_person_name(value):
    text = scraper.clean_person_name(value).replace("\u2019", "'")
    if not text or _PROJECT_LINE_RE.search(text):
        return False
    if re.search(r"\b(chief|councillor|councilor|total|travel|expense|payment|salary|wage)\b", text, re.I):
        return False
    if len(re.findall(r"[A-Za-z]+", text)) < 2:
        return False
    return bool(_NAME_RE.match(text))


def _parse_text_line(line, allow_inferred_councillor=False, header_context=""):
    line = " ".join(str(line or "").replace("$", " $ ").split())
    # pdfplumber can split the leading digit from a comma-grouped amount
    # (for example "$ 9 0,000" for "$90,000"). Restrict the repair to a
    # currency-prefixed value so ordinary adjacent numeric columns are not
    # merged accidentally.
    line = re.sub(
        r"(\$\s*)(\d)\s+(\d{1,2}(?:,\d{3})+(?:\.\d+)?)",
        lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}",
        line,
    )
    if not line:
        return None

    has_role = re.search(r"\b(chief|councillor|councilor)\b", line, re.I)
    if _SKIP_LINE_RE.search(line) and not has_role:
        return None
    if _PROJECT_LINE_RE.search(line) and not has_role:
        return None
    if not has_role and not allow_inferred_councillor:
        return None

    matches = list(_MONEY_RE.finditer(line))
    values = []
    for match in matches:
        raw = match.group(0).replace("$", "").strip()
        amount = _parse_amount(raw)
        if amount is not None:
            values.append({"raw": raw, "amount": amount, "start": match.start(), "end": match.end()})
    if len(values) < 2:
        return None

    first_value = values[0]
    months = None
    money_values = values
    if first_value["amount"] <= 24 and "," not in first_value["raw"] and "." not in first_value["raw"]:
        months = first_value["amount"]
        money_values = values[1:]
    if len(money_values) < 2:
        return None

    name_part = line[: first_value["start"]].strip(" -:\t")
    role_match = re.search(r"\b(chief|councillor|councilor)\b", name_part, re.I)
    if role_match:
        role_word = role_match.group(1).lower()
        role = "Chief" if role_word == "chief" else "Councillor"
    else:
        role = "Councillor"

    name = _strip_role_words(name_part)
    if not _looks_like_person_name(name):
        return None

    amounts = [item["amount"] for item in money_values]
    money = _assign_text_money_values(amounts, header_context)

    return {
        "name": name,
        "role": role,
        "months": months,
        **money,
    }


def _dedupe_people(people):
    seen = set()
    clean = []
    for person in people:
        key = (person.get("name", "").lower(), person.get("role", "").lower())
        if not person.get("name") or key in seen:
            continue
        seen.add(key)
        clean.append(person)
    return clean


def _extract_people_from_text(pdf_bytes):
    if scraper.pdfplumber is None:
        return []
    pages = []
    with scraper.pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text(x_tolerance=1, y_tolerance=3) or "")
    return _extract_people_from_text_pages(pages)


def _extract_people_from_text_pages(pages):
    """Parse extracted or OCR-produced page text through the same row parser."""
    people = []
    for text in pages:
        page_is_schedule = bool(
            re.search(
                r"chief\s+and\s+council|chief\s+and\s+councillors|remuneration\s+and\s+expenses",
                text,
                re.I,
            )
        )
        header_context = ""
        in_data_section = False
        for line in text.splitlines():
            if _is_column_header_line(line):
                header_context = (header_context + " " + _clean_cell(line)).strip()
                header_hits = {
                    match.lower() for match in _COLUMN_HEADER_RE.findall(header_context)
                }
                in_data_section = in_data_section or (
                    "months" in header_context.lower()
                    and bool(
                        re.search(
                            r"\b(remuneration|salary|honou?raria|wages?)\b",
                            header_context,
                            re.I,
                        )
                    )
                    and len(header_hits) >= 3
                )
                continue
            if not page_is_schedule or not in_data_section:
                continue
            person = _parse_text_line(
                line,
                allow_inferred_councillor=True,
                header_context=header_context,
            )
            if person:
                people.append(person)
    return _dedupe_people(people)


def _stage(name, status, warnings=None):
    return {
        "stage": name,
        "status": status,
        "warnings": list(warnings or []),
    }


def _extract_remuneration_rows_enhanced(pdf_url):
    if not pdf_url:
        return {"parse_status": "no_pdf_url", "warnings": ["No PDF URL available"], "people": []}

    warnings = []
    stages = []
    try:
        pdf_bytes = scraper.fetch_url(scraper.normalize_pdf_url(pdf_url), timeout=30)
    except Exception as exc:
        return {
            "parse_status": "error_pdf_download",
            "warnings": [f"PDF download failed: {exc}"],
            "people": [],
        }

    if scraper.pdfplumber is not None:
        try:
            keyword_people = []
            fallback_people = []
            candidate_count = 0
            accepted_qualities = []
            source_totals = []
            with scraper.pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                    for table in page.extract_tables() or []:
                        quality = parser_quality.score_candidate_table(table, page_text)
                        if not quality["accepted"]:
                            continue
                        candidate_count += 1
                        accepted_qualities.append(quality)
                        source_total = parser_quality.source_total_from_table(table)
                        if source_total is not None:
                            source_totals.append(source_total)
                        parsed = _extract_people_from_keyword_table(table)
                        if parsed:
                            keyword_people.extend(parsed)
                        else:
                            fallback_people.extend(scraper.extract_people_from_table(table))
            people = _dedupe_people(keyword_people or fallback_people)
            if people and not _looks_project_heavy(people):
                method = "ok_pdf_keyword_table" if keyword_people else "ok_pdfplumber"
                note = "Parsed from keyword-aware PDF table extraction" if keyword_people else None
                if note:
                    warnings.append(note)
                if candidate_count > 1:
                    warnings.append("Multiple candidate Chief and Council tables found")
                quality = accepted_qualities[0] if accepted_qualities else None
                source_total = source_totals[0] if source_totals else None
                result = {"parse_status": method, "warnings": warnings, "people": people}
                result = parser_quality.apply_validation_metadata(result, source_total, quality)
                if not result.get("manual_review_required"):
                    result["parse_stages"] = stages + [_stage("local", method, result.get("warnings"))]
                    return result
                warnings.extend(result.get("warnings") or [])
                warnings.append("Local table output failed validation; trying the next free stage")
                stages.append(_stage("local", "failed_validation", result.get("warnings")))
            if people and _looks_project_heavy(people):
                warnings.append("Discarded table extraction because rows looked project-heavy")
            elif candidate_count == 0:
                warnings.append("No clear Chief and Council remuneration table found")
        except Exception as exc:
            warnings.append(f"PDF table extraction failed: {exc}")

        try:
            text_people = _extract_people_from_text(pdf_bytes)
            if text_people:
                result = {
                    "parse_status": "ok_pdf_text",
                    "warnings": warnings + ["Parsed from PDF text fallback"],
                    "people": text_people,
                }
                result = parser_quality.apply_validation_metadata(result)
                if not result.get("manual_review_required"):
                    result["parse_stages"] = stages + [_stage("local", "ok_pdf_text", result.get("warnings"))]
                    return result
                warnings.extend(result.get("warnings") or [])
                warnings.append("Local text output failed validation; trying free local OCR")
                stages.append(_stage("local", "failed_validation", result.get("warnings")))
        except Exception as exc:
            warnings.append(f"PDF text extraction failed: {exc}")
    else:
        warnings.append("pdfplumber unavailable")

    if not stages:
        stages.append(_stage("local", "no_reliable_rows", warnings))

    ocr_result = local_ocr.ocr_pdf_bytes(pdf_bytes)
    ocr_warnings = ocr_result.get("warnings") or []
    if ocr_result.get("pages"):
        ocr_people = _extract_people_from_text_pages(ocr_result["pages"])
        if ocr_people:
            result = parser_quality.apply_validation_metadata(
                {
                    "parse_status": "ok_ocr",
                    "warnings": warnings + ["Parsed via free local OCR fallback"] + ocr_warnings,
                    "people": ocr_people,
                }
            )
            if not result.get("manual_review_required"):
                result["parse_stages"] = stages + [_stage("ocr", "ok_ocr")]
                return result
            ocr_warnings = ocr_warnings + result.get("warnings", [])
            ocr_warnings.append("OCR output failed validation")
        else:
            ocr_result["status"] = "no_ocr_rows"
            ocr_warnings.append("Local OCR text contained no reliable official rows")
    stages.append(_stage("ocr", ocr_result.get("status", "no_reliable_rows"), ocr_warnings))
    warnings.extend(ocr_warnings)

    if not openai_fallback_enabled():
        warning = (
            "OpenAI fallback was not enabled; local parsing and free OCR were exhausted"
        )
        warnings.append(warning)
        stages.append(_stage("openai", "disabled", [warning]))
        return {
            "parse_status": "pending_openai_opt_in",
            "warnings": list(dict.fromkeys(warnings)),
            "people": [],
            "parse_stages": stages,
            "parse_confidence": "low",
            "manual_review_required": True,
        }

    ai_result = scraper.extract_with_openai_vision(pdf_bytes, pdf_url)
    if not ai_result.get("people") and ai_result.get("parse_status") == "error_openai_http":
        inline_result = scraper.extract_with_openai_vision(pdf_bytes)
        if inline_result.get("people"):
            inline_result["warnings"] = [
                "OpenAI file_url retry failed; parsed from inline PDF fallback"
            ] + inline_result.get("warnings", [])
            ai_result = inline_result
        else:
            inline_result["warnings"] = (
                ai_result.get("warnings", [])
                + ["OpenAI file_url retry failed; inline PDF retry also failed"]
                + inline_result.get("warnings", [])
            )
            ai_result = inline_result
    if ai_result.get("people"):
        ai_result["warnings"] = warnings + ["Parsed via OpenAI fallback"] + ai_result.get("warnings", [])
        ai_result = parser_quality.apply_validation_metadata(ai_result)
        if ai_result.get("manual_review_required"):
            warnings.extend(ai_result.get("warnings") or [])
            stages.append(_stage("openai", "failed_validation", ai_result.get("warnings")))
        else:
            ai_result["parse_stages"] = stages + [_stage("openai", "ok_openai")]
            return ai_result

    warnings.append("No extraction stage produced reliable remuneration rows")
    warnings.extend(ai_result.get("warnings", []))
    if not stages or stages[-1].get("stage") != "openai":
        stages.append(
            _stage("openai", ai_result.get("parse_status", "no_rows"), ai_result.get("warnings"))
        )
    return {
        "parse_status": ai_result.get("parse_status", "no_rows"),
        "warnings": warnings,
        "people": [],
        "parse_stages": stages,
        "parse_confidence": "low",
        "manual_review_required": True,
    }


def _looks_project_heavy(people):
    if not people:
        return False
    bad = sum(1 for person in people if _PROJECT_LINE_RE.search(person.get("name", "")))
    return bad >= max(1, len(people) // 2)


def _bounded_should_parse_people(filing):
    if filing.get("year") not in _ALLOWED_YEARS:
        return False
    return _original_should_parse_people(filing)


def _bounded_extract_remuneration_rows(pdf_url):
    if _attempts["count"] >= _MAX_PDF_ATTEMPTS:
        return {
            "parse_status": "skipped_run_limit",
            "warnings": [f"Skipped after {_MAX_PDF_ATTEMPTS} PDF parse attempts in this run"],
            "people": [],
        }
    _attempts["count"] += 1
    print(f"  parsing PDF {_attempts['count']}/{_MAX_PDF_ATTEMPTS}")
    return _extract_remuneration_rows_enhanced(pdf_url)


scraper.should_parse_people = _bounded_should_parse_people
scraper.extract_remuneration_rows = _bounded_extract_remuneration_rows

if __name__ == "__main__":
    print("OpenBand bounded run")
    print("  bands:", len(scraper.BANDS))
    print("  parse years:", ", ".join(sorted(_ALLOWED_YEARS)))
    print("  max PDF attempts:", _MAX_PDF_ATTEMPTS)
    scraper.main()
