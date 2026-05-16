# Phase 4e: Multi-year 2023 EN FS Enrich Report

## Changes
- `tools/enrich_db_from_parser.py`: added `--pdf` argument, multi-year loop for all parsed years
- `data_mart_v2.db`: enriched from 2023 EN FS

## Discovery results (2023 PDF)
| Section | Status | Notes |
|---------|--------|-------|
| IS | PASS (page 9, 16 metrics) | years [2022, 2023] |
| BS | YEAR BUG | "14 March 2024" in footer contaminates year detection |
| CF | PASS (page 13, 25 metrics) | years [2022, 2023] |
| Note 16 Inventory | PASS | years [2022, 2023] |
| Note 13 PPE | PASS (page 36) | years [2022, 2023] |
| Note 14 Intangibles | PASS (page 41) | years [2022, 2023] |
| Note 15 Associates | EMPTY | wide-table layout differs in 2023 |
| Note 19 Debt | PASS (pages 55-56) | 12 for 2023, 11 for 2022 |
| Note 20 Provisions | PASS (page 57) | years [2022, 2023] |
| Note 8 Tax | STRUCTURE BUG | default_year=2024 hardcoded |

## Enrich summary
| Metric | Count |
|--------|------:|
| IS/BS/CF/Inv matched | 98 |
| IS/BS/CF/Inv inserted | 13 |
| BS mismatches (year bug) | 30 |
| PPE components 2022 | 77 |
| Debt instruments 2022 | 11 |

## DB coverage after enrich
| Data | 2022 | 2023 | 2024 |
|------|:----:|:----:|:----:|
| Inventory breakdown | 3 rows | 3 rows | 3 rows |
| PPE components | 77 rows | 98 rows | 98 rows |
| Debt instruments | 11 | 12 | 17 |

## Known issues
1. **BS year detection**: 2023 PDF BS page has "14 March 2024" in approval footer, causing year 2024 to be detected. BS values for 2023 PDF get mapped to wrong year. **Impact**: 30 mismatches reported, no incorrect data inserted (existing values not overwritten)
2. **Note 15 Associates**: wide-table layout may differ in 2023 FS (different column header format)
3. **Note 8 Tax**: `default_year: 2024` hardcoded in yaml doesn't work for 2023 PDF

## Prod sanity
- us_steel BS: 0.000004
- rusal BS: 0.000004

## Status: PASS (with known limitations on BS/Note8/Note15)
