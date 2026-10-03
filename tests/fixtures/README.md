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
