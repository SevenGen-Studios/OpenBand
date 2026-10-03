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
        'Statement of Financial Position', 'Statement of Financial Activities',
        'Statement of Revenues and Expenses', 'Statement of Revenues and Expenditures',
        'Schedule of Remuneration and Expenses', 'Chief and Councillors', 'Chief and Council',
        'Number of Months', 'Total Revenue', 'Total Expenses', 'Annual Surplus',
        'Annual Deficit', 'Accumulated Surplus', 'Net Financial Assets', 'For the year ended',
    ):
        pattern = r'\b' + r'\s*'.join(re.escape(word) for word in heading.split()) + r'\b'
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


def coordinate_lines(items):
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
    return "\n".join(" ".join(cell[3] for cell in sorted(row)) for row in rows)


def _rapidocr_text(image):
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
        return coordinate_lines([(item[0], item[1]) for item in result or []])
    if output.boxes is None or output.txts is None:
        return ""
    return coordinate_lines([(box.tolist(), text) for box, text in zip(output.boxes, output.txts)])


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
                        pages[page_number - 1] = _rapidocr_text(image)
                    image.unlink()
                    processed.append(page_number)
                    if stop_after is None and stop_when is not None and stop_when(pages):
                        stop_after = index + max(0, extra_pages)
                    if stop_after is not None and index >= stop_after:
                        break
                return {'status': 'ok_ocr_text' if any(pages) else 'error_ocr_empty',
                        'warnings': [], 'pages': pages, 'page_count': len(processed),
                        'page_numbers': processed,
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
