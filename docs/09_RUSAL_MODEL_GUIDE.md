# Rusal Model Guide

**Updated:** August 2026 | **Version:** 2.2.0 | **Status:** Production ready, BS=0.000000

## Company Profile

- **Industry:** Aluminium, IFRS, reporting in USD
- **Data source:** PDF parser (EN Financial Statements 2011-2025)
- **Model mode:** Custom, segment revenue modeling
- **Debt mode:** Optimizer (instrument-level corkscrew, 70 instruments loaded)

## Revenue: 3 Segments

| Segment | Volume method | Price method | Price driver |
|---------|--------------|-------------|-------------|
| Primary Al | EWA (halflife=4) | macro | lme_aluminium |
| Alumina | EWA (halflife=4) | macro | lme_alumina |
| Other | EWA (halflife=3) | EWA | — |

## COGS: Component-based

| Component | Share | Driver |
|-----------|------:|--------|
| Alumina cost | 37% | LME alumina |
| Energy | 27% | Russian power price |
| Labour | 12% | CPI RU |
| Other | 24% | PPI RU |

Mean reversion dampening: 0.30, clamp ±0.06 (1σ).
Alumina intensity: 1.93 t/t Al, energy: 15,500 kWh/t Al.

## Macro Drivers (8 factors)

`lme_aluminium`, `lme_alumina`, `usd_rub`, `brent`, `gdp_world`, `cpi_ru`, `ppi_ru`, `russian_power_price`

All have history (2011-2025) and forecasts in DB.
VECM/MR/EWA methods applied via macro runner.

## Debt: 69 instruments in DB (70 loaded, 23 active 2026)

- 9 floating rate: CBR KeyRate + spread (1.2-3.0%)
- CBR forecast in project.yaml: 2026=14%, 2027=11%, 2028=9%, 2029=8%, 2030=7%
- Fixed rate: CNY bonds (4.75-8.5%), RUB bonds (10.9-12%)
- Interest: 818M (2026) → 718M (2030), declining with CBR

## Stress Scenarios (8)

| Scenario | Key shocks |
|----------|-----------|
| lme_mild | LME Al -15% |
| aluminium_downturn | LME -25%, alumina -15%, WC stress |
| sanctions_shock | RUB +30%, power +20%, WC stress |
| energy_spike | Power +40%, Brent +30% |
| rate_spike | Rate +200bp |
| severe | LME -30%, RUB +25%, rate +400bp, WC stress |
| upside | LME +20%, alumina +15% |
| covenant_breach | LME -20%, power +30%, rate +200bp (auto-trigger) |

## Covenants

| Covenant | Threshold | 2026 value | Status |
|----------|----------:|-----------:|--------|
| ND/EBITDA | ≤4.5 | 4.49 | warning |
| ICR | ≥2.0 | 0.96 | breach |
| D/E | ≤4.0 | 0.74 | ok |
| Current Ratio | ≥1.0 | 2.16 | ok |
| EBITDA Margin | ≥5% | 10.7% | ok |

## Rating: S&P Methodology

- Industry adjustment: -6.0 (less cyclical than steel)
- Size adjustment: +2.0
- Cycle avg EBITDA margin: 12%
- Result: B (score 28.9-33.4), speculative grade

## Feature Flags

```yaml
features:
  min_cash: 500000000
  use_ppe_corkscrew: true
  use_wc_days: true
  use_tax_corkscrew: true
  use_intangibles_corkscrew: true
  use_interest_payable_cork: true
  use_debt_rc: false
```

## Corkscrews in DB

| Corkscrew | Table | Rows | Closing=BS |
|-----------|-------|-----:|:----------:|
| PPE | ppe_components | 273 | verified |
| Debt | debt_instruments + debt_schedule | 666 | verified |
| Intangibles | intangible_assets | 24 | verified |
| Tax DTA/DTL | tax_schedule | 6 | verified |
| Provisions | provisions_schedule | 20 | verified |
| Associates | associates_schedule | 54 | verified |
| Lease | lease_schedule | 4 | verified |
| Equity | equity_schedule | 15 | verified |

## Data Loading Pipeline

```
01_Data_Loading.ipynb
  ├── ExcelLoader.load()              → IS/BS/CF, PPE, Debt, Segments, Macro
  └── load_schedule_sheets.py         → Intangibles, Tax, Provisions, Associates, Operational
Total: ~2,500 rows → data_mart_v2.db
```

## Excel File: rusal_complete_v5.xlsx

21 sheets. v5 updates: 2025 FS data, intangibles convention (excl. goodwill),
PPE convention (excl. RoU), interest_payable from Note 19, lease_liab from notes.

### BS Data Conventions (IFRS)
- `ppe_net` = owned PPE only (EXCLUDES RoU asset) — `bs_totals.py` sums `ppe_net + rou_asset`
- `intangibles` = other intangibles only (EXCLUDES goodwill) — `bs_totals.py` sums `intangibles + goodwill`
- `short_term_debt` = loans CL − interest_payable (stored separately)
- `accounts_payable` = pure trade payables (EXCLUDES lease_liab_current, stored separately)
- `ppe_gross`/`ppe_accum_dep` = auto-reconciled in model loader if inconsistent with `ppe_net` (IFRS includes RoU in gross/accum_dep)

### BS Validation Pipeline
```
ExcelLoader._validate_bs_balance()     → CA/NCA/CL/NCL/TA sums vs reported totals
ModelInputLoader._build_base_year()    → bottom-up BS from components (no plugs)
ThreeStatementModel._solve_bs_totals() → forecast BS from components
YearState.full_validation()            → BS identity + CF bridge + cash consistency
```

## Model Output (v2.2.0, base year 2025)

| Year | Revenue | EBITDA | Net Income | BS diff |
|------|--------:|-------:|-----------:|--------:|
| 2026 | 13,378M | 1,464M | 833M | 0.00M |
| 2027 | 13,912M | 1,302M | 773M | 0.00M |
| 2028 | 14,348M | 1,207M | 689M | 0.00M |
| 2029 | 14,520M | 1,096M | 551M | 0.00M |
| 2030 | 14,651M | 994M | 318M | 0.00M |
