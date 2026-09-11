# Alberta parser regression sources

These are text-only statement-of-operations excerpts extracted with PDFium from the public ISC PDFs downloaded on September 11, 2026. The fixtures deliberately retain original labels and budget/current/prior columns.

- `ab_438_2025_operations.txt`: Alexander First Nation, year ended March 31, 2025, PDF page 9. [ISC original](https://services.sac-isc.gc.ca/fnp/main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=438&FY=2024-2025&DOC=Audited%20consolidated%20financial%20statements&lang=eng). SHA-256 is recorded in `data.json`.
- `ab_437_2025_operations.txt`: Alexis Nakota Sioux Nation, year ended March 31, 2025, PDF page 7. [ISC original](https://services.sac-isc.gc.ca/fnp/main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=437&FY=2024-2025&DOC=Audited%20consolidated%20financial%20statements&lang=eng).

Alexander's excess of revenue over expenses must never become an expense row. Alexis's other-items subtotal must not be counted again after its components, and operating surplus is the final annual result after those adjustments.
