"""Small, dependency-light local OCR adapter for scanned FNFTA PDFs.

The production workflow installs the free Poppler and Tesseract command-line
tools. Keeping them behind this adapter makes OCR optional: a developer without
either binary still gets the normal text stage, with a clear reason recorded for
the skipped OCR stage. Paid API fallback is controlled separately and is never
enabled implicitly by this module.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


_RAPID_OCR = None


def _binary(env_name, default):
    configured = os.getenv(env_name, "").strip()
    return configured or shutil.which(default)


def availability():
    missing = []
    pdftoppm = _binary("OPENBAND_PDFTOPPM_BIN", "pdftoppm")
    tesseract = _binary("OPENBAND_TESSERACT_BIN", "tesseract")
    if not pdftoppm:
        missing.append("pdftoppm")
    rapidocr = False
    if not tesseract:
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


def ocr_pdf_bytes(pdf_bytes, max_pages=None, dpi=None, timeout=None):
    """Render and OCR a bounded number of pages, returning page text and status."""
    tools = availability()
    if not tools["available"]:
        return {
            "status": "skipped_ocr_unavailable",
            "warnings": ["Local OCR unavailable; missing " + ", ".join(tools["missing"])],
            "pages": [],
        }

    max_pages = max_pages or int(os.getenv("OPENBAND_OCR_MAX_PAGES", "12"))
    dpi = dpi or int(os.getenv("OPENBAND_OCR_DPI", "220"))
    timeout = timeout or int(os.getenv("OPENBAND_OCR_TIMEOUT", "180"))

    try:
        with tempfile.TemporaryDirectory(prefix="openband-ocr-") as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source.pdf"
            prefix = temp / "page"
            source.write_bytes(pdf_bytes)

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
            "status": "error_ocr_timeout",
            "warnings": [f"Local OCR exceeded its {timeout}-second timeout"],
            "pages": [],
        }
    except Exception as exc:
        return {
            "status": "error_ocr_exception",
            "warnings": [f"Local OCR failed: {type(exc).__name__}: {exc}"],
            "pages": [],
        }
