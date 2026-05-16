# Phase 4b-ii Report

## Changes
- rusal.yaml: BS section added (22 rows, 5 section_markers, 2 anchors)
- parsers/tests/smoke_rusal_bs_2024.py: created (126 lines)

## BS Smoke Test
- Page: 11
- Years: [2025, 2024, 2023]
- Match: 15/16 (94%)
- Coverage: 16/22 (73%)
- Status: PASS

## Matched BS Metrics (15/16)
accounts_payable, accounts_receivable, apic, cash, dta, dtl, intangibles,
inventory, long_term_debt, ppe_net, retained_earnings, share_capital,
short_term_debt, total_assets, total_equity

## N/A (1)
investments_in_associates: parsed 4,868 but no DB match (metric name differs: DB has investments_lt)

## Not Found by Parser (6)
other_nca, other_ncl, total_ca, total_cl, total_nca, total_ncl
(section marker/pattern conflict — "Total non-current" triggers marker before pattern match)

## IS Regression
- Status: PASS (16/16, identical diff)

## Unit tests
- 7/7 passed

## Prod sanity
- us_steel BS: 0.000004
- rusal BS: 0.000004

## Artifacts
- audit/phase4b_ii_smoke_report.md
- audit/phase4b_ii_parse_result.json

## Next step
Phase 4b-iii (CF yaml extension)
