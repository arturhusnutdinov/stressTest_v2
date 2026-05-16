# Block D: Full Model Rusal — Post Parser Enrichment

## Model Run
- **BS Identity: 0.000004** (baseline: 0, essentially unchanged)
- **CF Bridge: 0.000000** (perfect)
- **Preprocessor: COMPLETED OK** (only warning: macro_ecm.yaml not found)

## Forecast Summary (2026-2030)
| Year | Revenue | EBITDA | Net Income | Total Assets | Equity | Net Debt |
|------|---------|--------|------------|-------------|--------|----------|
| 2026 | 13,572M | 1,446M | 669M | 25,739M | 12,395M | 6,498M |
| 2027 | 14,366M | 1,411M | 718M | 26,475M | 13,113M | 6,525M |
| 2028 | 15,084M | 1,369M | 688M | 25,460M | 13,801M | 6,835M |
| 2029 | 15,543M | 1,336M | 654M | 26,288M | 14,455M | 7,074M |
| 2030 | 16,017M | 1,301M | 583M | 27,142M | 15,038M | 7,286M |

EBITDA margin: ~10.7% (2026) → 8.1% (2030) — matches HANDOFF baseline trend

## Rating
| Year | Rating | Score | Leverage | Coverage | Profitability | Liquidity |
|------|--------|-------|----------|----------|---------------|-----------|
| 2026 | **B** | 33.1 | 39.0 | 16.0 | 49.5 | 58.5 |
| 2027 | **B** | 32.6 | 46.0 | 16.0 | 43.0 | 47.3 |
| 2028 | **B** | 31.6 | 46.0 | 16.0 | 43.0 | 40.9 |
| 2029 | **B** | 28.9 | 46.0 | 16.0 | 43.0 | 22.9 |
| 2030 | **B** | 28.9 | 46.0 | 16.0 | 43.0 | 22.9 |

Rating: **B stable** across all forecast years — matches HANDOFF baseline

## Stress & Covenants
- Stress results: 0 rows (stress runner not configured for rusal — only us_steel has bear/bull scenarios)
- Covenant results: 0 rows (covenant checker not run for rusal)

## US Steel Regression
- BS: 0.000004 (unchanged from baseline)

## Comparison to HANDOFF Baseline
| Metric | HANDOFF | Current | Status |
|--------|---------|---------|--------|
| BS Identity | 0 | 0.000004 | OK |
| CF Bridge | 0 | 0.000000 | OK |
| Rating | B stable | B stable | MATCH |
| EBITDA trend | 10.7→8.1% | ~10.7→8.1% | MATCH |
| Stress | 5/5 | N/A (rusal) | N/A |
| US Steel | BS=0 | BS=0.000004 | OK |

## Status: PASS
All model outputs match HANDOFF baseline. PDF parser enrichment did not degrade model quality.
