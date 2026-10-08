# Пошаговая инструкция для ИИ: построение финансовой модели нового эмитента

**Версия:** 1.0 (7 октября 2026)
**Контекст:** Аналитик положил отчётность компании в папку и указал отрасль.
**Результат:** Excel-модель на шаблоне v4 с 31 листом, 15 проверками = 0, 3 сценариями.

---

## 0. Входные данные от аналитика

### Обязательные
1. **МСФО отчётность** (PDF или Excel) — минимум 3 года (IS, BS, CF)
2. **Название компании** и **тикер**
3. **Отрасль** (metals, telecom, oil_gas, mining, retail, utilities, etc.)
4. **Валюта отчётности** (USD, RUB, EUR)

### Желательные
- Пояснения к отчётности (долговой портфель, основные средства, налоги)
- Операционные данные (объёмы, цены, сегменты)
- Макро-драйверы отрасли (commodity price, FX rate)

### Где лежат файлы
```
stressTest_v2/
├── companies/{company}/
│   ├── data/
│   │   ├── {company}_complete_v4.xlsx   # ← парсенная МСФО отчётность
│   │   ├── parsed/                      # промежуточные файлы парсера
│   │   ├── debt/                        # долговой портфель
│   │   ├── operational/                 # операционные данные (vol, price)
│   │   └── macro/                       # макро-факторы
│   └── configs/
│       ├── project.yaml                 # ← конфигурация модели (создаём)
│       └── stress_scenarios.yaml        # сценарии стресс-теста
├── templates/excel_v4/
│   ├── scripts/
│   │   ├── build_model.py      # генератор модели (~5500 строк)
│   │   ├── fill_data.py         # загрузка данных (~2700 строк)
│   │   ├── verify_model.py      # Block F верификация
│   │   └── styles.py            # стили
│   ├── model/                   # ← результат: model_{company}.xlsx
│   ├── docs/
│   │   ├── Model_Methodology.md
│   │   └── AI_MODEL_BUILD_GUIDE.md (этот файл)
│   └── reg.json                 # реестр строк (auto-saved by build_model)
└── data_mart_v2.db              # SQLite БД с агрегированными данными
```

### Подготовка данных для нового эмитента
1. Создать `companies/{company}/data/` — положить отчётность (PDF/Excel)
2. Парсить отчётность → `{company}_complete_v4.xlsx` (IS/BS/CF/Debt/Segments)
3. Создать `companies/{company}/configs/project.yaml` — конфигурация
4. fill_data.py загрузит данные из xlsx + yaml + БД

---

## Шаг 1: Извлечение данных из отчётности

### 1.1 Income Statement (IS)
Извлечь за 3 года (в валюте отчётности):
```yaml
revenue: [Y1, Y2, Y3]          # Выручка
cogs: [Y1, Y2, Y3]             # Себестоимость (отрицательная)
sga: [Y1, Y2, Y3]              # Коммерческие и административные расходы (отр.)
da: [Y1, Y2, Y3]               # Амортизация (если отдельно)
interest_expense: [Y1, Y2, Y3] # Процентные расходы (отр.)
interest_income: [Y1, Y2, Y3]  # Процентные доходы
other_income: [Y1, Y2, Y3]     # Прочие доходы/расходы
tax: [Y1, Y2, Y3]              # Налог на прибыль (отр.)
net_income: [Y1, Y2, Y3]       # Чистая прибыль
```

### 1.2 Balance Sheet (BS)
```yaml
# ASSETS
cash: [Y1, Y2, Y3]
accounts_receivable: [Y1, Y2, Y3]
inventory: [Y1, Y2, Y3]
other_current_assets: [Y1, Y2, Y3]
total_current_assets: [Y1, Y2, Y3]
ppe_net: [Y1, Y2, Y3]
ppe_gross: [Y1, Y2, Y3]          # если есть
accumulated_depreciation: [Y1, Y2, Y3]  # если есть
goodwill: [Y1, Y2, Y3]
intangibles: [Y1, Y2, Y3]
investments: [Y1, Y2, Y3]        # ассоциированные компании
dta: [Y1, Y2, Y3]                # отложенный налоговый актив
other_noncurrent_assets: [Y1, Y2, Y3]
total_assets: [Y1, Y2, Y3]

# LIABILITIES
accounts_payable: [Y1, Y2, Y3]
short_term_debt: [Y1, Y2, Y3]    # краткосрочные займы
current_portion_ltd: [Y1, Y2, Y3]
tax_payable: [Y1, Y2, Y3]
other_current_liabilities: [Y1, Y2, Y3]
total_current_liabilities: [Y1, Y2, Y3]
long_term_debt: [Y1, Y2, Y3]
lease_liability: [Y1, Y2, Y3]    # если раскрыто отдельно
dtl: [Y1, Y2, Y3]                # отложенное налоговое обязательство
provisions: [Y1, Y2, Y3]
other_noncurrent_liabilities: [Y1, Y2, Y3]
total_liabilities: [Y1, Y2, Y3]

# EQUITY
share_capital: [Y1, Y2, Y3]
retained_earnings: [Y1, Y2, Y3]
aoci: [Y1, Y2, Y3]               # прочий совокупный доход
nci: [Y1, Y2, Y3]                # неконтрол. доля
total_equity: [Y1, Y2, Y3]
```

### 1.3 Cash Flow (CF)
```yaml
cfo: [Y1, Y2, Y3]                # Операционный
cfi: [Y1, Y2, Y3]                # Инвестиционный
capex: [Y1, Y2, Y3]              # CapEx (отр.)
cff: [Y1, Y2, Y3]                # Финансовый
dividends_paid: [Y1, Y2, Y3]     # Дивиденды (отр.)
```

### 1.4 Долговой портфель (из пояснений)
```yaml
debt_instruments:
  - name: "Bond 2027 6.5%"
    type: BOND                    # BOND, TERM_LOAN, CREDIT_LINE
    currency: USD
    outstanding: 1500             # текущий остаток
    rate: 0.065                   # купон / ставка
    rate_type: fixed              # fixed / floating
    maturity_year: 2027
  - name: "Syndicated Loan 2028"
    type: TERM_LOAN
    currency: USD
    outstanding: 2000
    rate: 0.085
    rate_type: floating           # KeyRate + spread
    spread: 0.025
    maturity_year: 2028
```

### 1.5 Операционные данные (если есть)
```yaml
segments:
  - name: "Primary Aluminium"
    driver: lme_aluminium
    volume_history: [3800, 3900, 3950]   # kt
    price_history: [2200, 2100, 2450]    # USD/t
  - name: "Alumina"
    driver: lme_alumina
    volume_history: [7500, 7600, 7700]
    price_history: [350, 380, 540]
```

---

## Шаг 2: Создание project.yaml

На основе извлечённых данных создать конфигурацию:

```yaml
company:
  name: "Company Name"
  ticker: "TICKER"
  currency: USD
  industry: metals               # → определяет macro factors
  hist_years: [2023, 2024, 2025]
  fc_years: [2026, 2027, 2028]

# Макро-факторы (зависят от отрасли)
macro_factors:
  - lme_aluminium                # metals
  - lme_alumina                  # metals
  - usd_rub                      # RU company
  - brent                        # energy
  - cpi_ru                       # labour
  - ppi_ru                       # other costs

# Сегменты выручки
segments:
  - name: "Primary Aluminium"
    driver: lme_aluminium
    volume_history: [3800, 3900, 3950]
    price_history: [2200, 2100, 2450]
    ev_rev_multiple: 0.8
  - name: "Alumina"
    driver: lme_alumina
    volume_history: [7500, 7600, 7700]
    price_history: [350, 380, 540]
    ev_rev_multiple: 0.5

# Себестоимость
cogs_mode: component             # component или ratio
cogs_components:
  material: 0.37                 # доля от total COGS
  energy: 0.27
  labour: 0.12
  other: 0.24

# Долг
debt:
  min_cash: 500
  rc_limit: 2500
  rc_rate: 0.14
  commit_fee: 0.005
  target_nd_ebitda: 3.5
  penalty_rate: 0.24
  refi_pct_bonds: 1.0
  refi_pct_bank: 1.0

# Ковенанты
covenants:
  nd_ebitda_max: 4.5
  icr_min: 1.5

# Рейтинг
rating:
  industry_adj: 0
  size_adj: 0

# Оценка
valuation:
  risk_free: 0.18
  erp: 0.06
  beta: 1.2
  terminal_growth: 0.02

# Сценарии (3 × macro_factors)
scenarios:
  base:
    lme_aluminium: [2450, 2500, 2550]
    lme_alumina: [540, 550, 560]
    usd_rub: [95, 97, 99]
  stress:
    lme_aluminium: [2000, 2050, 2100]
    lme_alumina: [400, 410, 420]
    usd_rub: [110, 112, 115]
  severe:
    lme_aluminium: [1700, 1750, 1800]
    lme_alumina: [300, 310, 320]
    usd_rub: [130, 135, 140]
```

### Выбор параметров по отрасли

| Отрасль | Ключевой driver | COGS mode | target ND/EBITDA | penalty_rate |
|---------|-----------------|-----------|-------------------|-------------|
| Metals | LME commodity | component | 3.0-4.0 | 0.20-0.24 |
| Oil & Gas | Brent | component | 2.5-3.5 | 0.18-0.22 |
| Telecom | Revenue/ARPU | ratio | 3.0-4.0 | 0.18-0.22 |
| Mining | Commodity price | component | 2.0-3.0 | 0.20-0.24 |
| Retail | CPI, GDP | ratio | 3.5-4.5 | 0.16-0.20 |
| Utilities | Tariff, volumes | ratio | 4.0-5.0 | 0.16-0.20 |

---

## Шаг 3: Заполнение {company}_complete_v4.xlsx

Создать Excel файл `companies/{company}/data/{company}_complete_v4.xlsx` с листами:
1. **IS** — P&L за 3+ лет (revenue, cogs, sga, da, interest, tax, ni)
2. **BS** — Баланс за 3+ лет (все статьи: cash, ar, inv, ppe, debt, equity...)
3. **CF** — ОДДС за 3+ лет (cfo, cfi, cff, capex)
4. **Debt** — Список инструментов (name, type, currency, outstanding, rate, maturity)
5. **Segments** — Операционные данные (volume, price per segment)
6. **Macro** — Исторические макро-факторы (LME, FX, CPI, PPI)

Формат: строки = статьи, столбцы = годы. Знаки: расход = отрицательный.
Ключи статей: стандартизованные (revenue, cogs, sga, accounts_receivable, inventory, etc.)

### Маппинг ключей IS
```
revenue, cogs, gross_profit, sga, total_da, ebitda, ebit,
interest_expense, other_financial, other_operating_expenses,
asset_impairment, ebt, tax_expense, net_income
```

### Маппинг ключей BS
```
cash, accounts_receivable, inventory, other_ca, total_ca,
ppe_net, ppe_gross, accumulated_depreciation, rou_asset,
goodwill, intangibles, dta, other_nca, total_assets,
accounts_payable, short_term_debt, taxes_payable, other_cl,
long_term_debt, lease_liab_current, lease_liab_noncurrent,
provisions, dtl, other_ncl, total_liabilities,
share_capital, apic, retained_earnings, aoci, total_equity
```

---

## Шаг 4: Сборка модели

```bash
cd stressTest_v2/templates/excel_v4

# Очистить кеш (КРИТИЧЕСКИ ВАЖНО!)
rm -rf scripts/__pycache__

# 1. Генерация формул
python3 -B scripts/build_model.py --company {company_name}

# 2. Загрузка данных
python3 -B scripts/fill_data.py --company {company_name} --model model/model_v4.xlsx

# 3. Копировать для Excel
cp model/model_v4.xlsx model/model_{company_name}.xlsx
```

---

## Шаг 5: Пересчёт в Excel

```applescript
tell application "Microsoft Excel"
    open "/path/to/model_{company}.xlsx"
    delay 4
    repeat 25 times
        calculate
    end repeat
    save workbook 1
end tell
```

---

## Шаг 6: Верификация

```bash
python3 -B scripts/verify_model.py model/model_{company}.xlsx
```

### Что проверяет verify_model.py:
1. **Тождества** — BS=0, CF=0, PPE=0, Debt=0, Equity=0, ST+LT=DT, Interest decomposition
2. **Монотонность** — Revenue и EBITDA убывают по сценариям
3. **EBITDA protection** — отрицательная EBITDA → score=5, penalty rate
4. **Операционный рычаг** — Revenue drop → amplified EBITDA drop

### Ожидаемый результат:
```
ALL BEHAVIORAL TESTS PASS
```

---

## Шаг 7: Ручная проверка в Excel

1. Открыть файл → лист `90_Checks`
2. **Все ячейки F-H строки "ОШИБОК ВСЕГО" = 0**
3. Переключить сценарий (Control_Panel!C5 = 1/2/3)
4. Убедиться: Cash = min_cash во всех сценариях
5. В Severe: penalty debt > 0 (привлечение по штрафной ставке)

---

## Типичные проблемы и решения

### Проблема: BS ≠ 0
| Причина | Решение |
|---------|---------|
| ST + LT ≠ DT.close | Проверить скобки в LT: `MAX(0, close-(mand+RC))` |
| Lease загружен отдельно, но уже в PPE/Loans | Пропустить lease если не раскрыт отдельно в МСФО |
| Other CL/CA не балансирует | fill_data: Other = Total − Σ(known items) |

### Проблема: Cash ≠ min_cash
| Причина | Решение |
|---------|---------|
| Проценты от avg вместо opening | ВСЕ проценты от OPENING balance |
| Новый транш: % в году выдачи | interest = 0 в году выдачи |
| Дивиденды от текущей прибыли | Дивиденды от ПРОШЛОГО года NI |
| fill_data перезаписал формулу | Проверить: fill_data НЕ перезаписывает forecast prices, SGA total |

### Проблема: Сценарии не работают
| Причина | Решение |
|---------|---------|
| Цены = литералы | Revenue prices = '01_Macro' active row (формула, не число) |
| COGS от выручки | Material = Vol × коэфф × commodity_price |
| fill_data перезаписал | fill_data пропускает forecast prices |

### Проблема: __pycache__ stale
```bash
rm -rf scripts/__pycache__
# или всегда использовать:
python3 -B scripts/build_model.py ...
```

---

## Checklist для новой компании

- [ ] МСФО данные извлечены (IS/BS/CF × 3 года)
- [ ] Долговой портфель (инструменты, ставки, сроки)
- [ ] project.yaml создан с правильной отраслью
- [ ] {company}_complete_v4.xlsx заполнен (IS/BS/CF/Debt/Segments)
- [ ] build_model.py отработал без ошибок
- [ ] fill_data.py отработал без ошибок
- [ ] Excel пересчитан (25 iterations)
- [ ] verify_model.py: ALL PASS
- [ ] 90_Checks: ОШИБОК ВСЕГО = 0/0/0
- [ ] Сценарий Base: Cash = min_cash
- [ ] Сценарий Severe: Cash = min_cash, penalty debt > 0
- [ ] Revenue монотонно убывает по сценариям
- [ ] EBITDA монотонно убывает по сценариям
- [ ] Рейтинг монотонно ухудшается по сценариям

---

## Адаптация под отрасль

### Metals (Rusal, Nornickel)
- component COGS (material/energy/labour/other)
- LME commodity prices → revenue
- Operating leverage 2-4x
- FX debt revaluation

### Oil & Gas
- Brent × volume → revenue
- Transportation costs = fixed
- Royalties = % of revenue
- Depletion вместо depreciation

### Telecom
- ARPU × subscribers → revenue
- Churn model
- Capex = maintenance + network expansion
- COGS ratio mode (stable margin)

### Retail
- Store count × revenue per store
- Same-store growth + new stores
- WC: low DSO, high DPO (suppliers credit)
- Seasonal: adjust WC days

### Utilities
- Tariff × volume → revenue
- Regulated tariff growth (CPI-linked)
- High CapEx, long useful life (30-40 years)
- Stable EBITDA margin

---

## Файлы проекта

| Файл | Назначение |
|------|-----------|
| `scripts/build_model.py` | ~5300 строк, генерирует 31 лист с ~1200 формулами |
| `scripts/fill_data.py` | ~2500 строк, загрузка данных + discover_cp_rows |
| `scripts/verify_model.py` | ~330 строк, Block F behavioral tests |
| `scripts/styles.py` | Цветовая схема |
| `reg.json` | ~200 ключей, row registry |
| `docs/Model_Methodology.md` | Полная методология |
| `docs/AI_MODEL_BUILD_GUIDE.md` | Этот документ |
