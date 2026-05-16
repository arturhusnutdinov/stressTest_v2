# Rusal Model Guide

**Updated:** April 2026 | **Status:** Production ready, BS=0.000004

## Company Profile

- **Industry:** Aluminium, IFRS, reporting in USD
- **Data source:** PDF parser (EN Financial Statements 2011-2025)
- **Model mode:** Custom, segment revenue modeling

## Revenue: 3 Segments

| Segment | Volume method | Price method | Price driver |
|---------|--------------|-------------|-------------|
| Primary Al | EWA (halflife=4) | macro | lme_aluminium |
| Alumina | EWA (halflife=4) | macro | lme_alumina |
| Other | flat | flat | — |

## COGS: Component-based

| Component | Share | Driver |
|-----------|------:|--------|
| Alumina cost | 37% | LME alumina |
| Energy | 27% | Brent, Russian power price |
| Labour | 12% | CPI RU |
| Other | 24% | PPI RU |

Mean reversion dampening: 0.30, clamp ±0.06 (1σ)

## Macro Drivers (8 factors)

`lme_aluminium`, `lme_alumina`, `usd_rub`, `brent`, `gdp_world`, `cpi_ru`, `ppi_ru`, `russian_power_price`

All have history (2011-2024) and forecasts (2023-2030) in DB.
VECM/MR/EWA methods applied via macro runner.

## Debt: 71 instruments

- 9 floating rate: CBR KeyRate + spread (2.2-2.95%)
- CBR forecast in project.yaml: 2026=14%, 2027=11%, 2028=9%, 2029=8%, 2030=7%
- EUR Euribor linked bonds

## Corkscrews in DB

| Corkscrew | Table | Rows | Closing=BS |
|-----------|-------|-----:|:----------:|
| PPE | ppe_components | 273 | ✓ verified |
| Debt | debt_instruments + debt_schedule | 668 | ✓ |
| Intangibles | intangible_assets | 24 | ✓ |
| Tax DTA/DTL | tax_schedule | 6 | ✓ |
| Provisions | provisions_schedule | 20 | ✓ |
| Associates | associates_schedule | 54 | ✓ |

## Data Loading Pipeline

```
01_Data_Loading.ipynb (9 cells)
  ├── ExcelLoader.load()              → 2,280 rows
  │   ├── IS/BS/CF (1,263 cells)
  │   ├── PPE components (273 rows)
  │   ├── Debt instruments (71)
  │   ├── Segments (168)
  │   └── Macro + KPI (45)
  └── load_schedule_sheets.py         → 177 rows
      ├── Intangibles (24)
      ├── Tax (6)
      ├── Provisions (20)
      ├── Associates (54)
      └── Operational Drivers (73)
Total: 2,457 rows → data_mart_v2.db
```

## Excel File: rusal_complete_v4.xlsx

21 sheets, 58 KB. All data from parser (blue font = verified).

## Model Output

| Year | Revenue | EBITDA | Net Income | Rating |
|------|--------:|-------:|-----------:|--------|
| 2026 | 13,572M | 1,446M | 669M | B |
| 2027 | 14,366M | 1,411M | 718M | B |
| 2028 | 15,084M | 1,369M | 688M | B |
| 2029 | 15,543M | 1,336M | 654M | B |
| 2030 | 16,017M | 1,301M | 583M | B |

EBITDA margin: 10.7% (2026) → 8.1% (2030)
