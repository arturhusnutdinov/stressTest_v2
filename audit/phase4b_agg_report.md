# Phase 4b-ii-agg Report

## Parser change
- Added `combine_from` field to compiled dict in `_map_rows()`
- After main row-matching loop: combine_from pass sums helper components per year
- Helper rows (prefix `_`) filtered from final `metrics` dict
- ~20 lines added to `parsers/pdf_parser.py`

## Yaml change
- BS.rows: 22 -> 38 (added 5 direct + 9 helpers + 3 aggregates, removed 1 old `other_ncl`)
- notes_only: 0 -> 11 (9 helpers + 2 DB-incompatible: taxes_payable, dividends_payable)

### New direct rows
| canonical | source | section |
|-----------|--------|---------|
| aoci | Currency translation reserve | equity |
| nci | Other reserves | equity |
| other_ca_tax | Current income tax receivables | current_assets |
| taxes_payable | Other tax payable | current_liab |
| dividends_payable | Dividends payable | current_liab |

### New aggregates (combine_from)
| aggregate | formula | 2024 value |
|-----------|---------|------------|
| other_ca | ST_inv + prepay_VAT + div_recv + deriv_CA | 881 |
| other_cl | advances + deriv_liab + provisions_cl | 542 |
| other_ncl | provisions_ncl + other_ncl_line | 362 |

## Unit tests
- 11/11 passed (9 existing + 2 new: `test_combine_from_basic`, `test_combine_from_partial_year`)

## IS regression
- Status: PASS (identical output before/after)
- Match rate: 16/16 (100%), Coverage: 145%

## BS smoke
- Coverage before: 22/22 (100%)
- Coverage after: 29/27 (107%)
- Match rate before: 20/22 (91%)
- Match rate after: **25/27 (93%)**
- New matches: aoci, nci, other_ca, other_ca_tax, other_cl (+5)
- N/A: investments_in_associates (DB uses `investments_lt`, different breakdown)
- Known mismatch: other_ncl (parser 362 vs DB 275, gap = lease_liab_nc(42) + employee_benefits(45) from Notes)
- notes_only skipped: taxes_payable (DB sign -157 vs parser +157), dividends_payable (no DB row)

## Prod sanity
- us_steel BS: 0.000004
- rusal BS: 0.000004

## Status: PASS

## Next
Phase 4b-iii (CF yaml extension)
