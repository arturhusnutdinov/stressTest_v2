# Phase 4c-note8 Report

## Changes
- `parsers/pdf_parser.py`: +`_parse_sequential_pivot_text()` (100 lines), branch in `parse_pivot_note()` for `pivot_sequential: true`, `default_year` support (996 total lines)
- `parsers/adapters/rusal.yaml`: NOTE_8_TAX_RECONCILIATION + NOTE_8_DTA_MOVEMENT sections
- `parsers/tests/smoke_rusal_note8_tax.py`: created
- `parsers/tests/test_parser_helpers.py`: +1 unit test

## Note 8 Smoke Test: 12/12 (100%)

### Tax Reconciliation (page 28)
- 9/10 categories parsed (missing: effect_rate_change — 3-line label)
- profit_before_tax_2024 = 858, tax_expense_2024 = 55 -- all exact

### DTA/DTL Movement (page 29)
- 7 categories × 2 years × 4 movements
- total_closing_2024 = -138 = DB dta(328) - dtl(466) -- exact cross-check
- opening_2024 = closing_2023 = -176 -- consistency verified

## Design
`_parse_sequential_pivot_text()`: 5th text-based parsing mode. Handles tables with separate year sub-blocks where rows=categories and columns=movements. `default_year` config for single-block tables (reconciliation).

## Regression
- All 9 existing smoke tests: exit=0
- Unit tests: 22/22
- Prod: us_steel 0.000004, rusal 0.000004

## Status: PASS

## Complete parser coverage (10 Notes)
| Note | Method | Result |
|------|--------|--------|
| IS/BS/CF face | parse_section | PASS |
| Note 8 Tax Recon | parse_pivot_note (sequential) | 6/6 |
| Note 8 DTA/DTL | parse_pivot_note (sequential) | 6/6 |
| Note 13 PPE | parse_pivot_note (text) | 12/12 |
| Note 14 Intangibles | parse_pivot_note (text) | PASS |
| Note 15 Associates | parse_pivot_note (wide) | 4/4 |
| Note 16 Inventory | parse_section (text fallback) | 6/6 |
| Note 19 Debt Loans | parse_instrument_list | 7/8 |
| Note 20 Provisions | parse_pivot_note (text) | 2/2 |
