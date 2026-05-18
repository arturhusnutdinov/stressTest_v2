# Rusal Model Guide

**Updated:** May 2026 | **Version:** 2.1.0 | **Status:** Production ready, BS=0.000004

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

## Excel File: rusal_complete_v4.xlsx

21 sheets, 58 KB. All data from parser (blue font = verified).

## Model Output

| Year | Revenue | EBITDA | Margin | Net Income | ND/EBITDA | ICR | Rating |
|------|--------:|-------:|-------:|-----------:|----------:|----:|--------|
| 2026 | 13,572M | 1,446M | 10.7% | 775M | 4.5x | 1.8x | B |
| 2027 | 14,366M | 1,413M | 9.8% | 714M | 4.5x | 1.7x | B+ |
| 2028 | 15,084M | 1,373M | 9.1% | 670M | 4.9x | 1.8x | B |
| 2029 | 15,543M | 1,345M | 8.7% | 639M | 5.1x | 1.9x | B |
| 2030 | 16,017M | 1,302M | 8.1% | 567M | 5.5x | 1.8x | B |
