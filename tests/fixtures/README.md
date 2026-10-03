# Alberta parser regression sources

These are text-only statement-of-operations excerpts extracted with PDFium from the public ISC PDFs downloaded on September 11, 2026. The fixtures deliberately retain original labels and budget/current/prior columns.

- `ab_438_2025_operations.txt`: Alexander First Nation, year ended March 31, 2025, PDF page 9. [ISC original](https://services.sac-isc.gc.ca/fnp/main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=438&FY=2024-2025&DOC=Audited%20consolidated%20financial%20statements&lang=eng). SHA-256 is recorded in `data.json`.
- `ab_437_2025_operations.txt`: Alexis Nakota Sioux Nation, year ended March 31, 2025, PDF page 7. [ISC original](https://services.sac-isc.gc.ca/fnp/main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=437&FY=2024-2025&DOC=Audited%20consolidated%20financial%20statements&lang=eng).

Alexander's excess of revenue over expenses must never become an expense row. Alexis's other-items subtotal must not be counted again after its components, and operating surplus is the final annual result after those adjustments.
# Piikani 2020–2021

`ab_436_2021_operations.txt` contains the native text of PDF page 7 from the
[ISC audited statement](https://services.sac-isc.gc.ca/fnp/main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=436&FY=2020-2021&DOC=Audited%20consolidated%20financial%20statements&lang=eng).
It preserves the wrapped “before the undernoted” result and the reported $35,210
gain needed to reconcile the final $3,581,515 surplus.

`ab_444_2016_remuneration.txt` retains native text from PDF page 4 of Samson Cree Nation's 2015–2016 schedule. It includes the printed Chief/Councillor role, remuneration funding splits, five expense components and footer; the regression allows only the source's two-dollar aggregate rounding difference.
Source: [ISC schedule](https://services.sac-isc.gc.ca/fnp/main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=444&FY=2015-2016&DOC=Schedule%20of%20Remuneration%20and%20Expenses&lang=eng).

`ab_467_2025_ocr_boxes.json` retains RapidOCR cell positions from PDF page 6 of Fort McKay's 2024–2025 financial statements. The source page was rendered and visually checked: the actual revenue is $111,781,540, expenses are $72,291,197, and the final annual surplus is $7,308,429 after three reported deductions. Blank numeric columns and printed dashes must keep budget and comparative amounts out of the current-year totals.
Source: [ISC audited statement](https://services.sac-isc.gc.ca/fnp/main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=467&FY=2024-2025&DOC=Audited%20consolidated%20financial%20statements&lang=eng).

`ab_453_2022_operations.txt` preserves Lubicon Lake Band No. 453's native statement text on PDF page 7 for 2021–2022. The Covid-19 program label must remain intact; the unlabelled totals and amortization reconcile to the final $34,840,305 excess.
Source: [ISC audited statement](https://services.sac-isc.gc.ca/fnp/main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=453&FY=2021-2022&DOC=Audited%20consolidated%20financial%20statements&lang=eng).

`ab_467_2023_operations.txt` preserves Fort McKay's native statement text on PDF page 6 for 2022–2023. The reported business profit, depreciation and members savings plan distributions are deductions from the before-other-items surplus.
Source: [ISC audited statement](https://services.sac-isc.gc.ca/fnp/main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=467&FY=2022-2023&DOC=Audited%20consolidated%20financial%20statements&lang=eng).

`ab_446_2022_ocr_boxes.json` preserves RapidOCR cell positions from Tallcree's 2021–2022 statement on PDF page 9. The page was visually checked against the source: schedule indices must remain separate from year columns, the actual investment income is $46, and C-92 Capacity Funding is a printed expense of $79,227. Revenue $26,129,301 less expenses $25,790,087 and reported other expenses $1,050,007 equals the $710,793 final deficit.
Source: [ISC audited statement](https://services.sac-isc.gc.ca/fnp/main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=446&FY=2021-2022&DOC=Audited%20consolidated%20financial%20statements&lang=eng).
