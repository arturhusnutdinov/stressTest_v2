# refactoring_v2 — Documentation Index

| Doc | Contents |
|-----|----------|
| [00_PROJECT_OVERVIEW](00_PROJECT_OVERVIEW.md) | Directory structure, architecture, pipeline, design principles |
| [01_MODELING_SCHEMA](01_MODELING_SCHEMA.md) | YearState fields, ForecastMethod enum, `_solve_year` solver, block-by-block logic |
| [02_DATABASE_SCHEMA](02_DATABASE_SCHEMA.md) | All DB tables, EAV structure, indexes, repository API |
| [03_YAML_CONFIGURATION](03_YAML_CONFIGURATION.md) | Every YAML section, solver params, preprocessor fallback chain |
| [04_DATA_LOADING](04_DATA_LOADING.md) | History loaders, preprocessor, ModelLoader, min_cash computation |
| [05_MACRO_MODULE](05_MACRO_MODULE.md) | VECM pipeline, commodity models, EWA, gap-fill, circular import fix |
| [06_STRESS_RATING_COVENANTS](06_STRESS_RATING_COVENANTS.md) | Stress scenarios, S&P rating scorecard, covenant thresholds, covenant breach auto-trigger |
| [07_US_STEEL_EXAMPLE](07_US_STEEL_EXAMPLE.md) | Running the model, preprocessor values, debt structure, solver convergence |

## Key Features (v2)

- **NOL carryforward** (TCJA): indefinite carryforward, 80% taxable income cap, `taxes.nol_opening_balance`
- **ASC 842 leases**: operating lease BS identity (ΔROU = ΔLL), 7 preprocessor lease metrics
- **Covenant breach auto-trigger**: orchestrator auto-runs `covenant_breach` scenario on breach
- **Capital allocation**: leverage-gated buybacks (`buyback_pct_fcf`, `buyback_leverage_max`) + `equity_additional_events`
- **Floating rate instruments**: `rate_type = floating` → stress rate shocks; `callable_flag` → acceleration
- **CapEx floor**: `min_capex_da_ratio` prevents structural underspend; `additional_capex` for project adds
- **Dynamic WC days**: macro-cycle sensitivity auto-extends DSO/DIO in downturns
- **TaxBlock DTL**: accelerated depreciation generates DTL corkscrew
- **Rating steel methodology**: `industry_adjustment: -8.0`, through-the-cycle EBITDA normalization
