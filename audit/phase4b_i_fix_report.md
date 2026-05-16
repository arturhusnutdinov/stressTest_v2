# Phase 4b-i FIX Report

## Changes
- rusal.yaml: 6 patterns with anchored `$` replaced (removed `$` suffix)
- parsers/tests/smoke_rusal_is_2024.py: created as real file (125 lines, 4266 bytes)
- parsers/tests/test_parser_helpers.py: +2 regression guard tests
- smoke test: DB→mUSD unit conversion fix

## Unit tests
- 9/9 passed (7 original + 2 new regression guards)

## IS Smoke Test (strict sign, file-based)
- Page: 9
- Years: [2024, 2023]
- **Match: 16/16 (100%)**
- **Coverage: 16/11 (145%)**
- **Status: PASS**

## Prod sanity
- us_steel BS: 0.000004
- rusal BS: 0.000004

## Artifacts
- audit/phase4b_i_fix_backup/rusal.yaml.bak
- audit/phase4a_v2_parse_result.json (fresh)
- audit/phase4a_v2_smoke_report.md (fresh, file-based)
- parsers/tests/smoke_rusal_is_2024.py (real file)

## Next step
Phase 4b-ii (BS + CF yaml extension)
