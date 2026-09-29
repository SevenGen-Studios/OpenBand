"""Read-only comparison: never writes the public financial datasets."""
import argparse
import json
from pathlib import Path
import time

from tools import capital_parser, docling_adapter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bands", default="467,464,442")
    parser.add_argument("--year", default="2024-2025")
    parser.add_argument("--output", default="/private/tmp/openband-docling-benchmark")
    parser.add_argument("--reuse-extraction", action="store_true",
                        help="Recheck saved PDFs and tables without downloads or model conversion")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    data = json.loads(Path("capital-data.json").read_text())["bands"]
    report = []
    for band_id in args.bands.split(","):
        band = data[band_id]
        source = band["years"][args.year]["sourceUrl"]
        entry = {"bandId": band_id, "community": band["name"], "year": args.year,
                 "sourceUrl": source, "verifiedAgainstPdf": False}
        started = time.monotonic()
        try:
            payload = (output / f"{band_id}.pdf").read_bytes() if args.reuse_extraction else capital_parser.fetch_pdf(source)
            if not args.reuse_extraction:
                (output / f"{band_id}.pdf").write_bytes(payload)
            baseline = capital_parser.parse_pdf_bytes(payload, source, args.year)
            extracted = (json.loads((output / f"{band_id}-extraction.json").read_text())
                         if args.reuse_extraction else docling_adapter.extract_pdf(payload))
            if not args.reuse_extraction:
                (output / f"{band_id}-extraction.json").write_text(json.dumps(extracted, indent=2))
            candidate = capital_parser.parse_structured_capital(extracted, source, args.year)
            candidate.update(capital_parser.validate_summary(candidate))
            entry.update({"baseline": baseline, "docling": candidate,
                          "conversionStatus": extracted["status"],
                          "conversionWarnings": extracted.get("warnings", [])})
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
        entry["seconds"] = round(time.monotonic() - started, 2)
        report.append(entry)
        (output / "report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps({k: entry[k] for k in ("community", "seconds")}, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
