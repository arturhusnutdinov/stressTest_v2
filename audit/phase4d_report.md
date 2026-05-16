# Phase 4d Enrich Report

## Changes
- `tools/enrich_db_from_parser.py`: created (186 lines) — parser-to-DB pipeline
- `data_mart_v2.db`: enriched (INSERT only, backup at `audit/phase4d_enrich_backup_data_mart_v2.db`)

## Enrich Summary (live run)

| Metric | Count |
|--------|------:|
| Matched (parser == DB, 2% tol) | 75 |
| Inserted (new metrics) | 5 |
| PPE components inserted | 196 |
| Mismatches (NOT overwritten) | 2 |

### Inserted metrics (history_bs)
- `dividends_payable` = 5 mUSD
- `investments_in_associates` = 4,868 mUSD
- `inventory_raw_materials` = 1,447 mUSD
- `inventory_wip` = 848 mUSD
- `inventory_fg` = 2,182 mUSD

### Known mismatches (reported, not overwritten)
- `taxes_payable`: parser +157 vs DB -157 (sign convention)
- `other_ncl`: parser 362 vs DB 275 (Notes-level split: lease_liab + employee_benefits)

### PPE components (196 rows)
- 2 blocks (cost, accum_dep) x 2 years (2023, 2024)
- ~6 movements per block (additions, disposals, transfers, fx, depreciation_charge, impairment, closing)
- 7 categories (buildings, equipment, lysers, other, assets, progress, total)
- Plus snapshot types (gross, accumulated, net) per category per year

## DB state after enrich
- `inventory_raw_materials` 2024 = 1,447 mUSD
- `inventory_wip` 2024 = 848 mUSD
- `inventory_fg` 2024 = 2,182 mUSD
- `ppe_components` rusal rows = 196

## Model verification
- us_steel BS: 0.000004
- rusal BS: 0.000004

## Pipeline proof
PDF (2024 EN FS) -> Parser (IS/BS/CF/Note16/Note13) -> data_mart_v2.db

## Status: PASS
