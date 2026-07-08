# CLAUDE.md — stressTest_v2

## Стиль работы
- Отвечать кратко, на русском, без лишних объяснений
- Результат сразу: таблицы и код вместо описаний
- Artur — опытный разработчик (Python, IFRS/US GAAP, кредитный анализ)

## Git
- Коммиты и пуш — **только по явному запросу**
- Remote: `git@github.com:arturhusnutdinov/stressTest_v2.git`, ветка `main`
- Не использовать `--no-verify`, не амендить публичные коммиты

## База данных
- **Единственная БД:** `data_mart_v2.db` (39 таблиц, SQLite WAL)
- **INSERT OR REPLACE** — upsert семантика для идемпотентности
- **YAML конфиги:** только policy/parameters, не числа модели (числа через preprocessor)
- **После любых изменений:** `python3 -m pytest tests/ -v` → 45/45, BS diff ≈ 0

## Запуск моделей
```python
build_model('rusal', run_preprocessor=False, run_model=True,
            run_stress=True, run_rating=True, run_covenants=True)
```
Показывать: BS diff, stress (все сценарии), rating по годам, covenant breaches,
forecast таблица (Rev/EBITDA/Margin/NI/ND-EBITDA/ICR/Rating), debt schedule.

## Архитектура (v2.3)

### Pipeline
```
External ECM (modelMacro, 19 factors) →
Preprocessor (14 groups + production_kpi) →
Macro (VECM/MR/EWA + sanity validation + gap-fill fallback) →
ThreeStatementModel (8+1 corkscrews, calibrated) →
Stress (segment rebuild, full 3-statement, 110 metrics/scenario) →
Rating (S&P + national RU scale via sovereign BBB+ mapping) →
Covenants (via Repository)
```

### Структура engine/
```
engine/
├── orchestrator.py              # Точка входа build_model()
├── constants.py                 # 90+ именованных констант (calibrated from Rusal OLS 2011-2025)
├── database/
│   ├── schema.py                # DDL 39 таблиц + миграции
│   └── repository.py            # 46 методов CRUD
├── loader/
│   ├── base.py                  # FormulaEngine, MappingConfig, unit conversion
│   └── excel.py                 # ExcelLoader: xlsx → DB (IS/BS/CF + canonical)
├── preprocessor/core.py         # 14 групп метрик (margins, WC days, capex, debt...)
├── model/
│   ├── core.py                  # ThreeStatementModel (solver, 10 итераций, $1K tol)
│   ├── loader.py                # ModelInputLoader: DB → HistoricState + ModelConfig
│   ├── inputs.py                # YearState (120+ полей), ModelConfig (50+ полей)
│   ├── saver.py                 # IS(32)/BS(45)/CF(33) metrics → forecast_*
│   ├── blocks/                  # revenue, sga (split), cash, bs_totals, is_subtotals, bs_other (provisions)
│   ├── schedules/               # debt, ppe, tax (IAS 12), lease, equity, wc, intangibles, provisions
│   ├── cogs_block.py            # Component COGS (configurable factors per company)
│   ├── segment_revenue.py       # Volume × Price per segment
│   ├── forecast_dispatcher.py   # 10 methods: EWA/MACRO/DRIVER/CORK/CALC/LINK...
│   └── revenue_models.py        # OLS, EWA with percentile clamp
├── macro/
│   ├── runner.py                # Entry point → MacroDBAdapter → vecm_bridge
│   ├── db_adapter.py            # MacroDBAdapter — единственный DB интерфейс macro
│   ├── vecm_bridge.py           # VECM groups + MR commodity + EWA fallback
│   ├── vecm.py                  # VECM solver (Johansen, 1,600+ строк)
│   ├── commodity_models.py      # Mean reversion, RW drift
│   └── preprocess.py            # Anomaly detection, cycle detection
├── stress/                      # Macro + driver shocks, multi-scenario
├── rating/                      # S&P/Moody's/Fitch scoring engine
└── covenants/                   # ND/EBITDA, ICR, leverage monitoring
```

### Загрузка данных
```
Excel → DB:
  tools/load_unified_excel.py    # Единый загрузчик: все 31 лист → DB
  tools/load_schedule_sheets.py  # Schedule-листы (18 handlers)
  engine/loader/excel.py         # ExcelLoader (IS/BS/CF + canonical)

DB → Excel:
  tools/export_to_excel.py       # Полный экспорт DB → 31-sheet Excel

Инициализация:
  tools/init_company.py          # Scaffold: 31-sheet Excel + configs + notebooks
```

### Schedule corkscrews
```
PPE:          gross_open + capex - dep - disposals = gross_close
WC:           DSO/DIH/DPO days → AR/Inv/AP (cyclical elasticity)
Debt:         per-instrument schedule / optimizer / parametric
Lease:        ROU + liability (IFRS 16 / US GAAP ASC 842)
Tax:          Current + Deferred (IAS 12), NOL→DTA, DT categories
Equity:       RE = open + NI - dividends - buybacks
Intangibles:  open + additions - amortization = close
Provisions:   open + charge - utilization + accretion = close (3 categories)
```

## Компании

### US Steel
- US GAAP, 2010-2024 → 2025-2029
- 38 debt instruments, `tax_paid_timing: next_year`
- Rating BBB→A-, ND/EBITDA ≤ 3.5x
- TaxBlock: NOL $1B + accel_dep — проверять BS после изменений

### Rusal
- IFRS, 2011-2025 → 2026-2030
- 31 debt instruments (9 CBR floaters, 1 EUR Euribor), base_rate_factor populated
- Revenue: segment_modeling (primary_al capacity=4100kt + alumina + other)
  - Volume: production_kt based, capacity cap, demand linkage GDP×0.8
  - Price: OLS chain-link from realized $2,652/t (VECM growth rate)
  - Alumina: EWA (OLS broken β=-0.72)
- COGS: component-based (commodity_factor=none — vertically integrated)
  - dampening=0.80 (OLS calibrated R²=0.76), clamp=0.09 (1.5σ)
- CapEx: sustaining 110% D&A + growth 5% rev_growth
- Tax: tax_rate_statutory=0.25 (Russian 2025+)
- Interest: payment_timing=current_year
- 9 стресс-сценариев (включая demand_shock)
- Covenants: ND/EBITDA ≤ 4.5, ICR ≥ 2.0
- Rating: B+→B- intl / BBB+(RU)→BBB(RU) national
- External ECM: enabled (19 факторов из modelMacro)
- Features: use_ppe/wc_days/tax/intangibles/interest_payable/provisions corkscrew (все true)
- **Optional features** (disabled, config ready):
  - `sga_split_enabled: true` → distribution/admin/ECL/other_opex
  - `deferred_tax_categories.enabled: true` → PPE/Inv/AR/AP rates
- PDFs: `/Users/arturhusnutdinov/Documents/IT Development/Docker/rusalFinStates/`
- **Кредитный отчёт:** `UnionMethodology/reports/credit_report_rusal_Q3_2026.html` (9 разделов, 24 SVG, 190KB)

### Nornickel
- IFRS, USD, `is_income_sign=natural`
- Metals/mining: Ni (~35%), Pd (~30%), Cu (~20%), Pt (~10%)
- MOEX: GMKN
- **Этапы:**
  1. ✅ Init + Data Collection (2026-05-18)
  2. ⬜ Data Loading → DB
  3. ⬜ Revenue Analysis → макро-факторы
  4. ⬜ YAML Config → Model Run → Stress/Rating
- **Дневник:** `companies/nornickel/PROJECT_DIARY.md`
- **Excel:** `companies/nornickel/data/excel/nornickel_unified.xlsx`

## TaxBlock (IAS 12 / ASC 740)
```
IS:  total_tax = current_tax + deferred_tax
     current  = rate × max(0, EBT − NOL_used − accel_dep_excess)
     deferred = −(ΔDTL − ΔDTA)
     NI = EBT + total_tax

BS:  DTA, DTL, taxes_payable (closing balances)

CF:  CFO = NI + D&A + cfo_deferred_tax + ΔWC + Δtaxes_payable + ...
     cfo_deferred_tax = dtl_delta - dta_delta (non-cash reversal)
     Supplemental: tax_paid_cf = current_tax only (no deferred)

DT Categories (optional): PPE, Inventory, AR, AP — each × category rate
NOL: min(nol_open, EBT × 80%) — TCJA cap
Payment: US Steel=next_year, Rusal=current_year
```
Референс: `docs/Financial-Modeling-Guidelines.pdf` (CFI, p.30-31, 37, 41-48)

## Workflow: добавление данных нового года
1. `python3 tools/export_to_excel.py --company rusal` → получить текущий Excel
2. Аналитик добавляет колонку 2026 в IS/BS/CF + обновляет schedule листы
3. `python3 tools/load_unified_excel.py --company rusal` → загрузить только новое
4. `build_model('rusal', run_preprocessor=True, run_model=True, ...)` → пересчитать

## Ключевые файлы
| Путь | Назначение |
|------|-----------|
| `engine/orchestrator.py` | Точка входа `build_model()` |
| `engine/model/core.py` | 3-statement solver |
| `engine/constants.py` | 90+ констант (calibrated from OLS) |
| `engine/database/schema.py` | DDL 39 таблиц |
| `engine/database/repository.py` | 46 CRUD методов |
| `tools/load_unified_excel.py` | Единый загрузчик Excel → DB |
| `tools/export_to_excel.py` | Экспорт DB → Excel (31 лист) |
| `tools/init_company.py` | Инициализация новой компании |
| `templates/excel_loader_template.yaml` | Маппинг 31 лист → DB |
| `templates/scenario_template.yaml` | Шаблон стресс-сценариев |
| `data_mart_v2.db` | Единственная БД |
| `docs/Financial-Modeling-Guidelines.pdf` | CFI benchmark (94 стр.) |
| `companies/nornickel/PROJECT_DIARY.md` | Дневник Норникеля |

## Калибровка моделей (v2.3, July 2026)

Все параметры откалиброваны из исторических данных Rusal 2011-2025:

| Параметр | Значение | Метод | Файл |
|----------|----------|-------|------|
| COGS dampening | 0.80 | OLS Δln(COGS/Rev) ~ β×Δln(PPI), R²=0.76 | project.yaml |
| COGS clamp | 0.09 | 1.5 × σ(COGS/Rev), σ=0.059 | project.yaml |
| MR kappa | 0.12 | OU MLE на LME Al 40yr, φ=0.88, HL=5.6yr | vecm_bridge.py |
| WC DSO elast | 0.87 | OLS Δdays/days ~ β×Δrev/rev, n=14 | constants.py |
| WC DIH elast | 0.36 | OLS, n=14 | constants.py |
| WC DPO elast | 0.64 | OLS, n=12 | constants.py |
| WC other_ca | 7% rev | Rusal median 2021-2025 | constants.py |
| WC other_cl | 4% rev | Rusal median 2021-2025 | constants.py |
| Tax rate | 0.25 | РФ законодательство 2025+ | project.yaml |
| Al capacity | 4100 kt | Nameplate (Bratsk+Kras+Sayan+Novok+Taishet) | project.yaml |
| Volume base | production_kt | Avoids inventory spike (sales 4490 vs prod 3918) | project.yaml |
| CapEx model | sustaining 2.0× DA + growth 5% | Median 2021-2025 (2.17×) | project.yaml + core.py |
| Alumina price | ewa | OLS broken (β=-0.72, R²=0.13) | project.yaml |
| GDP World | IMF +2.8% CAGR | Excluded from VECM/fallback | runner.py |
| Revenue elasticity | 0.8 × GDP | Al demand/GDP consensus | segment_revenue.py |

**AR(1)** — реализовано в preprocessor _summary():
- SGA/Rev: AR(1) improves MAE by 31% vs EWA
- Interest/Rev: +49%
- EBITDA margin: +34%

## Кредитный отчёт

Генератор: `UnionMethodology/generate_credit_report.py`
Отчёт: `UnionMethodology/reports/credit_report_rusal_Q3_2026.html`
Руководство: `UnionMethodology/docs/REPORT_GUIDE.md`

**Структура:** 9 разделов, 24 SVG, 21 таблица, 190KB
**Источники:** stressTest_v2 (DB), impliedPD (PD/spread), stressTest_complete (sector heatmap),
modelMacro (8 CSV + scenarios + sector)

**Ключевые правила:**
- ВСЕ числа динамические — нет hardcoded в аналитических комментариях
- Debt service: ST debt (maturing), не debt_repayments (optimizer refi)
- Covenant: n_breaches / n_covenants_total (не /10)
- CAGR: из forecast[-1] / rev_h (не текстовая константа)
- Sector heatmap: OilGas + Real_Estate обязательно (высокий PD)
- Quarterly labels: "24Q3" (не "2024Q3" — перекрытие)
- GVA→ВДС, PPI→ИЦП (русские аббревиатуры)
- SVG x-axis: skip every other label при >8 точках

**Фичи:** donut, waterfall, heatmap, sparklines, PD→Rating, national scale,
debt service capacity, stress cash gap, capacity utilization, factor analysis,
dynamic verdict, 9 stress scenarios with ratings

## Статус доработок (3 фазы завершены)

| # | Доработка | Статус |
|---|-----------|--------|
| 1 | GDP World fix (VECM→IMF +2.8%) | ✅ Phase 1 |
| 2 | Volume: production_kt + capacity cap 4100kt | ✅ Phase 1 |
| 3 | Demand linkage GDP×0.8 elasticity | ✅ Phase 2 |
| 4 | CapEx: sustaining 110%DA + growth 5% | ✅ Phase 2 |
| 5 | External ECM enabled (19 factors) | ✅ Phase 2 |
| 6 | LME reconciliation (analyzed — chain-link correct) | ✅ Phase 3 |
| 7 | AR(1) in preprocessor _summary() | ✅ Phase 3 |
| 8 | Demand shock scenario (9th) | ✅ Phase 3 |
| 9 | ForecastDispatcher beta from preprocessor | ✅ Phase 3 |
| 10 | Capacity utilization in report | ✅ Phase 3 |

## Будущие доработки

| # | Доработка | Приоритет |
|---|-----------|-----------|
| — | CapEx project-based pipeline (Taishet+) | Средний |
| — | Capacity expansion trigger (if demand > capacity) | Низкий |
| — | Preprocessor: per-company WC constants pipeline | Низкий |
| — | Tolling revenue model (demand > capacity) | Низкий |
| — | Volume shock in stress (direct production cut) | Низкий |
