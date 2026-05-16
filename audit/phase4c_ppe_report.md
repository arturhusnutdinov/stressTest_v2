# Phase 4c-ppe Report

## Changes
- `parsers/pdf_parser.py`: +2 new classes/methods (593 lines total)
  - `PivotNoteResult` dataclass (new return type for pivot Notes)
  - `parse_pivot_note()` public method — uses page text directly
  - `_parse_pivot_text()` private method — text-based pivot parsing
- `parsers/adapters/rusal.yaml`: NOTE_13_PPE section added
- `parsers/tests/smoke_rusal_note13_ppe.py`: created (154 lines)
- `parsers/tests/test_parser_helpers.py`: +2 unit tests (test_pivot_table_basic, test_pivot_table_two_years)

## Design: text-based pivot parsing
pdfplumber splits PPE numbers across columns ("18,623" → "18," + "623"). Instead of fighting table extraction, `parse_pivot_note()` works directly on `page.extract_text()` which has clean formatting. Key algorithm:
1. Detect category count from trailing data numbers (skip years 2015-2030)
2. Detect categories from header line containing "Total"
3. Scan lines for block switches, year markers, and movement rows
4. Extract last N values per data line (N = category count)

## PPE Smoke Test
- Page: 35
- Categories: ['buildings', 'equipment', 'lysers', 'other', 'assets', 'progress', 'total']
- Blocks: cost (2023, 2024), accum_dep (2023, 2024)
- **Sanity checks: 9/9 (100%)**
- **DB cross-checks: 3/3 (100%)**
- **Total: 12/12 (100%)**

## Regression
- IS: identical | BS: identical | CF: identical | Inv: identical

## Unit tests
- 18/18 passed

## Prod sanity
- us_steel BS: 0.000004
- rusal BS: 0.000004

## Status: PASS
