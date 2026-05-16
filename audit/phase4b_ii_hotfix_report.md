# Phase 4b-ii-hotfix Report

## Change
- parsers/pdf_parser.py: section marker matching `p in norm` → `norm.startswith(p)`
- Lines changed: 1

## Unit tests
- 7/7 passed

## IS regression
- Status: PASS (16/16, identical diff)

## BS smoke
- Coverage before: 16/22 (73%)
- Coverage after:  22/22 (100%)
- Match rate:      20/22 (91%)
- Recovered: total_ca, total_nca, total_cl, total_ncl, other_nca, other_ncl
- N/A (1): investments_in_associates (parsed 4,868 but DB key = investments_lt)
- MISMATCH (1): other_ncl (parsed 119 vs DB 275 — DB includes additional items)

## Prod sanity
- us_steel BS: 0.000004
- rusal BS: 0.000004

## Status
PASS

## Artifacts
- audit/phase4b_ii_hotfix_backup/pdf_parser.py.bak
- audit/phase4b_ii_smoke_report.md (fresh)

## Next
Phase 4b-iii (CF yaml extension)
