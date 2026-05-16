# Phase 4c-pivot Report (Notes 14/20)

## Changes
- `parsers/adapters/rusal.yaml`: 2 new sections (NOTE_14_INTANGIBLES, NOTE_20_PROVISIONS)
- `parsers/tests/smoke_rusal_note14_intangibles.py`: created
- `parsers/tests/smoke_rusal_note20_provisions.py`: created
- `parsers/pdf_parser.py`: NOT modified

## Smoke Tests

### Note 14 Intangibles (page 41)
- Blocks: cost, accum_amort
- Cost closing 2024: 3,224 | AccumAmort closing 2024: -1,023
- **NBV = 2,201 = DB intangibles (2,201) -- PASS**

### Note 20 Provisions (page 57)
- Block: provisions (2023 + 2024)
- 2023: 8 movements, closing = 383
- 2024: 9 movements, closing = 339
- **Sanity: 2/2 (100%) -- PASS**

### Note 15 Associates — SKIPPED
Years are in columns (2024 cols + 2023 cols side by side), not in row labels.
Current pivot parser assumes year_in_label. Note 15 needs a different approach
or a `pivot_year_in_columns` mode. Deferred to future phase.

## Regression
- IS/BS/CF/Inv/PPE/Debt: all exit=0

## Prod sanity
- us_steel BS: 0.000004
- rusal BS: 0.000004

## Status: PASS (2/2 new Notes, 1 deferred)

## Parser coverage summary
| Note | Method | Status |
|------|--------|--------|
| IS (face) | parse_section | 16/16 |
| BS (face) | parse_section | 25/27 |
| CF (face) | parse_section | 34/34 |
| Note 16 Inventory | parse_section | 6/6 |
| Note 13 PPE | parse_pivot_note | 12/12 |
| Note 14 Intangibles | parse_pivot_note | PASS |
| Note 15 Associates | -- | DEFERRED |
| Note 19 Debt Loans | parse_instrument_list | 7/8 |
| Note 20 Provisions | parse_pivot_note | 2/2 |
