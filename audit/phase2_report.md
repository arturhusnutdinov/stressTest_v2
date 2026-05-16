# Phase 2 Report

## Inputs
- Decision Table (inline): 15 REMOVE, 6 FLIP, 2 ADD

## Changes Applied
- **xlsx v2:** `companies/rusal/data/rusal_unified_complete_v2.xlsx`
- **Removed:** 15 empty metric rows from history_is (rnd, depreciation_owned, depreciation_rou, amortization, lease_interest*, dep_rou*, lease_expense_operating, gain_loss_on_disposal, other_income, other_expense, eps_basic, eps_diluted)
- **Flipped signs:** 6 values (ppe_accum_dep years 2015, 2016, 2018, 2019, 2022, 2023: negative → positive)
- **Added rows:** 2 (ebitda_standard in IS, investments_in_associates in BS — empty, for Phase 4)
- **Loader yaml:** +2 lines in key_optional (ebitda_standard, investments_in_associates)

## DB State After Reload
- 1906 rows loaded, 0 errors
- ppe_accum_dep: **all 15 years positive** ✅
- ebitda_standard: 0 rows (empty, as expected)
- investments_in_associates: 0 rows (empty, as expected)

## Round-trip Test
- **Rusal BS: 0.0000** ✅ (threshold < 1.0)
- **US Steel BS: 0.0000** ✅ (unchanged)

## Status
**PASS** ✅

## Artifacts
- `audit/phase2_backup/` — backups for rollback
- `audit/phase2_xlsx_changes.log` — detailed change log
- `audit/phase2_baseline_pre.txt` — pre-change baseline
- `audit/phase2_test_result.json` — test results
- `companies/rusal/data/rusal_unified_complete_v2.xlsx` — v2 template
