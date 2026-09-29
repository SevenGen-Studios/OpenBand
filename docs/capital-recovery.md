# Automated capital recovery

Accuracy checks are used instead of routine manual review: only candidates
that pass current-year, category-total and final-surplus reconciliation can
replace pending records. Uncertain files remain unpublished, not guessed.

## Bounded retries

Work on a copy of capital-data.json. The parser skips existing publishable
records and always preserves manually verified records. Do not enable paid
OpenAI fallback unless explicitly authorized.

```sh
cp capital-data.json /tmp/capital-recovery.json
python tools/capital_parser.py --province AB --unresolved-only \
  --year 2022-2023 --limit 10 --output /tmp/capital-recovery.json \
  --report /tmp/capital-recovery-report.json
python -m tools.merge_capital_recovery --recovery /tmp/capital-recovery.json
python -m unittest discover -s tests
```

The merge tool independently revalidates candidates, checks their fiscal year
and source URL, and does not overwrite existing usable or manually verified
records. Failed trial output stays separate from published data.

## Scanned documents

GitHub Actions installs Tesseract and Poppler for free OCR. They are not
installed in the local environment used for this recovery pass. The optional
Docling tier also runs locally and is off by default; it has a conversion
timeout and model-download/runtime overhead. Raw cells are preserved where
possible. Missing OCR dashes and unaligned merged rows stay blocked.

Passing mathematical checks is automated validation, not an independent audit
of every source figure. Coverage figures count available summaries, not proof
that every field in an audited statement was extracted. Missing ancillary
metrics remain null, and failed candidates do not inflate coverage.
