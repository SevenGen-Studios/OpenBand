"""OpenBand v2 scraper launcher.

Keeps the restored compatibility scraper intact, then adds Saskatchewan bands
that were still missing from the coverage review before running the scrape.
"""

import run_scraper

# ISC First Nation Profile band numbers used by FNFTA filing pages.
EXTRA_BANDS = [
    {"id": 407, "name": "Witchekan Lake First Nation", "province": "SK", "treaty": "Treaty 6"},
    {"id": 408, "name": "Ocean Man First Nation", "province": "SK", "treaty": "Treaty 4"},
]

existing_ids = {band.get("id") for band in run_scraper.scraper.BANDS}
existing_names = {band.get("name", "").lower() for band in run_scraper.scraper.BANDS}
for band in EXTRA_BANDS:
    if band["id"] not in existing_ids and band["name"].lower() not in existing_names:
        run_scraper.scraper.BANDS.append(band)

if __name__ == "__main__":
    print("OpenBand v2 run")
    print("  bands:", len(run_scraper.scraper.BANDS))
    print("  parse years:", ", ".join(sorted(run_scraper._ALLOWED_YEARS)))
    print("  max PDF attempts:", run_scraper._MAX_PDF_ATTEMPTS)
    run_scraper.scraper.main()
