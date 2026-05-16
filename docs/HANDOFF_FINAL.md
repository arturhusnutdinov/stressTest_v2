# stressTest v2 — Финальная передача контекста

**Дата: April 2026 | Статус: PRODUCTION READY**

---

## ВСТАВЬ В НАЧАЛО НОВОГО ЧАТА

Я работаю над **stressTest v2** — движком финансового моделирования
(3-statement model, credit rating, stress testing, covenants).
Две компании: US Steel (US GAAP) и Rusal (IFRS). Обе production ready.

**Рабочая папка:**
```
/Users/arturhusnutdinov/Documents/IT Development/Docker/stressTest_v2
```
**БД:** `data_mart_v2.db` (НЕ v3!)
**Rusal PDFs:** `/Users/arturhusnutdinov/Documents/IT Development/Docker/rusalFinStates`

---

## СТАТУС МОДЕЛЕЙ

```
US Steel: BS=0.000004  Rating BBB→A-  EBITDA margin 14.7%  — PRODUCTION READY
Rusal:    BS=0.000004  Rating B       EBITDA margin 10.7→8.1%  — PRODUCTION READY
```

### US Steel Forecast

| Year | Revenue | EBITDA | Margin | Net Income | Rating |
|------|--------:|-------:|-------:|-----------:|--------|
| 2025 | 14,284M | 2,103M | 14.7% | 1,229M | BBB |
| 2026 | 13,225M | 1,928M | 14.6% | 862M | BBB+ |
| 2027 | 12,386M | 1,791M | 14.5% | 773M | BBB+ |
| 2028 | 11,716M | 1,682M | 14.4% | 707M | BBB+ |
| 2029 | 11,174M | 1,594M | 14.3% | 657M | A- |

### Rusal Forecast

| Year | Revenue | EBITDA | Margin | Net Income | ND/EBITDA | ICR | Rating |
|------|--------:|-------:|-------:|-----------:|----------:|----:|--------|
| 2026 | 13,572M | 1,446M | 10.7% | 670M | 4.5x | 1.5x | B |
| 2027 | 14,366M | 1,413M | 9.8% | 719M | 4.6x | 1.7x | B+ |
| 2028 | 15,084M | 1,373M | 9.1% | 691M | 5.0x | 1.8x | B |
| 2029 | 15,543M | 1,345M | 8.7% | 660M | 5.2x | 1.9x | B |
| 2030 | 16,017M | 1,302M | 8.1% | 584M | 5.6x | 1.8x | B |

---

## АРХИТЕКТУРА ДВИЖКА

```
engine/
├── orchestrator.py          build_model() — E2E pipeline
├── preprocessor/core.py     1,095 строк — калибровка из истории (EWA, OLS)
├── ecm/                     VECM/MR макропрогнозирование
├── model/
│   ├── core.py              2,044 строк — ThreeStatementModel (iterative solve)
│   ├── loader.py            Загрузка конфига и DB → ModelConfig
│   ├── inputs.py            Dataclasses: YearState, ModelConfig, DebtSettings
│   └── schedules/
│       ├── debt.py          DebtOptimizer (instrument-level corkscrew)
│       ├── ppe.py           PPEBlock (additions/disposals/depreciation)
│       ├── tax.py           TaxBlock (NOL carryforward, DTA/DTL)
│       ├── lease.py         LeaseBlock (IFRS 16 / ASC 842)
│       ├── equity.py        EquityBlock (dividends, buybacks)
│       └── intangibles.py   IntangiblesBlock
├── stress/
│   ├── core.py              ShockSpec, StressScenario, ScenarioLoader
│   └── runner.py            428 строк — StressRunner (macro + driver shocks)
├── rating/core.py           459 строк — RatingEngine (S&P scorecard)
├── covenants/core.py        389 строк — CovenantsChecker (breach/warning/ok)
├── loader/                  ExcelLoader, EDGAR loader
└── database/                Repository (SQLite)

parsers/
├── pdf_parser.py            ~1,000 строк — Rusal PDF extraction (pdfplumber)
└── adapters/rusal.yaml      ~600 строк — YAML adapter

companies/
├── us_steel/configs/        project.yaml, stress_scenarios.yaml, macro_ecm.yaml
└── rusal/configs/           project.yaml, stress_scenarios.yaml, macro_ecm.yaml
```

### build_model() параметры

```python
build_model(
    company_id='rusal',
    run_preprocessor=True,   # калибровка параметров из истории
    run_macro=True,          # VECM/MR макро-прогноз
    run_model=True,          # 3-statement model
    run_stress=False,        # stress scenarios
    run_rating=False,        # S&P credit rating
    run_covenants=False,     # covenant monitoring
)
# Returns: BuildResult with .model_result, .stress_results, .rating_result, .covenants_result
```

### Iterative Solve Loop (core.py)

```
Revenue → COGS → SGA → EBITDA → D&A → EBIT
  → Debt(interest) → EBT → Tax(NOL) → NI → Cash → Debt (again)
Convergence: cash_delta < $1,000 AND ni_delta < $1,000, max 15 iterations
```

---

## КОНФИГУРАЦИЯ

### US Steel (US GAAP)

- **Mode:** custom, debt=full (schedule_based alias)
- **Revenue:** elastic_net on steel_price_hrc
- **COGS:** standard, PPI uplift (ppi_us, beta=1.0)
- **Macro:** gdp_us, industrial_production_us, dxy, steel_price_hrc, iron_ore_price, cpi_us, ppi_us, gdp_world
- **Debt:** 30 instruments (7 active), revolving credit $2B, min_cash $596M
- **Covenants:** steel methodology (ND/EBITDA≤3.5, ICR≥2.5, D/E≤3.0, CR≥1.0, EBITDA%≥5%)
- **Rating:** S&P, industry_adj=-12.0, size_adj=+2.0, cycle_avg_margin=10%
- **Stress:** 1 scenario (covenant_breach)
- **Sign convention:** credit_negative (US GAAP stores income as negative)

### Rusal (IFRS)

- **Mode:** custom, debt=optimizer
- **Revenue:** segment_modeling=True (primary_al + alumina + other)
- **COGS:** component-based (alumina 37%, energy 27%, labour 12%, other 24%)
- **Macro:** lme_aluminium, lme_alumina, usd_rub, brent, gdp_world, cpi_ru, ppi_ru, russian_power_price
- **Debt:** 71 instruments (23 active 2026), no RC, CBR KeyRate linked (9 floaters)
  - CBR forecast: 2026=14%, 2027=11%, 2028=9%, 2029=8%, 2030=7%
- **Covenants:** default methodology + metals industry override
  - ND/EBITDA≤4.5, ICR≥2.0, D/E≤4.0, CR≥1.0, EBITDA%≥5%
  - Acceleration triggers: interest_coverage, net_debt_ebitda
- **Rating:** S&P, industry_adj=-6.0, size_adj=+2.0, cycle_avg_margin=12%
- **Stress:** 8 scenarios (lme_mild, aluminium_downturn, sanctions_shock, energy_spike, rate_spike, severe, upside, covenant_breach)
- **Features:** use_ppe_corkscrew, use_wc_days, use_tax_corkscrew, use_intangibles_corkscrew, use_interest_payable_cork (all true), use_debt_rc=false
- **Sign convention:** natural (expenses negative)

---

## DEBT OPTIMIZER — CANONICAL MAPPING

Debt optimizer reads instruments from `debt_instruments` table and produces a corkscrew per instrument per year.

**BS mapping:**
- `short_term_debt` ← DebtSolveResult.st_debt (Rules: RC=ST; maturity≤yr+1=ST; next_amort=current_portion; breach+callable=ST)
- `long_term_debt` ← DebtSolveResult.lt_debt (everything else + remainder of partial splits)

**IS mapping:**
- `interest_expense_debt` ← sum(instrument.interest) × (1 - cap_pct)
- `interest_expense` ← interest_expense_debt + interest_expense_leases
- `loss_on_debt_extinguishment` ← sum(refi_fees)

**CF mapping:**
- `cff_debt_issuance` ← sum(draw + refi_draw)
- `cff_debt_repayment` ← -sum(repay)

**Verified:** Total debt (ST+LT) matches corkscrew closing exactly (Δ=0). Interest and CF flows match exactly. BS=0.000004.

---

## DB STATE (data_mart_v2.db)

### Rusal Data

| Table | Rows | Content |
|-------|-----:|---------|
| history_is | 281 | IS 2011-2025 (15 years) |
| history_bs | 450 | BS 2012-2025 (14 years) |
| history_cf | 544 | CF 2011-2025 (15 years) |
| ppe_components | 273 | PPE cost+accum_dep, 2022-2025 |
| debt_instruments | 71 | Note 19: loans, bonds, floaters |
| debt_schedule | 597 | Instrument × year schedule |
| intangible_assets | 24 | Note 14 |
| tax_schedule | 6 | Note 8 DTA/DTL |
| provisions_schedule | 20 | Note 20 |
| associates_schedule | 54 | Note 15 |
| operational_drivers | 73 | Al/Alumina KPI + geo revenue |
| segment_data | 168 | Revenue segments |
| macro_forecasts | 92 | 8 factors forecast |

### US Steel Data

| Table | Rows |
|-------|-----:|
| history_is | 329 |
| history_bs | 669 |
| history_cf | 614 |
| ppe_components | 330 |
| debt_instruments | 38 |
| debt_schedule | 338 |
| tax_schedule | 15 |
| equity_schedule | 15 |
| lease_schedule | 11 |
| macro_forecasts | 292 |

---

## PDF PARSER

**Code:** `parsers/pdf_parser.py` (~1,000 lines) + `parsers/adapters/rusal.yaml` (~600 lines)

**5 parsing modes:**

| Method | Mode | Use case |
|--------|------|----------|
| `parse_section()` | standard | IS, BS, CF, Inventory |
| `parse_pivot_note()` | text pivot | PPE, Intangibles, Provisions |
| `parse_pivot_note()` | wide pivot | Associates |
| `parse_pivot_note()` | sequential | DTA/DTL, Tax reconciliation |
| `parse_instrument_list()` | instrument | Debt schedule |

**Coverage:** IS 2011-2025, BS 2012-2025, CF 2011-2025. Notes 8/13/14/15/16/19/20.
**Tests:** 22 unit tests, 12 smoke tests. All pass.

---

## EXCEL & DATA LOADING

**Excel:** `companies/rusal/data/rusal_complete_v4.xlsx` — 21 sheets, 58 KB

**Loading pipeline:**
```
ExcelLoader.load()              → 2,280 rows (IS/BS/CF, PPE, Debt, Segments, Macro)
load_schedule_sheets.py         → 177 rows (Intangibles, Tax, Provisions, Associates, Operational)
Total: 2,457 rows → data_mart_v2.db
```

**Test stand:** `tests/integration/` — setup, load, verify (11 tables, BS identity). Result: PASS.

---

## УЧЕБНИК

- **Source:** `docs/financial_modeling_textbook_rewritten.md` (3,162 lines, 213 KB)
- **PDF:** `docs/financial_modeling_textbook_rewritten.pdf` (54 pages, 280 KB)

**Structure:**
1. Основы финансовой отчетности
2. Внешняя среда: макро и отраслевые факторы
3. Введение в анализ временных рядов
4. Методы прогнозирования: ARIMA → VECM
5. Построение 3-Statement модели + 5.1b Препроцессор
6. Валидация: Train/Test Split
7. Архитектура движка + 7.3.4 Stress & Rating + 7.3.6b Covenants + 7.7 YAML Guide
8. Практический пример: US Steel
8b. Практический пример: Rusal
9. Канонические формы + 9b Загрузка данных
10. Заключение

---

## КЛЮЧЕВЫЕ ПРИНЦИПЫ

```
БД: data_mart_v2.db (НЕ v3!)
US Steel: не трогать без необходимости — зафиксирован
Prod BS: должен оставаться 0.000004 для обеих компаний
Parser: INSERT only в DB, не overwrite
YAML: policy/parameters only, не числа модели
Коммиты: не делать без явного запроса
```

---

## QUICK START

```bash
cd /Users/arturhusnutdinov/Documents/IT Development/Docker/stressTest_v2

# Проверить prod
python3 -c "
import sys, logging; sys.path.insert(0,'.'); logging.disable(logging.CRITICAL)
from engine.orchestrator import build_model
for co in ['us_steel','rusal']:
    r = build_model(co, run_preprocessor=False, run_model=True)
    print(f'{co}: BS={max(r.model_result.bs_diffs.values()):.6f}')
"
# Ожидание: us_steel=0.000004, rusal=0.000004

# Проверить parser
python3 parsers/tests/test_parser_helpers.py   # 22/22

# Полный pipeline с stress/rating/covenants
python3 -c "
import sys, logging; sys.path.insert(0,'.'); logging.disable(logging.CRITICAL)
from engine.orchestrator import build_model
r = build_model('rusal', run_preprocessor=False, run_model=True,
                run_stress=True, run_rating=True, run_covenants=True)
print(f'BS={max(r.model_result.bs_diffs.values()):.6f}')
print(f'Stress: {len(r.stress_results)} scenarios, all OK={all(s.success for s in r.stress_results.values())}')
print(f'Rating: {r.rating_result.ratings[2026][\"rating\"]}')
print(f'Covenants: {len(r.covenants_result.breaches())} breaches')
"
```

---

## ВОЗМОЖНЫЕ СЛЕДУЮЩИЕ ШАГИ

### Расширение Rusal
- Equity Schedule парсер (SOCIE — Statement of Changes in Equity)
- Lease corkscrew полный (Note 9, сейчас ratio-based)
- Гео-данные 2012-2014 из старых AR (сложная верстка)
- Дополнительные macro: caustic_soda_price, anode_carbon_price

### Новая компания
1. Скопировать `companies/rusal/` как шаблон
2. Создать Excel по образцу `rusal_complete_v4.xlsx`
3. Настроить `project.yaml` (mode, macro_factors, features)
4. Загрузить через `01_Data_Loading.ipynb` → data_mart_v2.db
5. `build_model()` → BS≈0

### Улучшение учебника
- Практические задания в конце каждой главы
- Глоссарий терминов
- Перевод на английский

### Инфраструктура
- Dashboard (Streamlit/Gradio) для визуализации результатов
- CI/CD: автотесты BS regression при коммитах
- Dockerization для развёртывания
