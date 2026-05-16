# Phase 4c-tests Report

## Change
- `parsers/tests/test_parser_helpers.py`: +5 unit tests (149 → 248 lines)
  - `test_build_text_table_basic` — header + data row extraction
  - `test_build_text_table_no_years` — negative case, no years → empty
  - `test_build_text_table_notes_case` — Note 16-like structure
  - `test_fallback_activates_on_split_columns` — virtual table gives 2 years
  - `test_fallback_not_needed_when_table_has_two_years` — normal table no fallback

## Unit tests
- Before: 11/11
- After: **16/16**

## Smoke regression
- IS: 16/16 (100%)
- BS: 25/27 (93%)
- CF: 34/34 (100%)
- Inv: 6/6 (100%)

## Prod sanity
- us_steel BS: 0.000004
- rusal BS: 0.000004

## Status: PASS
