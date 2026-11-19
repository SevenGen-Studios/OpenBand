# Independent OCR review queue

Generate the current work list from OpenBand’s dataset.

```sh
python3 tools/manual_review_report.py --ocr-queue data.json ocr-review-queue.json
```

Start with the latest fiscal year. Within that year, check manual-review filings first, then check published rows that lack documented independent OCR. A result marked `ok_ocr` means OCR extracted the rows. Verification requires the original PDF and a second reading of the published figures. Record the source hash, page, engine, and each discrepancy resolved during review. Work source gaps separately so a wrong file or missing name does not delay the available schedules.

## November 16, 2026 review batch

| 2025–26 filing | Named rows checked | Review outcome |
|---|---:|---|
| Ahtahkakoop Cree Nation | 18 | Reconciled the Chief and Council columns. Retained the separate Nation employee amounts as source context. |
| Fishing Lake First Nation | 9 | Reconciled every printed row total and the schedule footer. |
| Muskeg Lake Cree Nation | 7 | Reconciled the printed remuneration and expense subtotals using their separate components. |
| Sapotaweyak Cree Nation | 8 | Checked every named line. The page image confirmed both one-month terms that OCR missed. |
| Star Blanket Cree Nation | 5 | Reconciled the printed wages, travel, per diems, and contracts. |
| Fort McKay First Nation | — | The PDF labels rows by role. Named attribution needs a source that identifies each official. |
| Piapot First Nation | — | Show the separate unreimbursed member-payment adjustment alongside the printed total before publishing the named rows. |

Ten Manitoba 2024–25 schedules already checked in the [earlier OCR audit](manitoba-2024-25-ocr-audit.md) now carry document-bound OCR evidence in the dataset.

The queue accounts for all 1,684 posted remuneration records in the current dataset. Fifty-three carry evidence of independent OCR verification. The remaining 1,631 include 506 manual-review filings, 1,122 published schedules that need independent OCR, and three that need a usable source.
