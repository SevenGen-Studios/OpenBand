"""Optional local Docling extraction, isolated to enforce a conversion timeout."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def extract_pdf(pdf_bytes):
    if os.getenv("OPENBAND_ENABLE_DOCLING", "").lower() not in {"1", "true", "yes"}:
        return {"status": "disabled", "pages": [], "tables": [], "warnings": []}
    if importlib.util.find_spec("docling") is None:
        return {"status": "unavailable", "pages": [], "tables": [],
                "warnings": ["Optional Docling dependency is not installed"]}
    try:
        with tempfile.TemporaryDirectory(prefix="openband-docling-") as folder:
            source = Path(folder) / "source.pdf"
            output = Path(folder) / "result.json"
            source.write_bytes(pdf_bytes)
            subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), str(source), str(output)],
                check=True, capture_output=True,
                timeout=int(os.getenv("OPENBAND_DOCLING_TIMEOUT", "300")),
            )
            return json.loads(output.read_text(encoding="utf-8"))
    except subprocess.TimeoutExpired:
        reason = "Docling exceeded its conversion time limit"
    except subprocess.CalledProcessError as exc:
        reason = "Local Docling conversion failed"
        # Retain the final diagnostic without dumping model/download logs.
        lines = (exc.stderr or b"").decode("utf-8", errors="replace").splitlines()
        if lines:
            reason += ": " + lines[-1][:300]
    except Exception as exc:
        reason = f"Local Docling extraction failed: {type(exc).__name__}"
    return {"status": "error", "pages": [], "tables": [], "warnings": [reason]}


def convert(source, output):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(enable_remote_services=False)
    options.do_ocr = True
    options.do_table_structure = True
    options.table_structure_options.mode = TableFormerMode.ACCURATE
    converter = DocumentConverter(format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=options)
    })
    document = converter.convert(
        source, max_num_pages=int(os.getenv("OPENBAND_DOCLING_MAX_PAGES", "100")),
        max_file_size=50 * 1024 * 1024,
    ).document
    pages = []
    for page_number in range(1, max(document.pages, default=0) + 1):
        if page_number not in document.pages:
            pages.append("")
            continue
        # Existing financial line parsers expect whitespace rather than Markdown
        # delimiters. Keep per-page headings and original labels for context.
        markdown = document.export_to_markdown(page_no=page_number)
        lines = [line.replace("|", " ") for line in markdown.splitlines()
                 if not (line.strip().startswith("|") and
                         set(line.replace("|", "").strip()) <= set("-: "))]
        pages.append("\n".join(lines))
    tables = []
    for table in document.tables:
        frame = table.export_to_dataframe(doc=document).fillna("")
        rows = [[str(cell) for cell in row] for row in frame.values.tolist()]
        headers = [str(column) for column in frame.columns]
        tables.append({"rows": [headers] + rows,
                       "rawRows": raw_table_rows(table.data),
                       "page": table.prov[0].page_no if table.prov else None,
                       "method": "docling_tableformer"})
    Path(output).write_text(json.dumps({
        "status": "ok", "pages": pages, "tables": tables, "warnings": [],
    }), encoding="utf-8")


def raw_table_rows(data):
    """Keep model cell boundaries and line breaks, without duplicating spans."""
    rows = [["" for _ in range(data.num_cols)] for _ in range(data.num_rows)]
    for cell in data.table_cells:
        row, column = cell.start_row_offset_idx, cell.start_col_offset_idx
        if 0 <= row < data.num_rows and 0 <= column < data.num_cols:
            rows[row][column] = cell.text
    return rows


if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])
