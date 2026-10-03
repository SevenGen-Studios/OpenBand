"""Small, dependency-light local OCR adapter for scanned FNFTA PDFs.

The production workflow installs the free Poppler and Tesseract command-line
tools. Keeping them behind this adapter makes OCR optional: a developer without
either binary still gets the normal text stage, with a clear reason recorded for
the skipped OCR stage. Paid API fallback is controlled separately and is never
enabled implicitly by this module.
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


_RAPID_OCR = None


def normalize_ocr_headings(text):
    """Restore spaces in known report headings without changing names or figures."""
    for heading in (
        'Consolidated Statement of Operations', 'Statement of Operations',
        'Statement of Changes in Net Financial Assets', 'Statement of Changes in Net Financial Debt',
        'Statement of Cash Flows',
        'Statement of Financial Position', 'Statement of Financial Activities',
        'Statement of Revenues and Expenses', 'Statement of Revenues and Expenditures',
        'Schedule of Remuneration and Expenses', 'Chief and Councillors', 'Chief and Council',
        'Number of Months', 'Total Revenue', 'Total Expenses', 'Annual Surplus',
        'Annual Deficit', 'Accumulated Surplus', 'Net Financial Assets', 'For the year ended',
        'Surplus before the following', 'Other items', 'Other income (expense)',
        'Surplus before other items', 'Surplus (deficit) before other items',
        'Other income (expenses)', 'Other expenses', 'Other expenditures',
        'Deferred revenue', 'Loss on disposal of tangible capital assets',
        'C-92 Capacity Funding', 'Indigenous Services Canada', 'Health Canada',
        'First Nations and Inuit Health Branch', 'Employment and Social Development Canada',
        'Government of Alberta', 'First Nations Development Fund', 'Investment income',
        'Deficiency of revenues over expenses', 'Excess of revenue over expenditures',
        'Excess (shortfall) of revenue over expenditures',
        'Excess (deficiency) of revenue over expenditures',
        'Excess (deficiency) of revenue over expenses',
        'Excess (deficiency) of revenues over expenses',
        'Deficiency of revenue over expenses', 'Excess of revenue over expenses',
        'Surplus (deficit)',
        'Settlement Trust member distribution', 'Business profit distributions',
    ):
        pattern = r'(?<!\w)' + r'\s*'.join(re.escape(word) for word in heading.split()) + r'(?!\w)'
        text = re.sub(pattern, heading, text, flags=re.I)
    return text


def _binary(env_name, default):
    configured = os.getenv(env_name, "").strip()
    return configured or shutil.which(default)


def availability(engine=None):
    missing = []
    requested = engine or os.getenv('OPENBAND_OCR_ENGINE', '').strip().lower()
    pdftoppm = _binary("OPENBAND_PDFTOPPM_BIN", "pdftoppm")
    tesseract = None if requested in ('windows', 'rapidocr') else _binary("OPENBAND_TESSERACT_BIN", "tesseract")
    if not pdftoppm:
        missing.append("pdftoppm")
    rapidocr = False
    windows = False
    if requested == 'windows':
        try:
            import winocr  # noqa: F401
            windows = True
        except ImportError:
            missing.append('winocr (optional Windows OCR bindings)')
    elif not tesseract:
        try:
            from rapidocr_onnxruntime import RapidOCR  # noqa: F401

            rapidocr = True
        except ImportError:
            try:
                from rapidocr import RapidOCR  # noqa: F401

                rapidocr = True
            except ImportError:
                missing.append("tesseract or RapidOCR")
    return {
        "available": not missing,
        "pdftoppm": pdftoppm,
        "tesseract": tesseract,
        "rapidocr": rapidocr,
        "windows": windows,
        "missing": missing,
    }


def coordinate_lines(items, align_financial_columns=False, return_metadata=False):
    """Group OCR cells by baseline before ordering each financial row left-to-right."""
    cells = []
    for box, text in items:
        if not box or not str(text).strip():
            continue
        xs, ys = zip(*box)
        cells.append((min(xs), (min(ys) + max(ys)) / 2,
                      max(max(ys) - min(ys), 1), str(text).strip()))
    rows = []
    for cell in sorted(cells, key=lambda item: (item[1], item[0])):
        matches = [row for row in rows
                   if abs(cell[1] - row[0][1]) <= min(cell[2], row[0][2]) * 0.4]
        if matches:
            min(matches, key=lambda row: abs(cell[1] - row[0][1])).append(cell)
        else:
            rows.append([cell])
    lines = [" ".join(cell[3] for cell in sorted(row)) for row in rows]
    if align_financial_columns:
        aligned = financial_column_lines(items, rows, lines)
        if aligned is not None:
            result = {'text': '\n'.join(aligned), 'financialColumnsAligned': True}
            return result if return_metadata else result['text']
    result = {'text': '\n'.join(lines), 'financialColumnsAligned': False}
    return result if return_metadata else result['text']


def financial_column_lines(items, rows, lines):
    """Retain empty numeric columns only when year headings and amounts align."""
    header = normalize_ocr_headings('\n'.join(lines[:14]))
    if not re.search(r'statement of (?:consolidated )?(?:operations|financial activities|revenues|'
                     r'financial position|cash flows?|(?:changes? in )?net financial (?:assets|debt))', header, re.I):
        return None
    if re.search(r'\bcontents\b|by (?:program|segment)', header, re.I):
        return None
    amount_re = re.compile(r'^\(?\$?\s*-?\d[\d,]*(?:\.\d+)?\)?$')
    right = max((max(p[0] for p in box) for box, text in items), default=0)
    amounts = [(max(p[0] for p in box), str(text).strip(), max(p[1] for p in box)-min(p[1] for p in box))
               for box, text in items if amount_re.fullmatch(str(text).strip())
               and max(p[0] for p in box) > right * .55
               and not re.fullmatch(r'20\d{2}', str(text).strip())]
    clusters = []
    for x, text, height in sorted(amounts):
        if not clusters or x - clusters[-1][-1][0] > max(10, height * .6):
            clusters.append([])
        clusters[-1].append((x, text, height))
    clusters = [group for group in clusters if len(group) >= 3]
    centers = [sum(x for x, _, _ in group) / len(group) for group in clusters]
    edge_by_cell = {(min(p[0] for p in box), str(text).strip()): max(p[0] for p in box) for box,text in items}
    headings, matched_centers = None, None
    for row in rows[:14]:
        years = [cell for cell in sorted(row) if re.fullmatch(r'20\d{2}', cell[3])]
        if len(years) not in (2, 3):
            continue
        year_edges = [edge_by_cell[(cell[0], cell[3])] for cell in years]
        spacing = min(b-a for a,b in zip(year_edges, year_edges[1:]))
        # A fiscal-date caption may share the header baseline, but must remain
        # entirely to the left of the numeric year columns.
        if any(cell not in years and not re.fullmatch(
                r'\$|budget|actual|schedules?|notes?|\(?unaudited\)?|\(?audited\)?', cell[3], re.I)
               and edge_by_cell[(cell[0], cell[3])] >= years[0][0] - spacing * .1 for cell in row):
            continue
        candidates = [center for center in centers
                      if any(abs(center-edge) <= spacing * .3 for edge in year_edges)]
        # Schedule indices have no corresponding fiscal-year heading.
        if len(candidates) == len(years):
            headings, matched_centers = years, candidates
            break
    if not headings:
        return None
    centers = matched_centers
    spacing = min(b-a for a,b in zip(centers, centers[1:]))
    if any(abs(cell[0]-center) > spacing * .6 for cell, center in zip(headings, centers)):
        return None
    # Use original right edges rather than string width or inferred amounts.
    output = []
    for row, original in zip(rows, lines):
        if any(re.fullmatch(r'20\d{2}', cell[3]) for cell in row):
            output.append(original)
            continue
        slots, labels, used = ['-'] * len(centers), [], False
        for cell in sorted(row):
            text = cell[3]
            edge = edge_by_cell.get((cell[0], text), cell[0])
            if amount_re.fullmatch(text) and edge > centers[0] - spacing * .4:
                column = min(range(len(centers)), key=lambda i: abs(centers[i]-edge))
                if abs(centers[column]-edge) > spacing * .2 or slots[column] != '-':
                    return None  # Conflicting or shifted cells require another extraction.
                slots[column], used = text, True
            elif text != '$':
                if not (re.search(r'\bschedules?\b', header, re.I)
                        and re.fullmatch(r'\d{1,2}', text)
                        and edge < centers[0] - spacing * .4):
                    labels.append(text)
        output.append(' '.join(labels + slots) if used else original)
    return output


def _rapidocr_text(image, return_metadata=False):
    """Return reading-order text from RapidOCR when Tesseract is unavailable."""
    global _RAPID_OCR
    if _RAPID_OCR is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            threads = max(1, int(os.getenv('OPENBAND_OCR_THREADS', '1')))
            _RAPID_OCR = RapidOCR(intra_op_num_threads=threads, inter_op_num_threads=threads)
        except ImportError:
            from rapidocr import RapidOCR
            _RAPID_OCR = RapidOCR()
    output = _RAPID_OCR(str(image))
    if isinstance(output, tuple):
        result, _ = output
        items = [(item[0], item[1]) for item in result or []]
    elif output.boxes is None or output.txts is None:
        items = []
    else:
        items = [(box.tolist(), text) for box, text in zip(output.boxes, output.txts)]
    result = coordinate_lines(items, align_financial_columns=True, return_metadata=True)
    return result if return_metadata else result['text']


def _windows_text(image):
    """Read a local image with Windows OCR and preserve the word coordinates."""
    import asyncio
    import winocr
    from PIL import Image
    async def recognize():
        with Image.open(image) as source:
            bitmap = source.convert('RGB')
            bitmap.thumbnail((2200, 2200))
            return await winocr.recognize_pil(bitmap, 'en')
    result = asyncio.run(recognize())
    items = []
    for line in result.lines:
        for word in line.words:
            box = word.bounding_rect
            items.append(([[box.x, box.y], [box.x + box.width, box.y],
                           [box.x + box.width, box.y + box.height], [box.x, box.y + box.height]], word.text))
    return coordinate_lines(items)


def _rapidocr_text_isolated(image):
    """Keep ONNX DLL loading separate from Windows' native OCR runtime."""
    import sys
    result = subprocess.run(
        [sys.executable, '-c',
         'import sys; from tools.local_ocr import _rapidocr_text; print(_rapidocr_text(sys.argv[1]))',
         str(image)], capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=120, check=True, cwd=str(Path(__file__).resolve().parents[1]),
        env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    return result.stdout


def ocr_pdf_bytes(pdf_bytes, max_pages=None, dpi=None, timeout=None, page_numbers=None,
                  stop_when=None, extra_pages=0, engine=None):
    """Render and OCR a bounded number of pages, returning page text and status."""
    tools = availability(engine) if engine else availability()
    if not tools["available"]:
        return {
            "status": "skipped_ocr_unavailable",
            "warnings": ["Local OCR unavailable; missing " + ", ".join(tools["missing"])],
            "pages": [],
        }

    max_pages = max_pages or int(os.getenv("OPENBAND_OCR_MAX_PAGES", "12"))
    dpi = dpi or int(os.getenv("OPENBAND_OCR_DPI", "220"))
    timeout = timeout or int(os.getenv("OPENBAND_OCR_TIMEOUT", "180"))

    pages = []
    aligned_pages = []
    try:
        with tempfile.TemporaryDirectory(prefix="openband-ocr-") as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source.pdf"
            prefix = temp / "page"
            source.write_bytes(pdf_bytes)

            if page_numbers is not None:
                # Render selected pages individually to bound temporary disk usage.
                pages = [''] * max(page_numbers, default=0)
                processed, stop_after = [], None
                for index, page_number in enumerate(sorted(set(page_numbers))):
                    image = temp / 'selected.png'
                    rendered = subprocess.run(
                        [tools['pdftoppm'], '-f', str(page_number), '-l', str(page_number),
                         '-singlefile', '-r', str(dpi), '-png', str(source), str(temp / 'selected')],
                        capture_output=True, text=True, timeout=timeout, check=False)
                    if rendered.returncode or not image.exists():
                        raise RuntimeError(f'Page {page_number} rendering failed: {rendered.stderr[:300]}')
                    if tools['tesseract']:
                        recognized = subprocess.run(
                            [tools['tesseract'], str(image), 'stdout', '--psm', '6'],
                            capture_output=True, text=True, timeout=timeout, check=True)
                        pages[page_number - 1] = recognized.stdout or ''
                    elif tools.get('windows'):
                        pages[page_number - 1] = _windows_text(image)
                        # Financial PDFs normally print whole dollars or cents.
                        # A three-digit decimal can be a misread thousands comma;
                        # cross-check that page with the independent OCR engine.
                        if re.search(r'\b\d{1,3}\.\d{3}\b', pages[page_number - 1]):
                            pages[page_number - 1] = ''  # Unconfirmed numeric text cannot be published.
                            pages[page_number - 1] = _rapidocr_text_isolated(image)
                    else:
                        recognized = _rapidocr_text(image, return_metadata=True)
                        pages[page_number - 1] = recognized['text'] if isinstance(recognized, dict) else recognized
                        if isinstance(recognized, dict) and recognized['financialColumnsAligned']:
                            aligned_pages.append(page_number)
                    image.unlink()
                    processed.append(page_number)
                    if stop_after is None and stop_when is not None and stop_when(pages):
                        stop_after = index + max(0, extra_pages)
                    if stop_after is not None and index >= stop_after:
                        break
                return {'status': 'ok_ocr_text' if any(pages) else 'error_ocr_empty',
                        'warnings': [], 'pages': pages, 'page_count': len(processed),
                        'page_numbers': processed,
                        'financialColumnPages': aligned_pages,
                        'engine': 'windows_with_rapidocr_crosscheck' if tools.get('windows') else
                                  'tesseract' if tools['tesseract'] else 'rapidocr'}

            rendered = subprocess.run(
                [
                    tools["pdftoppm"],
                    "-f",
                    "1",
                    "-l",
                    str(max_pages),
                    "-r",
                    str(dpi),
                    "-png",
                    str(source),
                    str(prefix),
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            images = sorted(temp.glob("page-*.png"))
            if rendered.returncode != 0 or not images:
                detail = (rendered.stderr or rendered.stdout or "render produced no pages").strip()
                return {
                    "status": "error_ocr_render",
                    "warnings": [f"Local OCR PDF rendering failed: {detail[:500]}"],
                    "pages": [],
                }

            pages = []
            for image in images:
                if tools["tesseract"]:
                    recognized = subprocess.run(
                        [tools["tesseract"], str(image), "stdout", "--psm", "6"],
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        check=False,
                    )
                    if recognized.returncode != 0:
                        detail = (recognized.stderr or "unknown Tesseract error").strip()
                        return {
                            "status": "error_ocr_recognition",
                            "warnings": [f"Local OCR recognition failed: {detail[:500]}"],
                            "pages": pages,
                        }
                    pages.append(recognized.stdout or "")
                elif tools.get('windows'):
                    text = _windows_text(image)
                    pages.append(_rapidocr_text_isolated(image) if re.search(r'\b\d{1,3}\.\d{3}\b', text) else text)
                else:
                    pages.append(_rapidocr_text(image))

            if not any(page.strip() for page in pages):
                return {
                    "status": "error_ocr_empty",
                    "warnings": ["Local OCR returned no text"],
                    "pages": pages,
                }
            return {
                "status": "ok_ocr_text",
                "warnings": [],
                "pages": pages,
                "page_count": len(pages),
            }
    except subprocess.TimeoutExpired:
        return {
            "status": "error_ocr_partial_text" if any(pages) else "error_ocr_timeout",
            "warnings": [f"Local OCR exceeded its {timeout}-second timeout"],
            "pages": pages,
            "engine": 'windows_with_rapidocr_crosscheck' if tools.get('windows') else 'rapidocr',
        }
    except Exception as exc:
        return {
            "status": "error_ocr_partial_text" if any(pages) else "error_ocr_exception",
            "warnings": [f"Local OCR failed: {type(exc).__name__}: {exc}"],
            "pages": pages,
            "engine": 'windows_with_rapidocr_crosscheck' if tools.get('windows') else 'rapidocr',
        }
