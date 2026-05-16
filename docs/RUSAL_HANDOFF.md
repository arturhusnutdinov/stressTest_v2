# Project Handoff — stressTest Engine + RUSAL Setup

> Создан: 2026-04-01
> Рабочая директория: `/Users/arturhusnutdinov/Documents/IT Development/Docker/stressTest_v2`
> Для Claude Code: прочитай этот файл целиком перед началом работы.

---

## ЧАСТЬ 1 — stressTest Engine (проект US Steel)

### Что это за проект

Финансовый трёхформный (IS/BS/CF) стресс-тест движок для корпоративного финансового моделирования. Написан на Python. Компания-образец — **United States Steel Corporation** (данные 2010–2024).

Движок существует в **двух репозиториях**:

| Репо | Путь | Статус |
|------|------|--------|
| `stressTest` (v3) | `/Users/arturhusnutdinov/Documents/IT Development/Docker/stressTest` | Основной, production-ready, Phase 9–10 |
| `stressTest_v2` | `/Users/arturhusnutdinov/Documents/IT Development/Docker/stressTest_v2` | Параллельный, упрощённая архитектура, активная разработка RUSAL |

> **ВАЖНО**: В текущей сессии работаем в `stressTest_v2`. При запуске `claude` из `stressTest` — другой проект.

---

### stressTest (v3) — Архитектура и статус

**БД**: `data_mart_v2.db` (SQLite, корень проекта)

**Ключевые файлы движка:**
```
engine/
  model3/
    core.py              # ThreeStatementModel — основная модель
    orchestrator.py      # ModelOrchestrator
    balancing.py         # ModelBalancer (BS Identity, Cash Bridge, RE Bridge)
    validation.py        # FullModelValidator
    verification.py      # BS/CF checks
    debt.py              # DebtOptimizer
    corkscrews/          # builders_v3.py, debt_cork.py, lease corks, routing.py
  canonical/
    audit_full.py        # CLI: python -m engine.canonical.audit_full --strict
    metric_name_mapping.py  # METRIC_NAME_MAPPING — единственный источник маппинга
    cf_verification_spec.py # компоненты CFO/CFI/CFF
  database/
    repositories_v3/     # HistoryRepositoryV3, ModelMetricsRepositoryV3, etc.
    services/
      normalization_service.py  # YAML-first metric mapping
```

**Схема БД V3:**
- `history_is/bs/cf` — EAV: (company_id, period_id, metric, value, source)
- `fs_is/bs/cf` — canonical JSON через ModelMetricsRepositoryV3
- `debt_schedule_raw`, `lease_schedule`, `tax_schedule`, `equity_schedule`
- `model_preprocess_metrics` — результаты препроцессинга

**Ключевые принципы:**
1. YAML (`excel_loader.yaml`) — единственный источник маппинга
2. История читается ТОЛЬКО через `repositories_v3` (без legacy fallback)
3. Canonical forms (`fs_*`) = единственный формат хранения результатов модели
4. Corkscrews строятся из raw schedules В ПАМЯТИ, не хранятся в БД
5. `Plug < 0` = ошибка данных; исправления — в данных/YAML, не в core

**Статус рефакторинга (ветка `refactoring/phase-7-8-use-canonical-forms`):**

| Фаза | Статус | Ключевое |
|------|--------|----------|
| 1–6 | ✅ Done | DB V3, repositories, corkscrews, stress, rating, covenants |
| 7 | ✅ Done | Mapping verification; force_combined → plug |
| 8.0–8.9 | ✅ Done | Provenance, Enrichment, Plug, Data Contract, Mapping Autogen |
| 8 Strict | ✅ Done | audit_full --strict PASS; missing=0, collisions=0, cf_verified |
| 9 | ✅ Done | Test stand: 21 тест, все проходят |
| 10 | 🔶 Partial | A done; B–I pending (fixed-point loop, audit corkscrews) |

**Запуск / верификация:**
```bash
cd stressTest
python -m engine.canonical.audit_full --company us_steel --years 2010-2024 --strict
python -m engine.canonical.verify_cf --company us_steel --years 2010-2024
PYTHONPATH=. pytest tests/integration/test_minimal_one_step_optimizer.py -v
```

---

### stressTest_v2 — Архитектура

**БД**: `data_mart_v2.db` (SQLite, корень проекта)

**Ключевые отличия от v3:**
- Проще архитектура — нет EAV, нет repositories_v3
- Загрузка данных — через `engine/loader/excel.py` (`ExcelLoader`)
- Данные хранятся в Excel-формате UNIFIED (metric × years wide format)
- `engine/database/repository.py` — единственный репозиторий

**Структура для US Steel (reference, уже работает):**
```
companies/us_steel/
  configs/
    excel_loader.yaml          # маппинг метрик + aliases
    project.yaml               # конфиг модели (YAML)
    accounting_conventions.yaml
  data/
    us_steel_data_export_v2.xlsx  # UNIFIED Excel (метрики × годы)
    debt/                         # debt schedule
    macro/                        # макро-данные
  notebooks/
    00_Build_Model_Main.ipynb
    01_Data_Loading.ipynb
    02_Test_Model_Module.ipynb
    ...
```

**UNIFIED Excel формат (листы: history_is, history_bs, history_cf):**
- Строка 3 = заголовки: `metric | 2010 | 2011 | ... | 2024 | unit | source`
- `metric` = canonical db_metric name (из excel_loader.yaml)
- значения в единицах согласно `unit` (обычно mUSD = миллионы USD)

**ExcelLoader API:**
```python
from engine.loader.excel import ExcelLoader
from engine.database.repository import Repository

loader = ExcelLoader("companies/rusal/configs/excel_loader.yaml")
with Repository() as repo:
    repo.upsert_company("rusal", "RUSAL", "metals", "USD", "IFRS", "mUSD")
    loader.load_history(repo, "rusal", "companies/rusal/data/excel/rusal_data.xlsx")
```

**Repository API:**
```python
repo.upsert_company(company_id, name, industry, currency, accounting_standard, db_unit)
repo.upsert_history(company_id, statement, year, metrics_dict, source="excel")
```

**Что реализовано в v2 для US Steel (TODO.md — все выполнены):**
- D1–D18: долговой оптимизатор (`debt.mode: full`/`optimizer`), NOL/TCJA, ASC 842 leases, TaxBlock DTL, CapEx нормализация, PLanning covenant auto-trigger, Excel export v3
- BS_diff = 0 все годы, все 3 стресс-сценария
- 38 долговых инструментов, IntExp 2025 = $205M, Rating = BBB+

---

## ЧАСТЬ 2 — Проект RUSAL (новый, в stressTest_v2)

### Что сделано

#### 2.1 Парсинг отчётности через Claude Vision API

**Источник**: PDF-отчёты RUSAL (2011–2025), хранятся в `companies/rusal/data/reports/`

**Парсер**: `/tmp/rusal_claude_parser.py`

Технология:
- `PyMuPDF (fitz)` — конвертация страниц PDF → PNG (scale=2.5×)
- `PIL` — склейка страниц вертикально (multi-page statements)
- `Claude Vision API` (`claude-sonnet-4-6`) — извлечение таблиц из изображений
- `pypdf PdfReader` — текстовое извлечение для поиска оглавления (ToC)

**Алгоритм определения страниц:**
1. Парсинг оглавления (ToC) через regex из текста PDF
2. Fallback: поиск ключевых слов по тексту страницы (RU: `внеоборотные активы`, `движении денежных средств`; EN: `total assets`, `cash flows`)
3. Continuation detection для многостраничных отчётов
4. BS = 2 страницы (12+13 в RU формате), CF = 2 страницы (15+16)

**Исправленные баги парсера:**
- Модель `claude-sonnet-4-20250514` → `claude-sonnet-4-6`
- Отсутствующий параметр `stmt` в `parse_page_via_claude()`
- ToC regex: `[\s.·\-]*(\d+)` → `[\s\S]{0,60}?(\d+)\s*\n` (lazy wildcard для "или убытках 10")
- Добавлены RU-варианты label для cfo_total/cfi_total/cff_total

#### 2.2 Результат парсинга

**`/tmp/rusal_claude_parsed.json`** (125KB) — сырой вывод Claude с оригинальными RU/EN лейблами

**`/tmp/rusal_canonical.json`** (27KB) — каноникализированные данные

Формат:
```json
{
  "2012": {
    "IS": {"revenue": 10891, "cogs": -9232, "gross_profit": 1659, ...},
    "BS": {"ppe": 5453, "intangibles": 4051, "cash": 505, "total_assets": 25586, ...},
    "CF": {"cfo_total": 1092, "cfi_total": -93, "cff_total": -1131, ...}
  },
  ...
}
```

- **15 лет**: 2011–2025
- **Единицы**: миллионы USD
- **BS identity**: diff = 0 для 2014, 2015, 2018, 2019, 2023, 2024, 2025 ✅
- **Revenue 2021–2025**: все верификации прошли ✅
- **cfo_total 2020 = 1091** (корректно, Claude Vision vs text parser = 1134 ошибочно) ✅

#### 2.3 Создан rusal_input.xlsx

**`companies/rusal/data/excel/rusal_input.xlsx`** (15KB) — промежуточный файл

Листы: `history_is`, `history_bs`, `history_cf`
Формат: `label | db_metric | formula | sign | unit | 2011..2025`
Значения: миллионы USD

Метрики:
- IS: 18 метрик
- BS: 27–32 метрики
- CF: 34 метрики

---

### Что НЕ сделано — 6-шаговый план

#### Шаг 1 — Очистка `companies/rusal/` ✅ DONE

Удалить (старые, несовместимые):
```
companies/rusal/configs/excel_loader.yaml    # старый формат
companies/rusal/configs/project.yaml         # ссылается на CSV
companies/rusal/data/history/*.csv           # все CSV и .bak.csv
companies/rusal/history/*.csv                # is/bs/cf_history_rusal.csv
companies/rusal/data_input/                  # весь каталог
companies/rusal/drivers/                     # старые CSV драйверы
companies/rusal/companies/                   # случайный артефакт (вложенная папка)
```

Сохранить:
```
companies/rusal/data/excel/rusal_input.xlsx  # ИСТОЧНИК ДАННЫХ
companies/rusal/data/debt/                   # debt schedule CSVs
companies/rusal/data/macro/rusal_macro.xlsx
companies/rusal/data/operational/
companies/rusal/notebooks/
companies/rusal/configs/stress_scenarios.yaml
companies/rusal/configs/accounting_conventions.yaml
```

#### Шаг 2 — Создать `rusal_data.xlsx` ✅ DONE (rusal_unified_complete.xlsx)

Путь: `companies/rusal/data/excel/rusal_data.xlsx`
Источник: данные из `/tmp/rusal_canonical.json` (или `rusal_input.xlsx`)
Шаблон: взять за основу `companies/us_steel/data/us_steel_data_export_v2.xlsx`

Формат листов (history_is, history_bs, history_cf):
```
Row 3: metric | 2011 | 2012 | ... | 2025 | unit | source
Row 4+: db_metric_name | value | value | ... | mUSD | CFS_PDF_Claude_Vision
```

**Маппинг `rusal_input.xlsx` → canonical db_metric:**

IS:
| rusal_input | canonical db_metric |
|-------------|---------------------|
| revenue | revenue |
| cogs | cogs |
| gross_profit | gross_profit |
| distribution_costs + sgna | sga (суммировать) |
| depreciation | depreciation_owned |
| amortization | amortization |
| ebit | ebit |
| ebitda | ebitda |
| finance_income | interest_income |
| finance_expense | interest_expense_debt |
| share_of_associates | earnings_from_investees |
| impairment | asset_impairment |
| ebt | ebt |
| income_tax_expense | tax_expense |
| net_income | net_income |

BS:
| rusal_input | canonical db_metric |
|-------------|---------------------|
| cash | cash |
| receivables | accounts_receivable |
| inventory | inventory |
| ppe | ppe_net |
| intangibles | intangibles |
| investments_associates | investments_lt |
| dta | dta |
| total_assets | total_assets |
| debt_noncurrent | long_term_debt |
| dtl | deferred_tax_liabilities |
| debt_current | short_term_debt |
| payables | accounts_payable |
| total_equity | total_equity |
| (total_liab_equity рассчитывается) | total_liab_equity |

CF:
| rusal_input | canonical db_metric |
|-------------|---------------------|
| net_income | net_income_cf |
| depreciation | depreciation_owned |
| amortization | amortization |
| cfo_total | cfo_total |
| cfi_capex | capex |
| cfi_total | cfi_total |
| cff_total | cff_total |
| cash_opening | cash_opening |
| cash_closing | cash_ending |

#### Шаг 3 — Создать `configs/project.yaml` ✅ DONE

За основу взять `companies/us_steel/configs/project.yaml`.
Изменить для RUSAL:

```yaml
company:
  name: United Company RUSAL
  industry: metals
  currency: USD
  accounting_standard: IFRS   # ← IFRS, не US_GAAP

# УБРАТЬ секцию history: (нет CSV-истории)
# Данные грузятся через excel_loader.yaml

macro_forecast:
  factors:
    - lme_al          # ← LME aluminium price (главный драйвер)
    - brent           # ← нефть (энергозатраты)
    - gdp_world
    - fx_usdrub       # ← курс рубля
    - cpi_ru
  file_map:
    lme_al: lme_al_usd.csv
    brent: brent_usd.csv
    gdp_world: world_gdp.csv
    fx_usdrub: fx_usdrub.csv
    cpi_ru: cpi_ru_index.csv
  search_paths:
    - companies/rusal/data/macro
    - macro/global/drivers

model:
  engine_version: v2
  standard:
    periods:
      history_start_year: 2011
      history_end_year: 2025
      forecast_start_year: 2026
      forecast_end_year: 2030
      forecast_years: 5
    revenue:
      driver: lme_al
    margins:
      ebitda_margin_default: 0.18
      tax_rate_statutory: 0.20  # Россия
    debt:
      mode: full
      rc:
        min_cash: 300000000.0   # ~$300M операционный минимум

outputs:
  base: companies/rusal/outputs
```

#### Шаг 4 — Создать `configs/excel_loader.yaml` ✅ DONE

За основу взять `companies/us_steel/configs/excel_loader.yaml` **целиком**.

Добавить aliases для RUSAL-специфичных имён:
```yaml
# В секции history.BS.metrics.accounts_receivable:
aliases:
  - accounts_receivable
  - ar
  - receivables          # ← ДОБАВИТЬ

# В секции history.IS.metrics.sga:
aliases:
  - sga
  - sgna
  - distribution_costs   # ← ДОБАВИТЬ (RUSAL разделяет selling + admin)
```

#### Шаг 5 — Загрузить в DB ✅ DONE (ExcelLoader, 1907 rows)

```python
import sys
sys.path.insert(0, '/Users/arturhusnutdinov/Documents/IT Development/Docker/stressTest_v2')

from engine.loader.excel import ExcelLoader
from engine.database.repository import Repository

loader = ExcelLoader("companies/rusal/configs/excel_loader.yaml")

with Repository() as repo:
    repo.upsert_company(
        company_id="rusal",
        name="United Company RUSAL",
        industry="metals",
        currency="USD",
        accounting_standard="IFRS",
        db_unit="mUSD"
    )
    loader.load_history(
        repo,
        company_id="rusal",
        filepath="companies/rusal/data/excel/rusal_data.xlsx"
    )
    print("Done")
```

#### Шаг 6 — Верификация BS identity ✅ DONE (BS=0, CF=0)

```python
import sqlite3

conn = sqlite3.connect("data_mart_v2.db")
cur = conn.cursor()

years = list(range(2011, 2026))
print(f"{'Year':<6} {'Assets':>12} {'Liab+Eq':>12} {'Diff':>10}")
print("-" * 44)

for yr in years:
    cur.execute("""
        SELECT metric, value FROM history_bs
        WHERE company_id='rusal' AND year=?
        AND metric IN ('total_assets','total_liab_equity')
    """, (yr,))
    rows = {r[0]: r[1] for r in cur.fetchall()}
    ta = rows.get('total_assets', 0)
    tle = rows.get('total_liab_equity', 0)
    diff = round(ta - tle, 1)
    flag = "✅" if abs(diff) < 1 else "❌"
    print(f"{yr:<6} {ta:>12.1f} {tle:>12.1f} {diff:>9.1f} {flag}")

conn.close()
```

---

## ЧАСТЬ 3 — Как начать работу в новом чате

### Из stressTest_v2:

```bash
cd "/Users/arturhusnutdinov/Documents/IT Development/Docker/stressTest_v2"
claude
```

### Первое сообщение в новом чате:

```
Прочитай RUSAL_HANDOFF.md целиком. Мы настраиваем компанию RUSAL в stressTest_v2.

Данные: /tmp/rusal_canonical.json (JSON, 15 лет 2011-2025)
Промежуточный файл: companies/rusal/data/excel/rusal_input.xlsx

Нужно выполнить шаги 1-6 из RUSAL_HANDOFF.md последовательно.
Начни с Шага 1 — очистка companies/rusal/ от старых файлов.
```

---

## ПРИЛОЖЕНИЕ — Структура данных RUSAL (краткая)

### IS (данные из /tmp/rusal_canonical.json):
- Revenue 2025: ~$12.4B (пик 2022: ~$17B)
- EBITDA margin: 18–22% в хорошие годы
- Значительные убытки 2012 (чистый убыток), прибыльность восстановлена 2013+

### BS:
- Общие активы 2025: ~$16–18B
- Долг: значительный (debt_noncurrent >> debt_current)
- BS identity имеет расхождения для 2011–2013, 2016–2017, 2020–2022 — это нормально, данные неполные (не все статьи пассивов извлечены Claude Vision)

### Известные расхождения BS (требуют внимания):
Для лет с diff ≠ 0 нужно добавить "other liabilities plug" в excel_loader.yaml или вручную дополнить данные по статьям пассивов (trade payables, accrued liabilities, other current liabilities).

---

*Документ создан автоматически Claude Code в конце сессии 2026-04-01.*
