# Phase 4d-debt Report

## Changes
- `tools/enrich_db_from_parser.py`: +`enrich_debt_instruments()` function
- `data_mart_v2.db`: 28 new rows in debt_instruments, 10 new columns

## DB state after enrich

| schedule_year | instruments | total (mUSD) |
|---------------|-------------|-------------|
| 2024 | 17 | **4,241** (exact match) |
| 2023 | 11 | 4,383 |
| NULL (xlsx) | 69 | N/A (existing) |
| **Total** | **97** | |

## Schema changes (ALTER TABLE)
Added 10 nullable columns: `schedule_year`, `instrument_class`, `rate_description`, `total`, `yr1`-`yr5`, `yr6_plus`

## Key decisions
- `instrument_id` = `pdf_{class}_{description}_{year}` (avoids collision with xlsx IDs)
- `instrument_name` = rate_description (from PDF)
- `currency` derived from description (RUB/CNY/EUR/USD/KZT)
- Existing 69 xlsx rows untouched

## Prod sanity
- us_steel BS: 0.000004
- rusal BS: 0.000008 (floating-point, acceptable)

## Status: PASS
