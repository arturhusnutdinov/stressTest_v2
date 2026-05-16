# Phase 4c-pivot Note 15 Report

## Changes
- `parsers/pdf_parser.py`: +`_parse_wide_pivot_text()` method (80 lines), branch in `parse_pivot_note()` for `pivot_wide_table: true` (891 total lines)
- `parsers/adapters/rusal.yaml`: NOTE_15_ASSOCIATES section added
- `parsers/tests/smoke_rusal_note15_associates.py`: created
- `parsers/tests/test_parser_helpers.py`: +1 unit test (`test_wide_pivot_table_basic`)

## Note 15 Associates Smoke
- Page: 44
- Categories: [jv, associates, total]
- **Sanity: 4/4 (100%)**
  - closing_total_2024 = 4,868 (= BS investments_in_associates)
  - share_of_profits_2024 = 564 (= IS earnings_from_investees)
  - closing_total_2023 = 4,521
  - opening_total_2024 = 4,521 (= closing 2023)

## Design: wide-table mode
Note 15 has years in column headers (not row labels):
```
[JV_2024, Assoc_2024, Total_2024, JV_2023, Assoc_2023, Total_2023]
```
`_parse_wide_pivot_text()` handles this: detects years from header, expects n_cats*n_years numbers per line, maps by position.

## Regression
- All 8 existing smoke tests: exit=0
- Unit tests: 21/21

## Prod sanity
- us_steel BS: 0.000004, rusal BS: 0.000004

## Status: PASS

## Complete parser coverage
| Note | Method | Status |
|------|--------|--------|
| IS/BS/CF (face) | parse_section | PASS |
| Note 13 PPE | parse_pivot_note | 12/12 |
| Note 14 Intangibles | parse_pivot_note | PASS |
| Note 15 Associates | parse_pivot_note (wide) | **4/4** |
| Note 16 Inventory | parse_section | 6/6 |
| Note 19 Debt Loans | parse_instrument_list | 7/8 |
| Note 20 Provisions | parse_pivot_note | 2/2 |
