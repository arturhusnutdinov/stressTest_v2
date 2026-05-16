## STATUS [2026-04-03]
- US Steel: BS=0, CF=0, Stress OK
- Rusal: BS=6M, CF=0, Revenue $13.9→15.7B (LME linked), Stress OK
- All params from preprocessor (no YAML hardcodes)
- 8 macro factors with 2025-2029 forecasts
# RUSAL — Контекст для Claude Code
**Проект:** stressTest Engine v2 | **Дата:** Апрель 2026 | **Статус:** Фаза данных

---

## 0. ОБЯЗАТЕЛЬНАЯ ПРОВЕРКА ПРИ СТАРТЕ

```python
import sys; sys.path.insert(0, '.')
from engine import ROOT, DB_PATH
assert str(ROOT).endswith('stressTest_v2'), f'СТОП! ROOT={ROOT}'
assert 'v3' not in str(DB_PATH), f'СТОП! DB={DB_PATH}'
print(f'ROOT OK: {ROOT}')
print(f'DB OK:   {DB_PATH}')
```

---

## 1. АРХИТЕКТУРА ДВИЖКА (уже готова, не трогать)

### 1.1 Ключевой принцип
Движок **универсальный**. US Steel — референсная реализация. Rusal — вторая компания на том же движке.
**Не создаём новые скрипты** — используем существующую инфраструктуру.

### 1.2 Единая точка входа
```python
from engine.orchestrator import build_model

result = build_model('rusal',
    run_preprocessor=True,
    run_macro=True,
    run_model=True,
    run_stress=True,
    run_rating=True,
    run_covenants=True)
```

### 1.3 Структура проекта
```
stressTest_v2/
├── engine/
│   ├── orchestrator.py           ← build_model() — единственная точка входа
│   ├── model/
│   │   ├── core.py               ← ThreeStatementModel (joint iteration solver)
│   │   ├── inputs.py             ← YearState, HistoricState, ModelConfig, LeaseParams
│   │   ├── loader.py             ← ModelInputLoader
│   │   └── schedules/
│   │       ├── debt.py           ← DebtOptimizer (7 шагов)
│   │       ├── tax.py            ← TaxBlock (NOL/DTA/DTL)
│   │       ├── lease.py          ← FinanceLeaseBlock + OperatingLeaseIFRS16  ← ВАЖНО
│   │       ├── wc.py             ← WCBlock (6 corkscrew)
│   │       ├── ppe.py            ← PPEBlock
│   │       └── equity.py         ← EquityBlock
│   ├── preprocessor/core.py      ← 13 групп EWA параметров
│   ├── macro/runner.py           ← VECM + MR + EWA
│   ├── stress/                   ← StressRunner
│   ├── rating/core.py            ← CreditMetrics + RatingEngine
│   ├── covenants/core.py         ← CovenantsChecker
│   ├── loader/excel.py           ← ExcelLoader (уже работает)
│   └── database/repository.py   ← Repository (единственный доступ к БД)
├── companies/
│   ├── us_steel/                 ← РЕФЕРЕНС (не трогать)
│   └── rusal/
│       ├── configs/
│       │   ├── project.yaml      ← УЖЕ СОЗДАН
│       │   └── excel_loader.yaml ← УЖЕ СОЗДАН
│       ├── data/
│       │   ├── rusal_data_export.xlsx  ← ЧАСТИЧНО ГОТОВ (IS/BS/CF ✅)
│       │   └── raw_pdfs/         ← 31 PDF (AR + CFS 2012-2024)
│       └── notebooks/            ← 10 ноутбуков УЖЕ СОЗДАНЫ
└── data_mart_v2.db               ← SQLite (ТОЛЬКО эта БД!)
```

---

## 2. КАК РАБОТАЕТ US STEEL (референс)

### 2.1 Поток данных
```
Excel (us_steel_data_export_v2.xlsx)
  ↓ ExcelLoader + excel_loader.yaml
data_mart_v2.db (history_is/bs/cf, debt_instruments, lease_schedule)
  ↓ ModelInputLoader + project.yaml
HistoricState + ModelConfig
  ↓ ThreeStatementModel (joint iteration, max_iter=10)
YearState × 5 лет (2025-2029)
  ↓ ModelSaver
data_mart_v2.db (forecast_is/bs/cf)
```

### 2.2 Критические правила (нельзя нарушать)
1. **BS=0**: Total Assets = Total Liabilities + Equity (diff < $1)
2. **CF bridge**: Cash = prev_cash + CFO + CFI + CFF (не BS plug!)
3. **cfo_other ≈ 0**: нет балансировочного плага
4. **Знаки**: liabilities хранятся как отрицательные, в CF delta берём abs()
5. **Все параметры из препроцессора/YAML**: никакого хардкода

### 2.3 US Steel результаты (эталон)
```
2025: Rev=14.78B  EBITDA=12.7%  NI=946M  LTD=3179M  ND/EB=1.21x  Rating=BB+
BS=0.000008  CF=0.000000  NOL eff=4.2%  Стрессы: 3/3 PASS
```

---

## 3. КЛЮЧЕВЫЕ ОТЛИЧИЯ RUSAL vs US STEEL

| Параметр | US Steel | RUSAL |
|---|---|---|
| Стандарт | US GAAP | **МСФО (IFRS)** |
| Лизинг | ASC 842 | **IFRS 16** |
| Операционная аренда CF | ВЕСЬ платёж → CFO | interest → CFO, **principal → CFF** |
| Выручка | 1 сегмент (сталь) | **4 сегмента**: Al, глинозём, фольга, прочее |
| Revenue driver | HRC price | **LME Al price** |
| COGS метод | ratio × Revenue | **unit_cost × volume** (или ratio fallback) |
| Ассоциированные | нет | **Норникель** → earnings_from_associates |
| Макро | HRC, SPPI | **LME Al, LME Al2O3, USD/RUB, power_price_ru** |
| NOL | $1,014M (TCJA) | нет (МСФО IAS 12) |
| Cap.interest | ASC 835-20 | **IAS 23** (та же логика) |
| Ковенанты | ND/EBITDA ≤ 3.5x | **ND/EBITDA ≤ 4.5x, ICR ≥ 2.0x** |

### 3.1 IFRS 16 vs ASC 842 — ключевое отличие
```
ASC 842 (US Steel):
  Операционная аренда: ВЕСЬ платёж → CFO
  dep_rou НЕ добавляется в total_da (уже в SGA)

IFRS 16 (RUSAL): ← уже реализован в lease.py как OperatingLeaseIFRS16
  Операционная аренда: interest → CFO, principal → CFF
  dep_rou ДОБАВЛЯЕТСЯ в total_da (D&A строка)
  
Движок уже поддерживает оба стандарта через LeaseBlock!
Нужно только: project.yaml → leases.standard: ifrs16
```

### 3.2 Earnings from associates (Норникель)
```python
# RUSAL владеет ~27.8% Норникеля
# Доля прибыли идёт в IS отдельной строкой
# Увеличивает BS: investments_associates += earnings - dividends_received

# В движке это уже есть как investee_earnings в YearState
# Для прогноза используется EWA из истории (волатильно!)
# 2024 факт: $564M (очень значимо — 70% от NI!)
```

---

## 4. ТЕКУЩЕЕ СОСТОЯНИЕ RUSAL (аудит от сессии)

### 4.1 Что уже готово ✅
| Компонент | Статус |
|---|---|
| companies/rusal/configs/project.yaml | ✅ создан |
| companies/rusal/configs/excel_loader.yaml | ✅ создан |
| companies/rusal/notebooks/ (10 шт) | ✅ созданы |
| history_is: IS 2012-2024 | ✅ 256 строк, конвертация USD ok |
| history_bs: BS 2012-2024 | ✅ 389 строк |
| history_cf: CF 2012-2024 | ✅ 501 строк |
| debt_instruments | ✅ есть |
| macro_factors: LME Al, Al2O3, USD/RUB, Brent | ✅ 4 фактора |
| Revenue 2024 = $12,082M | ✅ конвертация работает |
| ExcelLoader | ✅ работает |

### 4.2 Что отсутствует ❌
| Компонент | Приоритет | Источник |
|---|---|---|
| production_kpi таблица в БД | **P0** | xlsb прототип (лист "Raw Data_") |
| Production KPI история 2012-2024 | **P0** | xlsb + Annual Reports PDF |
| macro_factors: russian_power_price | **P1** | xlsb лист "Macro Data" |
| macro_factors: cpi_ru, ppi_ru | **P1** | xlsb / Росстат |
| Debt instruments: полный schedule | **P1** | xlsb листы "Loans", "Bonds" |
| Lease schedule IFRS 16 | **P1** | xlsb / Notes to FS |
| Segments: Al/Al2O3/foil breakdown | **P1** | xlsb лист "Raw Data_" |
| unit_costs: alumina/power/labour | **P2** | xlsb + Annual Reports |

### 4.3 Источники данных
```
xlsb прототип (3-Statement_Model__Template__Rusal_1.xlsb, 482KB):
  23 листа: Cover, Outputs, Inputs, Model, Financial Statements,
  Raw Data_ (сегменты!), Loans and Borrowings, Bonds,
  Macro Data (LME квартальные), Scenarios, Methods...

31 PDF файл (companies/rusal/data/raw_pdfs/):
  CFS 2012-2024 (Consolidated Financial Statements)
  AR 2012-2024 (Annual Reports — production KPI!)
```

---

## 5. ПЛАН ВЫПОЛНЕНИЯ (строго по фазам)

### ФАЗА 1: Полный Excel шаблон (ТЕКУЩАЯ)

**Задача**: Дополнить rusal_data_export.xlsx недостающими данными из xlsb прототипа.

```
ШАГ 1.1: Извлечь из xlsb → rusal_data_export.xlsx:
  - Лист "Raw Data_" → Production_KPI (Al kt, alumina kt, bauxite mt, unit costs)
  - Лист "Loans and Borrowings" → дополнить Debt_Instruments (maturities, rates)
  - Лист "Bonds" → дополнить Debt_Instruments
  - Лист "Macro Data" → дополнить Macro_Factors (power_price, CPI/PPI RU)
  - Лист "Financial Statements" → проверить Revenue schedule + segments
  - Лист "Scenarios" → сохранить как референс для YAML стрессов

ШАГ 1.2: Создать таблицу production_kpi в БД (engine/database/schema.py)

ШАГ 1.3: Загрузить через ExcelLoader → data_mart_v2.db

ШАГ 1.4: Верификация BS identity на истории:
  - total_assets = total_liab + equity КАЖДЫЙ ГОД
  - CF bridge: cash_end = cash_open + CFO + CFI + CFF
  - допуск $1M (МСФО округляет до $M)
```

### ФАЗА 2: Калибровка движка

```
ШАГ 2.1: Запустить препроцессор
  python3 -c "
  from engine.orchestrator import build_model
  build_model('rusal', run_preprocessor=True, run_model=False)
  "

  Ключевые параметры препроцессора для Rusal:
  - cogs_ratio_recommended (fallback если unit_cost нет)
  - lme_al_beta (OLS: dln(Rev) ~ β × dln(LME_Al), ожидается β≈1.0)
  - fin_principal_rate, op_decay_rate (IFRS 16)
  - cap_interest_pct (IAS 23, ожидается <40%)
  - earnings_associates_ewa (EWA Норникель, halflife=3)

ШАГ 2.2: Проверить project.yaml
  - accounting_standard: ifrs
  - leases.standard: ifrs16
  - revenue.macro_factor: lme_aluminium
  - associates.method: equity

ШАГ 2.3: Первый прогон модели
  build_model('rusal', run_preprocessor=False, run_model=True)
  → BS=0, CF=0 ОБЯЗАТЕЛЬНО
```

### ФАЗА 3: Тестирование

```
Бэктест 2023→2024:
  Revenue ±10%, EBITDA ±15%, NI ±30% (Associates волатильны!)

Стресс-сценарии:
  - aluminium_downturn: LME Al -25%
  - usd_rub_shock: USD/RUB +30%
  - energy_spike: power_price +40%

Ковенанты:
  - ND/EBITDA ≤ 4.5x (МЯГЧЕ чем у US Steel 3.5x)
  - ICR ≥ 2.0x

Рейтинг:
  - metals/mining calibration (не steel)
  - industry_adjustment = -6 (Al менее цикличен)
  - TTC margin = 12%
```

---

## 6. КАК ПРАВИЛЬНО ДОБАВИТЬ ДАННЫЕ В БД

### 6.1 Через ExcelLoader (предпочтительно)
```python
from engine.loader.excel import ExcelLoader
from engine.database.repository import Repository
from pathlib import Path

loader = ExcelLoader(
    company_id='rusal',
    excel_path=Path('companies/rusal/data/rusal_data_export.xlsx'),
    config_path=Path('companies/rusal/configs/excel_loader.yaml'),
)
with Repository(Path('data_mart_v2.db')) as repo:
    result = loader.load(repo)
    print(f'Загружено: {result.rows_written} строк, ошибок: {result.errors}')
```

### 6.2 Через Repository напрямую (для новых таблиц)
```python
with Repository(Path('data_mart_v2.db')) as repo:
    # IS/BS/CF
    repo.upsert_history('rusal', 'IS', 2024, 'revenue', 12082e6)
    
    # Production KPI (новая таблица)
    repo.upsert_production_kpi('rusal', 2024, 'production_al_kt', 3859.0)
    
    # Macro
    repo.upsert_macro_factor('rusal', 'russian_power_price', {2020: 2.1, 2021: 2.3, ...})
```

### 6.3 Знаки (ОБЯЗАТЕЛЬНО для МСФО)
```python
# Расходы → отрицательные:
repo.upsert_history('rusal', 'IS', yr, 'cogs',              -value)  # negative!
repo.upsert_history('rusal', 'IS', yr, 'sga',               -value)  # negative!
repo.upsert_history('rusal', 'IS', yr, 'interest_expense',  -value)  # negative!

# Доходы → положительные:
repo.upsert_history('rusal', 'IS', yr, 'revenue',            value)  # positive
repo.upsert_history('rusal', 'IS', yr, 'interest_income',    value)  # positive
repo.upsert_history('rusal', 'IS', yr, 'earnings_from_associates', value)  # positive!

# CF outflows → отрицательные:
repo.upsert_history('rusal', 'CF', yr, 'capex',             -value)  # negative
repo.upsert_history('rusal', 'CF', yr, 'cff_lt_debt_repayment', -value)
```

---

## 7. PRODUCTION_KPI — НОВАЯ ТАБЛИЦА

### 7.1 Что добавить в schema.py
```sql
CREATE TABLE IF NOT EXISTS production_kpi (
    company_id  TEXT NOT NULL,
    period_id   INTEGER NOT NULL REFERENCES periods(period_id),
    metric      TEXT NOT NULL,
    value       REAL NOT NULL,
    PRIMARY KEY (company_id, period_id, metric)
);
```

### 7.2 Ключевые метрики Rusal
| Метрика | Единица | Источник xlsb |
|---|---|---|
| production_al_kt | тыс. тонн | Raw Data_ |
| production_alumina_kt | тыс. тонн | Raw Data_ |
| production_bauxite_mt | млн тонн | Raw Data_ |
| sales_al_kt | тыс. тонн | Raw Data_ |
| sales_alumina_kt | тыс. тонн | Raw Data_ |
| capacity_utilization_pct | % | Annual Reports |
| avg_al_price_usd_t | USD/т | IS Revenue / sales_al_kt |
| total_unit_cost_usd_t | USD/т | Annual Reports |
| alumina_cost_per_t | USD/т | Annual Reports |
| power_cost_per_t | USD/т | Annual Reports |

### 7.3 2024 известные данные (из AR 2024)
```
production_al_kt = 3,859  (Claude Code извлёк из PDF)
```

---

## 8. КЛЮЧЕВЫЕ ДАННЫЕ ИЗ RUSAL IS 2024 (уже в БД)

```
Revenue:              $12,082M  (✅ конвертация OK)
COGS:                 ~$9,800M  (cogs_ratio ≈ 0.81)
EBIT:                 $368M
earnings_from_associates: $564M  (НОРНИКЕЛЬ — ключевая строка!)
NI:                   $803M
D&A:                  $512M
EBITDA:               $880M  (margin 7.3%)
```

**Критично для Rusal**: Норникель ($564M) > EBIT ($368M). 
Без корректного EWA associates — NI будет неверным.

---

## 9. EXCEL_LOADER.YAML — ТЕКУЩИЙ СТАТУС

Файл создан: `companies/rusal/configs/excel_loader.yaml`

**Нужно проверить/дополнить**:
1. Лист `Production_KPI` — должен маппиться в таблицу `production_kpi`
2. `scale_factor: 1_000_000` — для IS/BS/CF (млн → USD)
3. `non_scale_metrics` — production kt, unit costs USD/t НЕ умножаем на 1M
4. Лист `Macro_Factors` — russian_power_price, cpi_ru, ppi_ru

---

## 10. СЕССИОННЫЙ СТАРТ — КОМАНДА ДЛЯ CLAUDE CODE

```bash
cd "/Users/arturhusnutdinov/Documents/IT Development/Docker/stressTest_v2"

python3 << 'EOF'
import sys; sys.path.insert(0, '.')
from engine import ROOT, DB_PATH
assert str(ROOT).endswith('stressTest_v2'), f'СТОП ROOT={ROOT}'
assert 'v3' not in str(DB_PATH), f'СТОП DB={DB_PATH}'
print(f'ROOT: {ROOT}')
print(f'DB:   {DB_PATH}')

# Проверка US Steel не сломан
from engine.orchestrator import build_model
r = build_model('us_steel', run_preprocessor=False, run_model=True)
bs = max(r.model_result.bs_diffs.values())
cf = max(r.model_result.cf_diffs.values())
assert bs < 1 and cf < 1, f'US STEEL BROKEN! BS={bs} CF={cf}'
print(f'US Steel BS={bs:.6f} CF={cf:.6f} ✅')

# Проверка Rusal данных
from engine.database.repository import Repository
from pathlib import Path
with Repository(DB_PATH) as repo:
    for stmt in ['is','bs','cf']:
        r2 = repo.query(f"""
            SELECT COUNT(*) n, MIN(p.year) y0, MAX(p.year) y1
            FROM history_{stmt} h JOIN periods p ON h.period_id=p.period_id
            WHERE h.company_id='rusal'
        """)[0]
        print(f'Rusal {stmt.upper()}: {r2["n"]} rows, {r2["y0"]}-{r2["y1"]}')
    
    rev = repo.query("""
        SELECT h.value FROM history_is h JOIN periods p ON h.period_id=p.period_id
        WHERE h.company_id='rusal' AND h.metric='revenue' AND p.year=2024
    """)
    print(f'Rusal Revenue 2024: ${rev[0]["value"]/1e9:.2f}B (ожидается ~$12B)')
EOF
```

---

## 11. СЛЕДУЮЩИЙ КОНКРЕТНЫЙ ШАГ

**Задача Фазы 1**: Дополнить `rusal_data_export.xlsx` из xlsb прототипа.

```bash
# В Claude Code терминале:
python3 << 'SCRIPT'
# 1. Открыть xlsb прототип
# 2. Извлечь Production KPI (лист "Raw Data_")
# 3. Извлечь Debt schedule (листы "Loans and Borrowings", "Bonds")  
# 4. Извлечь Macro data (лист "Macro Data": power_price, CPI/PPI)
# 5. Извлечь Segments (выручка по сегментам Al/Al2O3/foil)
# 6. Записать в rusal_data_export.xlsx (новые листы)
# 7. Обновить excel_loader.yaml (маппинг новых листов)
# 8. Создать таблицу production_kpi в schema.py
# 9. Загрузить через ExcelLoader
# 10. Верифицировать: BS identity + production_kpi count > 0
SCRIPT
```

**Путь к xlsb**: найти через `find . -name "*.xlsb"` — должен быть в `companies/rusal/data/`

---

*Документ описывает полный контекст: готовый движок, пример US Steel, отличия IFRS/GAAP, текущий статус Rusal, и точный план следующих шагов. Все доработки — только через существующую инфраструктуру движка.*
