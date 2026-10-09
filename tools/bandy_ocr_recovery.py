"""Free local OCR recovery for scanned corpus sources; all OCR figures stay in review."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import re
import sys
import time

from tools import bandy_financial as financial
from tools.bandy_corpus import atomic_json, mark_records, read_checkpoint
from tools.local_ocr import normalize_ocr_headings


def ocr_words(result, scale):
    words = []
    for line in result.get("lines", []):
        for word in line.get("words", []):
            box = word["bounding_rect"]
            words.append({"text": word["text"], "x0": box["x"]/scale,
                          "x1": (box["x"]+box["width"])/scale,
                          "top": box["y"]/scale, "bottom": (box["y"]+box["height"])/scale})
    return words


def recover_document(path, root, max_pages, retry_empty=False):
    sys.path.insert(0, str(Path("tmp/bandy-runtime").resolve()))
    import pypdfium2
    import winocr
    started = time.monotonic()
    entry = read_checkpoint(path)
    document = entry["document"]
    target = Path(root) / "ocr-results" / Path(path).name
    if target.exists():
        saved = read_checkpoint(target)
        if not retry_empty or (saved.get("result") or {}).get("records"):
            return {"documentKey": document["documentKey"], "status": saved["status"],
                    "recordCount": len((saved.get("result") or {}).get("records", [])), "resumed": True}
    result = None
    try:
        raw = (Path(root)/"pdf-cache"/f"{document['documentKey']}.pdf").read_bytes()
        pages = []
        with pypdfium2.PdfDocument(raw) as pdf:
            for index in range(min(max_pages, len(pdf))):
                with closing(pdf[index]) as page:
                    with closing(page.render(scale=2.5)) as bitmap:
                        recognized = winocr.recognize_pil_sync(bitmap.to_pil())
                    words = ocr_words(recognized, 2.5)
                    text = "\n".join(" ".join(w["text"] for w in line) for line in financial.lines_from_words(words))
                    pages.append({"page": index+1, "text": normalize_ocr_headings(text), "words": words})
            page_count = len(pdf)
        # An OCR word may include the currency symbol; retain the original word
        # and rectangle rather than inventing split glyph coordinates.
        financial.AMOUNT = re.compile(r"(?:\(?\$?-?\d[\d,]*(?:\.\d{1,2})?\)?|-)")
        result = financial.extract_fixture({"document": document, "pages": pages})
        mark_records(result, "ocr_source_requires_manual_review")
        for record in result["records"]:
            for ref in record["sourceReferences"]:
                ref["extractionMethod"] = "windows_ocr"
        status = "ocr_records_recovered" if result["records"] else "ocr_no_structured_records"
        recovered = {"document": deepcopy(document), "status": status, "result": result,
                     "ocrEngine": "Windows built-in OCR (winocr)", "ocrPages": len(pages),
                     "totalPages": page_count, "pageLimit": max_pages,
                     "elapsedSeconds": round(time.monotonic()-started, 2)}
    except Exception as exc:
        recovered = {"document": deepcopy(document), "status": "ocr_failed", "result": None,
                     "error": f"{type(exc).__name__}: {exc}", "elapsedSeconds": round(time.monotonic()-started, 2)}
    atomic_json(target, recovered, compressed=True)
    return {"documentKey": document["documentKey"], "status": recovered["status"],
            "recordCount": len((recovered.get("result") or {}).get("records", []))}


def merge_recoveries(root):
    root = financial.safe_output_directory(root)
    count = 0
    for path in (root / "ocr-results").glob("*.gz"):
        recovered = read_checkpoint(path)
        if not recovered.get("result"):
            continue
        native_path = root / "document-results" / path.name
        native = read_checkpoint(native_path)
        recovery_metadata = {k: v for k, v in recovered.items() if k not in ("document", "result")}
        if native.get("ocrRecoveryMerged") or (
            "ocrAddedRecords" in native and native.get("recovery", {}).get("ocr") == recovery_metadata
        ):
            continue
        native.setdefault("recovery", {})["ocr"] = recovery_metadata
        if not recovered["result"]["records"]:
            atomic_json(native_path, native, compressed=True)
            continue
        native_result = native.get("result") or {"records": [], "notes": [], "entities": [], "checks": [], "issues": {}}
        # Existing native observations retain priority; recovery only fills
        # missing metric/year/dimension keys. Original OCR results are retained.
        existing = {(r["fiscalYear"],r["metric"],r["dimension"]) for r in native_result["records"]}
        additional = [r for r in recovered["result"]["records"]
                      if (r["fiscalYear"],r["metric"],r["dimension"]) not in existing]
        native_result["records"].extend(additional)
        native_result["notes"].extend(recovered["result"]["notes"])
        native_result["entities"].extend(recovered["result"]["entities"])
        native_result["checks"].extend(recovered["result"]["checks"])
        native_result["issues"].update({f"ocr:{k}": v for k,v in recovered["result"]["issues"].items()})
        native["result"] = native_result
        native["status"] = "extracted" if any(r["validationStatus"] == "machine_checked" for r in native_result["records"]) else "manual_review"
        native["ocrAddedRecords"] = len(additional)
        native["ocrRecoveryMerged"] = True
        atomic_json(native_path, native, compressed=True)
        count += len(additional)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="research/bandy-financial/all-nations-2026-10-09")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--max-pages", type=int, default=16)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--merge", action="store_true")
    parser.add_argument("--retry-empty", action="store_true", help="Retry previously empty OCR results after parser improvements")
    args = parser.parse_args()
    root = financial.safe_output_directory(args.root)
    paths = []
    for path in (root/"document-results").glob("*.gz"):
        entry = read_checkpoint(path)
        if entry.get("requiresOcr") and entry["status"] != "failed":
            paths.append(path)
    if args.limit:
        paths = paths[:args.limit]
    print(f"OCR recovery candidates: {len(paths)}", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(recover_document, str(path), str(root), args.max_pages, args.retry_empty) for path in paths]
        completed = []
        for future in as_completed(futures):
            completed.append(future.result())
            progress = {"completed": len(completed), "total": len(paths),
                        "recoveredRecords": sum(x["recordCount"] for x in completed), "latest": completed[-1]}
            atomic_json(root/"ocr-progress.json", progress)
            print(json.dumps(progress), flush=True)
    if args.merge:
        print(f"Added {merge_recoveries(root)} OCR observations to research checkpoints; all remain manual review", flush=True)


if __name__ == "__main__":
    main()
