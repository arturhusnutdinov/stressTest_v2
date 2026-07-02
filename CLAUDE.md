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

## Архитектура (v2.2)

### Pipeline
```
Preprocessor → Macro (VECM/MR/EWA) → ThreeStatementModel → Stress → Rating → Covenants
```

### Структура engine/
```
engine/
├── orchestrator.py              # Точка входа build_model()
├── constants.py                 # 72 именованных константы (все модули импортируют)
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
- 69 instruments, 9 CBR floaters (KeyRate: 2026=14%→2030=7%)
- Revenue: segment_modeling (primary_al + alumina + other)
- COGS: component-based (configurable factors: commodity, energy, FX, CPI, PPI)
- 8 стресс-сценариев
- Covenants: ND/EBITDA ≤ 4.5, ICR ≥ 2.0
- Features: use_ppe/wc_days/tax/intangibles/interest_payable corkscrew (все true)
- **Optional features** (disabled, config ready):
  - `sga_split_enabled: true` → distribution/admin/ECL/other_opex
  - `provisions_corkscrew_enabled: true` → pension/site_restoration/legal
  - `deferred_tax_categories.enabled: true` → PPE/Inv/AR/AP rates
  - `tax_rate_statutory: 0.25` → uncomment когда данные 2025+ загружены
- PDFs: `/Users/arturhusnutdinov/Documents/IT Development/Docker/rusalFinStates/`
- **Excel:** `companies/rusal/data/excel/rusal_unified.xlsx` (31 лист, полный export из DB)

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
| `engine/constants.py` | 72 именованных константы |
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
