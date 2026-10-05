# Corporate Financial Model v4 — Excel-Driven Design

## Принцип
Вся модель живёт в Excel. Python (`build_corporate_model.py`) только **генерирует** файл с формулами.
Аналог: bank_model/scripts/build_all.py → model.xlsx (26 листов, ~5000 формул).

## Целевые компании
- **UC RUSAL** (metals/aluminium, USD, 3 сегмента: primary_al, alumina, other)
- **Nornickel** (metals/nickel, USD, 5 сегментов: nickel, copper, palladium, platinum, other)

## Листы (30 шт.)

### Навигация
| # | Sheet | Rows | Purpose |
|---|-------|------|---------|
| 00 | 00_Guide | 30 | 18-step navigation wizard |
| 00 | 00_Cover | 50 | Company info, scenario selector, analyst |

### Ввод
| # | Sheet | Rows | Purpose |
|---|-------|------|---------|
| CP | Control_Panel | 300 | 130+ parameters (A-L sections) |
| 01 | 01_Macro | 60 | 3-4 macro scenarios + econometrics display |
| 02 | 02_Hist | 120 | Historical IS/BS/CF (5-10 years) |
| 03 | 03_Assump | 200 | Expanded assumptions (← Control_Panel) |
| RI | Raw_IFRS | 250 | Raw МСФО data (167+ keys) |

### Операционные драйверы
| # | Sheet | Rows | Purpose |
|---|-------|------|---------|
| 10 | 10_Revenue | 60 | Σ(Volume × Price) by segment + macro regression |
| 11 | 11_Segments | 80 | Production, sales, prices, costs, utilization |
| 12 | 12_COGS | 50 | Component model: materials/energy/labour/transport |
| 13 | 13_SGA | 30 | SGA ratio + admin/distribution/marketing split |
| 14 | 14_OtherIS | 25 | Other income/expenses, associates |

### Corkscrews (расписания)
| # | Sheet | Rows | Purpose |
|---|-------|------|---------|
| 15 | 15_PPE | 40 | Gross → CapEx → Disp → Dep → Net |
| 16 | 16_WC | 40 | DSO/DIO/DPO → AR/INV/AP |
| 17 | 17_Debt | 70 | Instrument-level: mandatory→refi→draw→surplus |
| 18 | 18_Lease | 25 | IFRS 16: ROU → dep, liab → interest+payment |
| 19 | 19_Tax | 45 | IAS 12: current/deferred, DTA/DTL, NOL |

### Financial Statements (прогноз)
| # | Sheet | Rows | Purpose |
|---|-------|------|---------|
| 20 | 20_BS | 45 | Balance = Assets − Liabilities − Equity = 0 |
| 21 | 21_PL | 35 | Revenue → EBITDA → EBIT → EBT → Tax → NI |
| 23 | 23_CF | 35 | CFO + CFI + CFF = ΔCash (indirect) |
| 24 | 24_Equity | 30 | RE corkscrew: NI → Div → Buyback → RE_close |

### Аналитика
| # | Sheet | Rows | Purpose |
|---|-------|------|---------|
| 30 | 30_Ratios | 40 | 25+ KPIs (leverage, coverage, margins, WC) |
| 31 | 31_Score | 40 | S&P 4-factor rating scorecard |
| 32 | 32_Covenants | 30 | Thresholds, actuals, headroom, breach |
| 33 | 33_RevStress | 45 | Reverse stress + tornado analysis |
| 35 | 35_Valuation | 90 | DCF + SOTP + Sensitivity matrix |
| 40 | 40_Scen | 35 | Scenario comparison table |

### Контроль
| # | Sheet | Rows | Purpose |
|---|-------|------|---------|
| 90 | 90_Checks | 80 | BS Identity, CF Bridge, rollforwards, calibration |
| MO | Model_Output | 200 | 12-section summary dashboard |
| CL | Changelog | 15 | Version history |

## Столбцы (единый формат)
```
A = Label (42 chars)
B = Unit (7 chars)
C = Hist Year 1 (e.g. 2020)
D = Hist Year 2 (2021)
...
F = Hist Year N (2025)
G = Forecast Year 1 (2026E)
H = Forecast Year 2 (2027E)
I = Forecast Year 3 (2028E)
...
L = Notes/Source (42 chars)
```

## Цветовая схема (из bank model)
```
SL = '3F5A73'  # Slate — headers
GR = '33383D'  # Gray — labels
INPUT = 'FFF2A8'  # Yellow — user input
RESULT = 'E8F5E9'  # Green — formula result
REF_FONT = '008000'  # Green font — cross-sheet reference
INPUT_FONT = '0000FF'  # Blue font — editable value
SECTION_BG = '3F5A73'  # Section header background (white font)
```

## Circular Solver (Excel Iterative Calc)
```
Loop: RC draw → interest → EBT → tax → NI → RE → equity → BS → cash → RC draw
Solver: seed → MEDIAN(0, x + relax*(F−x), 3*limit)
Convergence: ~3-4 iterations, contraction 0.09
Settings: Enable Iterative Calc, Max 1000 iter, 0.001% delta
```

## Control_Panel Sections

### A. Макросценарий
- Активный сценарий (1-N dropdown)
- Commodity prices: LME Al/Ni/Cu/Pd/Pt, Brent
- FX: USD/RUB, EUR/USD
- Macro: GDP_world, GDP_RU, CPI_RU, PPI_RU
- Econometric: β_revenue, R², factor drivers

### B. Операционные показатели
- Volumes by segment (kt)
- Capacity, utilization
- Unit costs ($/t)

### C. Выручка
- Method selector (segment/macro_ols/ewa)
- Segment configs (volume_method, price_method)
- Elasticity coefficients

### D. Себестоимость
- COGS method (ratio/component/ppi)
- Component shares (material/energy/labour/transport)
- PPI beta, mean reversion

### E. SGA / OpEx
- SGA ratio, halflife
- Distribution/admin/marketing split

### F. CapEx / PPE
- Sustaining DA ratio, expansion %
- Useful life, disposal %

### G. Working Capital
- DSO/DIO/DPO days
- NWC floor

### H. Долг
- Target ND/EBITDA
- RC capacity, min cash
- Refinancing fees

### I. Налоги
- Statutory rate, effective rate
- DTA/DTL opening, NOL

### J. Дивиденды / Капитал
- Payout ratio, buyback %
- Leverage constraint

### K. Оценка (DCF)
- WACC components (Rf, β, ERP, CRP)
- Terminal growth, multiple

### L. Скоркарта
- S&P 4-factor weights and thresholds
- Industry/size adjustments
