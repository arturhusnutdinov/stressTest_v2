# Phase 4c-lease Report

## Changes
- `parsers/adapters/rusal.yaml`: NOTE_13_LEASE section added
- `parsers/tests/smoke_rusal_note13_lease.py`: created

## ROU Assets (page 38)
- Categories: equipment, total (buildings value present but not captured as separate category)
- Data: closing 2024 = 45 mUSD = DB rou_asset (45)
- Structure: minimal 2-row pivot (opening + closing only, no intermediate movements)

## Lease liabilities
- Not in tabular format — text disclosure only:
  - Non-current 2024 = USD 42M, 2023 = USD 30M (from page 39 text)
  - Already in DB as lease_liab_noncurrent, lease_liab_current from BS face

## Regression
- All 7 smoke tests: ok
- Prod: us_steel 0.000004, rusal 0.000004

## Status: PASS

## Complete parser coverage (11 Notes + 3 face sheets)
| Note | Method | Status |
|------|--------|--------|
| IS/BS/CF face | parse_section | PASS |
| Note 8 Tax Recon | parse_pivot_note (sequential) | 12/12 |
| Note 13 PPE | parse_pivot_note (text) | 12/12 |
| Note 13 Lease ROU | parse_pivot_note (text) | 1/1 |
| Note 14 Intangibles | parse_pivot_note (text) | PASS |
| Note 15 Associates | parse_pivot_note (wide) | 4/4 |
| Note 16 Inventory | parse_section (text fallback) | 6/6 |
| Note 19 Debt Loans | parse_instrument_list | 7/8 |
| Note 20 Provisions | parse_pivot_note (text) | 2/2 |
