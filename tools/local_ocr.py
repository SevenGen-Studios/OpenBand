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


def _binary(env_name, default):
    configured = os.getenv(env_name, "").strip()
    return configured or shutil.which(default)


def availability():
    missing = []
    pdftoppm = _binary("OPENBAND_PDFTOPPM_BIN", "pdftoppm")
    tesseract = _binary("OPENBAND_TESSERACT_BIN", "tesseract")
    if not pdftoppm:
        missing.append("pdftoppm")
    if not tesseract:
        missing.append("tesseract")
    return {
        "available": not missing,
        "pdftoppm": pdftoppm,
        "tesseract": tesseract,
        "missing": missing,
    }


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
