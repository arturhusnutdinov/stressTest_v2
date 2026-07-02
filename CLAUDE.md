# CLAUDE.md — stressTest_v2

## Стиль работы
- Отвечать кратко, на русском, без лишних объяснений
- Результат сразу: таблицы и код вместо описаний
- Artur — опытный разработчик (Python, IFRS/US GAAP, кредитный анализ), детальных пояснений не нужно

## Git
- Коммиты и пуш — **только по явному запросу**
- Remote: `git@github.com:arturhusnutdinov/stressTest_v2.git`, ветка `main`
- Не использовать `--no-verify`, не амендить публичные коммиты

## База данных
- **Единственная БД:** `data_mart_v2.db` — не создавать v3 и другие
- **INSERT only** — не перезаписывать существующие данные
- **YAML конфиги:** только policy/parameters, не числа модели (числа через preprocessor)
- **После любых изменений:** проверить `BS diff == 0.000004` для обеих компаний

## Запуск моделей
Полный pipeline (по запросу "прогони модель"):
```python
build_model('rusal', run_preprocessor=False, run_model=True,
            run_stress=True, run_rating=True, run_covenants=True)
```
Показывать: BS diff, stress (все сценарии), rating по годам, covenant breaches,
forecast таблица (Rev/EBITDA/Margin/NI/ND-EBITDA/ICR/Rating), debt schedule, debt corkscrew vs BS.

## Архитектура (v2.1.1)
```
Pipeline: Preprocessor → Macro → ThreeStatementModel → Stress/Rating/Covenants

engine/
  model/core.py          # 3-statement solver, до 10 итераций, tolerance $1K
  model/blocks/          # revenue, sga, cash, bs_totals, is_subtotals, bs_other
  model/schedules/       # debt, ppe, tax (IAS 12), lease, equity, wc, intangibles
  constants.py           # 81 именованная константа
  preprocessor/core.py
  macro/vecm.py
  stress/, rating/, covenants/
```

## Компании

### US Steel
- US GAAP, 2010-2024 → 2025-2029
- 38 debt instruments, `tax_paid_timing: next_year`
- Rating BBB→A-, ND/EBITDA ≤ 3.5x
- Чувствителен к TaxBlock (NOL $1B + accel_dep 40%) — проверять BS после изменений

### Rusal
- IFRS, 2011-2025 → 2026-2030
- 69 instruments в DB, 9 CBR floaters (KeyRate: 2026=14%, 2027=11%, 2028=9%, 2029=8%, 2030=7%)
- Revenue: segment_modeling=True (primary_al + alumina + other)
- COGS: компонентный (alumina 37%, energy 27%, labour 12%, other 24%)
- 8 стресс-сценариев: lme_mild, aluminium_downturn, sanctions_shock, energy_spike, rate_spike, severe, upside, covenant_breach
- Covenants: ND/EBITDA ≤ 4.5, ICR ≥ 2.0
- Features (все true): use_ppe_corkscrew, use_wc_days, use_tax_corkscrew, use_intangibles_corkscrew, use_interest_payable_cork
- При изменениях: проверять все 8 стресс-сценариев + debt corkscrew (Δ=0)
- PDFs: `/Users/arturhusnutdinov/Documents/IT Development/Docker/rusalFinStates/`

### Nornickel
- IFRS, USD, `is_income_sign=natural`
- Metals/mining: Ni (~35%), Pd (~30%), Cu (~20%), Pt (~10%)
- Тикер: MOEX: GMKN
- **Статус Этапы:**
  1. ✅ Init (2026-05-18)
  2. ✅ Data Collection — Databook + iXBRL → Excel (2026-05-18)
  3. ⬜ Data Loading → DB
  4. ⬜ Revenue Analysis → макро-факторы
  5. ⬜ YAML Config → Model Run → Stress/Rating/Validation
- **Дневник:** `companies/nornickel/PROJECT_DIARY.md` — всегда обновлять
- **Данные:** `companies/nornickel/data/statements/Databook_12m_25_Final.xlsx` (2009-2025)
- **Excel:** `companies/nornickel/data/excel/nornickel_unified.xlsx` (22 листа, 2011-2025)
- **Пробелы:** см. `companies/nornickel/DATA_AUDIT.md` + `DATA_GAPS_ANALYST_GUIDE.md`

## TaxBlock (IAS 12 / ASC 740)
`engine/model/schedules/tax.py`
- Total Tax = Current Tax + Deferred Tax
- Current = rate × max(0, EBT − NOL_used − accel_dep_excess)
- Deferred = −(ΔDTL − ΔDTA)
- NOL used = min(nol_open, EBT × 80%) — TCJA cap
- Payment timing из config: US Steel=`next_year`, Rusal=`current_year`
- Референс: `docs/Financial-Modeling-Guidelines.pdf` (CFI, p.30-31, 37, 41-48)

## Ключевые файлы
| Путь | Назначение |
|------|-----------|
| `engine/orchestrator.py` | Точка входа, `build_model()` |
| `engine/model/core.py` | 3-statement solver |
| `engine/constants.py` | Все константы |
| `data_mart_v2.db` | Единственная БД |
| `docs/Financial-Modeling-Guidelines.pdf` | CFI benchmark (94 стр.) |
| `companies/nornickel/PROJECT_DIARY.md` | Дневник Норникеля |
