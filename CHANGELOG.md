# Changelog

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
