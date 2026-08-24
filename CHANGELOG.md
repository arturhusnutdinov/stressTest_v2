# Changelog

## [2.2.0] — 2026-08-24

### Added
- **BS validation in ExcelLoader**: `_validate_bs_balance()` checks CA/NCA/CL/NCL component sums vs reported totals; reports specific gaps in mUSD instead of silently plugging
- **`_KNOWN_BS_METRICS` set**: 60+ canonical + alias names for unknown-metric detection during Excel loading
- **PPE gross/accum_dep reconciliation**: auto-adjusts `ppe_gross` when IFRS includes RoU in gross/accum_dep but `ppe_net` excludes it (prevents PPE corkscrew double-counting RoU asset)
- **Non-WC BS adjustment fields**: `cfo_non_wc_bs_adj` (Δemployee_benefits + Δother_ncl) and `cfi_non_wc_bs_adj` (−Δother_nca − Δrestricted_cash) ensure CF completeness
- **`full_validation()` on YearState**: BS identity, CF bridge, cash BS↔CF consistency checks
- **Lease safety caps**: `rou_op_amort` and `principal_op` capped to prevent negative RoU/liability
- **Rusal Excel v5**: 2025 FS data, intangibles convention fix, interest_payable/restricted_cash added, 2024 other_cl fixed (804→788M)

### Fixed
- **Eliminated plug approach**: model loader no longer computes `other_nca_plug` or `other_ncl_plug` — uses explicit DB values and warns on imbalance
- **PPE corkscrew 49M drift**: `ppe_gross(19,620) − ppe_accum_dep(12,589) = 7,031M` included RoU(49M) but `ppe_net = 6,982M` excluded it; reconciliation ensures consistency
- **BS sign conventions**: all liability BS items use `abs()` in model loader for consistent sign convention
- **`taxes_payable` sign**: preserved as-is from DB (can be negative = tax receivable); CF delta handles sign transition correctly
- **`other_ca` merge**: `other_ca + other_ca_tax` merged in model loader (was: only first value)

### Changed
- **Model loader BS logic**: bottom-up component sums for all subtotals (CA/NCA/CL/NCL/TE), no anchor-based residuals
- **CF WC deltas**: removed `abs()` wrappers — all BS items now stored as positive magnitudes by convention
- **excel_loader.yaml**: updated to v5 source, added IFRS convention comments (intangibles excl. goodwill, ppe_net excl. RoU, interest_payable from Note 19, lease_liab from notes)
- **CF totals**: `cfo_total` and `cfi_total` now include non-WC BS adjustments for complete BS↔CF linkage

### Model Output (Rusal, verified)
- Base year 2025: BS diff = 0.000000
- Forecast 2026-2030: BS diff = 0.000000, CF diff = 0.000000
- Revenue: 13,378M (2026) → 14,651M (2030)
- Net Income: 832M (2026) → 318M (2030)

## [2.1.1] — 2026-05-18

### Added
- **RUSAL stress scenarios**: expanded from 5 to 8 (lme_mild, sanctions_shock, severe, upside)
- **RUSAL feature flags**: explicit corkscrew flags in project.yaml (use_ppe_corkscrew, use_wc_days, use_tax_corkscrew, use_intangibles_corkscrew, use_interest_payable_cork)
- **Textbook chapters**: 5.1b Preprocessor, 7.3.4 Stress & Rating (6 subsections), 7.3.6b Covenants, 7.7 YAML Configuration Guide (10 subsections)
- **Textbook PDF**: 54 pages, 280 KB (docs/financial_modeling_textbook_rewritten.pdf)
- **HANDOFF_FINAL.md**: comprehensive handoff document with all current metrics

### Fixed
- **TaxBlock IAS 12 compliance**: IS Total Tax = Current + Deferred (was: current only, deferred ×0)
- **TaxBlock NOL→DTA**: EBT < 0 now creates DTA = new_nol × rate (IAS 12 tax benefit)
- **TaxBlock accel dep**: taxable_income = EBT − NOL − dep_adj (was: EBT − NOL only)
- **TaxBlock payment_lag**: from config `tax_paid_timing` (was: hardcoded next_year)
- **TaxBlock nol_enabled**: activates on EBT < 0 (was: only when nol_open > 0)
- **Covenants**: metals industry override now respects YAML threshold overrides (was ignoring them)
- **RUSAL covenants**: ND/EBITDA threshold correctly 4.5x (was defaulting to steel 3.5x)

### Changed
- **TaxBlock**: rewritten to follow CFI / IAS 12 / ASC 740 methodology
- **ModelConfig**: added `tax_paid_timing` field (current_year | next_year)
- **finmodelling_guide.html**: full rewrite — 12 sections, Russian, narrative blocks, actual results
- **Textbook**: 2,461 → 3,192 lines (+731 lines of new content)
- **Project tree**: updated in docs to reflect blocks/ decomposition and new files
- **Documentation**: all docs updated with current model output numbers

### Model Output (verified)
- US Steel: BS=0.000004, Rating BBB→A-, 0 covenant breaches, 1 stress scenario
- RUSAL: BS=0.000004, Rating B, 9 covenant breaches, 8 stress scenarios (all OK)

## [2.1.0] — 2026-05-16

### Added
- **Test suite**: 45 tests (unit + integration) for both US Steel and RUSAL
- **CI/CD**: GitHub Actions workflow (pytest + ruff on Python 3.11/3.12)
- **engine/constants.py**: 50+ named constants replacing magic numbers
- **engine/model/blocks/**: 6 extracted blocks (revenue, sga, is_subtotals, bs_other, cash, bs_totals)
- **pyproject.toml**: pip install -e . support, CLI entry point (`stresstest`)
- **audit_rusal_data.py**: read-only data quality audit tool
- **RUSAL data fixes**: 6 migrations for metric names, debt types, currency, schedules

### Changed
- **core.py**: 2044 → 1696 lines (revenue, sga, is_subtotals, bs_other, cash, bs_totals delegated to blocks)
- **ModelConfig**: +revenue_macro_factor, +cogs_revenue_factor, +cogs_cost_factor fields
- **blocks/is_subtotals**: uses config.da_in_cogs instead of re-reading YAML
- **blocks/revenue**: uses config.revenue_macro_factor instead of re-reading YAML
- **RUSAL Excel BS**: computed metrics removed, canonical metrics added

### Removed
- **Dead code**: `_joint_solve()` method (replaced by inline loop in `_solve_year`)
- **YAML reads from blocks**: revenue and is_subtotals no longer read project.yaml directly

### Fixed
- RUSAL: 71 debt instruments now have correct db_type (bond_fixed/bond_float/term_bullet)
- RUSAL: debt balances converted from RUB/CNY to USD ($7.918B total)
- RUSAL: lease_schedule and equity_schedule populated from parsed data
- RUSAL: 143 missing canonical metrics added to DB
- RUSAL: computed metrics removed from raw history tables

## [2.0.0] — 2026-03-31
- Initial release of stressTest Engine v2
- Three-statement model solver with joint iteration
- 10 forecast methods (MACRO, DRIVER, DAYS, CORK, EWA, LAST, ZERO, CALC, PLUG, LINK)
- 14 preprocessor metric groups
- VECM/ARIMA/ECM macro forecasting
- Stress testing, credit rating (S&P/Moody's/Fitch), covenant monitoring
- SQLite database (41 tables, WAL mode)
- US Steel (US GAAP) and UC RUSAL (IFRS) models
