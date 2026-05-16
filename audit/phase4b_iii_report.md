# Phase 4b-iii Report

## Changes
- `parsers/adapters/rusal.yaml`: CF section added (34 rows, 3 section_markers, 3 section_anchors)
- `parsers/tests/smoke_rusal_cf_2024.py`: created (108 lines) with fixed coverage formula
- `parsers/pdf_parser.py`: minimal fix — validate Strategy 1 year columns have data in body rows before returning (prevents false year-column detection on CF page where "2024" is split across table cells)

## CF Smoke Test
- Page: 13
- Years: [2024, 2023]
- **Match: 34/34 (100%)**
- **Coverage: 34/34 (100%)**
- Status: **PASS**

### CF row breakdown
- Operating: 17 rows (cfo_net_income through cfo_total)
- Investing: 8 rows (proceeds_ppe_disposal through cfi_total)
- Financing: 5 rows (cff_lt_debt_issuance through cff_total)
- Cash bridge: 4 rows (net_change_cash, cash_opening, fx_effect_cash, cash_closing)

### Split-row handling
Two metrics had values on a second row (pdfplumber word-wrap):
- `cfo_before_wc`: pattern matches "in working capital and provisions" (2nd row)
- `wc_payables`: pattern matches "received" (2nd row after "Increase/(decrease) in...payables and advances")

## IS regression
- Status: **identical** (16/16, 100%)

## BS regression
- Status: **identical** (25/27, 93%)

## Unit tests
- 11/11 passed

## Prod sanity
- us_steel BS: 0.000004
- rusal BS: 0.000004

## Parser fix: year column validation
Strategy 1 found col 8 as "2023" year column from header, but col 8 had no numeric data in body rows (data was in cols 7 and 9). Added validation: after Strategy 1, check each detected year column has numeric data in rows 5-20. If none pass, fall through to Strategy 2 which correctly maps page-text years to numeric columns.

## Artifacts
- audit/phase4b_iii_smoke_report.md
- audit/phase4b_iii_parse_result.json

## DB metrics NOT in parser scope (11 of 45)
These DB CF metrics are aliases or Notes-level detail not on the CF face:
- `cfo_da` (= depreciation), `net_income` (= cfo_net_income)
- `cfo_interest_paid` (= interest_paid), `cfo_interest_received` (= interest_received)
- `proceeds_borrowings` (= cff_lt_debt_issuance), `repayments_borrowings` (= cff_lt_debt_repayment)
- `taxes_paid` (= cfo_income_tax_paid), `interest_paid` (duplicated in DB)
- `deferred_income_taxes`, `op_lease_cash_cfo` — not on CF face
- `cff_dividends` (= 0, no PDF row), `fin_lease_principal_cff` (= -24, not on face)

## Next
Phase 4c (multi-year PDF parsing) or Phase 4b-iii-agg (if CF aggregates needed)
