# Changelog

## [2.1.1] — 2026-05-18

### Added
- **RUSAL stress scenarios**: expanded from 5 to 8 (lme_mild, sanctions_shock, severe, upside)
- **RUSAL feature flags**: explicit corkscrew flags in project.yaml (use_ppe_corkscrew, use_wc_days, use_tax_corkscrew, use_intangibles_corkscrew, use_interest_payable_cork)
- **Textbook chapters**: 5.1b Preprocessor, 7.3.4 Stress & Rating (6 subsections), 7.3.6b Covenants, 7.7 YAML Configuration Guide (10 subsections)
- **Textbook PDF**: 54 pages, 280 KB (docs/financial_modeling_textbook_rewritten.pdf)
- **HANDOFF_FINAL.md**: comprehensive handoff document with all current metrics

### Fixed
- **Covenants**: metals industry override now respects YAML threshold overrides (was ignoring them)
- **RUSAL covenants**: ND/EBITDA threshold correctly 4.5x (was defaulting to steel 3.5x)

### Changed
- **Textbook**: 2,461 → 3,162 lines (+701 lines of new content)
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
