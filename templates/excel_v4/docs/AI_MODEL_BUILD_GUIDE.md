# Пошаговая инструкция: построение финансовой модели нового эмитента

**Версия:** 2.0 (8 октября 2026)
**Статус:** v4.3 SELF-CONTAINED — 0 литералов, ~1760 формул, BS=0, Errors=0/0/0
**Результат:** Один Excel-файл с 31 листом. Все данные внутри. Внешних файлов не нужно.

---

## Архитектура модели (один Excel файл)

```
model_{company}.xlsx
├── INPUT SHEETS (аналитик заполняет):
│   ├── 02_Hist         — IS/BS/CF история (3 года, 44+ строки)
│   │                     Все расчётные листы ссылаются на 02_Hist
│   │                     Other items = plug (Total - known) → refs
│   ├── Raw_IFRS        — Долговой портфель (20 инструментов + Other)
│   │                     + KeyRate forecast (3 года)
│   │                     _Debt_Schedule → формулы от Raw_IFRS
│   ├── 11_Segments     — Vol/Price/Rev по сегментам (3 сегмента)
│   │                     10_Revenue → refs на 11_Segments
│   ├── 01_Macro        — Макро-факторы (3 сценария × 6 факторов)
│   └── Control_Panel   — 47+ параметров модели
│
├── CALC SHEETS (формулы, 0 литералов):
│   ├── 10_Revenue      — Σ(Vol × Price) + Reconciliation (formula)
│   ├── 12_COGS         — Component/Ratio/PPI uplift (method switch)
│   ├── 13_SGA          — Revenue × ratio (from CP)
│   ├── 15_PPE          — Corkscrew: Gross → CapEx → Dep → Net
│   ├── 16_WC           — DSO/DIH/DPO → AR/INV/AP (formulas from 02_Hist)
│   ├── 17_Debt         — Funding waterfall + penalty rate + calibration
│   │                     History: ALL refs to 02_Hist (ST+LT, interest, ND)
│   │                     Instrument summary: refs to Raw_IFRS
│   │                     Calibration: formulas (ST share, maint, spread, tenor)
│   ├── 18_Lease        — IFRS 16 ROU + Liability
│   ├── 19_Tax          — IAS 12 + DTA/DTL refs to 02_Hist
│   ├── 20_BS           — BS with ABS() in TCL/TNCL (handles negative tax_pay)
│   │                     Other items: refs to 02_Hist plugs
│   │                     Totals: formulas in ALL columns (history + forecast)
│   ├── 21_PL           — IS with history refs to 02_Hist
│   │                     other_opex/impairment: residual formulas
│   ├── 23_CF           — Indirect method, CFF includes new_term
│   ├── 24_Equity       — RE corkscrew + buyback + covenant-gated dividends
│   ├── 30_Ratios       — 25+ коэффициентов
│   ├── 31_Score        — S&P 4-factor rating + EBITDA sign protection
│   ├── 32_Covenants    — 5 ковенантов
│   ├── 33_RevStress    — Reverse stress + Tornado
│   ├── 35_Valuation    — DCF + SOTP + Sensitivity (refs CP terminal_g/mult)
│   └── 40_Scen         — 5 analytical stress scenarios
│
├── CONTROL:
│   ├── 90_Checks       — 15 проверок + 5 history checks (Rev/COGS/SGA/PPE/BS)
│   └── Model_Output    — Сводный дашборд
│
└── TECHNICAL:
    ├── _Debt_Schedule   — Per-instrument (fill_data writes formulas)
    ├── 03_Assump        — EWA preprocessing
    └── Changelog
```

---

## Пошаговый процесс

### Шаг 1: Извлечение данных из МСФО

Аналитик парсит отчётность и готовит данные в стандартизованном формате.

#### 1.1 Income Statement
| Ключ | Описание | Знак |
|------|----------|------|
| revenue | Выручка | + |
| cogs | Себестоимость | - |
| gross_profit | Валовая прибыль | computed |
| sga | SGA расходы | - |
| total_da | Амортизация | - |
| ebitda | EBITDA | computed |
| ebit | EBIT | computed |
| interest_expense | Процентные расходы | - |
| other_financial | Прочие финансовые | +/- |
| other_operating_expenses | Прочие операционные | +/- |
| asset_impairment | Обесценение | - |
| ebt | Прибыль до налога | computed |
| tax_expense | Налог | - |
| net_income | Чистая прибыль | +/- |

#### 1.2 Balance Sheet
| Ключ | Описание |
|------|----------|
| cash | Денежные средства |
| accounts_receivable | Дебиторская задолженность |
| inventory | Запасы |
| total_ca / total_current_assets | Итого оборотные активы |
| ppe_net | Основные средства (нетто) |
| ppe_gross | ОС (валовая стоимость) |
| goodwill | Гудвилл |
| intangibles | НМА |
| dta | Отложенный налоговый актив |
| rou_asset | Активы права пользования |
| total_nca / total_non_current_assets | Итого внеоборотные |
| total_assets | Итого активы |
| accounts_payable | Кредиторская задолженность |
| short_term_debt | Краткосрочный долг |
| taxes_payable | Налоги к уплате (МОЖЕТ БЫТЬ ОТРИЦАТЕЛЬНЫМ) |
| lease_liab_current | Обязательства по аренде (кратк.) |
| total_cl / total_current_liabilities | Итого краткосрочные обяз. |
| long_term_debt | Долгосрочный долг |
| lease_liab_noncurrent | Обяз. по аренде (долг.) |
| provisions | Резервы |
| dtl | Отложенное налоговое обязательство |
| total_ncl / total_non_current_liabilities | Итого долгосрочные |
| total_liabilities | Итого обязательства |
| share_capital | Уставный капитал |
| apic | Добавочный капитал |
| retained_earnings | Нераспределённая прибыль |
| aoci | Прочий совокупный доход |
| total_equity | Итого собственный капитал |

**ВАЖНО:** Модель использует `ABS()` в формулах TCL/TNCL для обработки отрицательных значений (например, taxes_payable может быть отрицательным = налоговая переплата). Other items вычисляются как plug: `Total − Σ(known items)` и хранятся в 02_Hist.

#### 1.3 Cash Flow
| Ключ | Описание |
|------|----------|
| cfo_total / cfo | Операционный поток |
| cfi_total / cfi | Инвестиционный поток |
| capex | CapEx (отрицательный) |
| cff_total / cff | Финансовый поток |
| net_change | Чистое изменение ДС |

#### 1.4 Долговой портфель
Для каждого инструмента (до 20 + Other):
| Поле | Описание | Пример |
|------|----------|--------|
| name | Название | "Bond 2027 6.5%" |
| kind | Тип: BOND_BULLET / BOND_FLOAT / TERM_AMORT / RC | BOND_BULLET |
| currency | Валюта | USD, CNY, RUB |
| balance | Остаток (mln) | 1551 |
| rate | Ставка (для fixed) или спред (для floating) | 0.12 |
| maturity | Дата погашения (текст, год в последних 4 символах) | "14.05.2027" |

**Типы инструментов:**
- **BOND_BULLET** — облигация с погашением в дату maturity, фиксированная ставка
- **BOND_FLOAT** — облигация с плавающей ставкой (KeyRate + spread)
- **TERM_AMORT** — кредит с амортизацией
- **RC** — револьверная линия (плавающая ставка)

#### 1.5 Сегменты (операционные данные)
По каждому сегменту (до 3):
- Volume (kt) × 3 года
- Price ($/t) × 3 года
- Driver: макро-фактор (lme_aluminium, lme_nickel, brent...)

#### 1.6 KeyRate forecast
Прогноз ставки ЦБ на 3 года (для floating rate instruments):
```
2026: 0.14, 2027: 0.11, 2028: 0.09
```

---

### Шаг 2: Создание project.yaml

Конфигурация модели определяет: company name, отрасль, сегменты, COGS mode, debt params, covenants, scenarios.

Выбор параметров по отрасли:

| Отрасль | COGS mode | target ND/EBITDA | penalty_rate | Сегменты |
|---------|-----------|-------------------|-------------|----------|
| Metals | component | 3.0-4.0 | 0.20-0.24 | По металлам |
| Oil & Gas | component | 2.5-3.5 | 0.18-0.22 | По бассейнам |
| Telecom | ratio | 3.0-4.0 | 0.18-0.22 | По сервисам |
| Mining | component | 2.0-3.0 | 0.20-0.24 | По ресурсам |
| Retail | ratio | 3.5-4.5 | 0.16-0.20 | По форматам |
| Utilities | ratio | 4.0-5.0 | 0.16-0.20 | По типам генерации |

---

### Шаг 3: Сборка модели

```bash
cd stressTest_v2/templates/excel_v4

# КРИТИЧЕСКИ ВАЖНО: python3 -B (без bytecode cache)
python3 -B scripts/build_model.py --company {company}

# Одноразовая загрузка данных из source → модель
python3 -B scripts/fill_data.py --company {company} --model model/model_v4.xlsx

# Копия для Excel
cp model/model_v4.xlsx model/model_{company}.xlsx
```

**После fill_data модель самодостаточна.** Все данные внутри Excel:
- 02_Hist: IS/BS/CF + Other plugs
- Raw_IFRS: 20 инструментов + KeyRate
- 11_Segments: vol/price/rev
- 01_Macro: сценарии
- Control_Panel: параметры

---

### Шаг 4: Пересчёт в Excel

```applescript
tell application "Microsoft Excel"
    open "/path/to/model_{company}.xlsx"
    delay 6
    repeat 25 times
        calculate
    end repeat
    save workbook 1
end tell
```

---

### Шаг 5: Верификация

```bash
python3 -B scripts/verify_model.py model/model_{company}.xlsx
```

Что проверяет:
1. **15 тождеств** — BS=0, CF=0, PPE=0, Debt=0, Equity=0, ST+LT=DT, Interest, S&U...
2. **5 history checks** — Rev/COGS/SGA/PPE/BS vs 02_Hist
3. **Монотонность** — Revenue/EBITDA убывают по сценариям
4. **EBITDA protection** — отрицательная EBITDA → score=5, penalty rate
5. **Операционный рычаг** — Revenue drop → amplified EBITDA drop

Ожидаемый результат: `ALL BEHAVIORAL TESTS PASS`

---

### Шаг 6: Проверка в Excel

1. `90_Checks`: **ОШИБОК ВСЕГО = 0/0/0** для всех 3 прогнозных лет
2. **History checks**: Rev/COGS/SGA/PPE/BS = 02_Hist (для 3 исторических лет)
3. Переключить `Control_Panel!C5` = 1/2/3 (Base/Stress/Severe)
4. Cash = min_cash в каждом сценарии
5. Penalty debt > 0 в Stress/Severe при нарушении ковенантов
6. Revenue/EBITDA/Rating монотонно ухудшаются

---

## Ключевые паттерны (ОБЯЗАТЕЛЬНО)

| Паттерн | Правило |
|---------|---------|
| `python3 -B` | Перед КАЖДОЙ сборкой (или `rm -rf __pycache__`) |
| reg.json | Auto-saved after build_model (fill_data reads it) |
| Проценты | ВСЕ от OPENING balance (не avg) |
| Новый транш | % = 0 в году выдачи (со следующего) |
| Дивиденды | От прибыли ПРОШЛОГО года |
| CFF_base | Исключает RC и new_term |
| Gate | = rate, не access. ВСЕГДА финансирует. Breach → penalty_rate (24%) |
| penalty_limit | CP param: 0=unlimited, >0=потолок на год |
| LT формула | `MAX(0, close-(mandatory+RC))` — скобки обязательны |
| ST | Next year mandatory (IAS 1); last year = avg ST share |
| TCL/TNCL | `ABS()` для каждого item (handles negative tax_pay) |
| BS Other | Plug → 02_Hist → refs (не direct literals) |
| Revenue recon | Formula: `=02_Hist!revenue - Σ segments` |
| Labels | НЕ начинать с `=` (openpyxl трактует как формулу → Excel repair) |
| Revenue prices | `='01_Macro'` active row (не литералы) |
| Material COGS | `Vol × 1.93 × alumina_price` (не от выручки) |
| OLS β | fill_data computes → CP.rev_elasticity (method 2) |
| EBITDA ≤ 0 | Floor score 5, covenant breach, penalty rate |
| S&U gap | = rc_draw + new_term (includes term_out) |
| Tenor | SUMPRODUCT formula: `balance × (VALUE(RIGHT(maturity,4)) - year) / SUM(balance)` |

---

## Типичные проблемы

| Проблема | Причина | Решение |
|----------|---------|---------|
| Excel repair dialog | Label comment starts with `=` | Не начинать text с `=` |
| BS ≠ 0 | Negative tax_pay | ABS() in TCL/TNCL formulas |
| BS ≠ 0 | LT parentheses | `MAX(0, close-(mand+RC))` |
| Cash ≠ target | Interest from avg | ALL interest from OPENING |
| Cash ≠ target | Dividends from current NI | Dividends from PREV year |
| Scenarios don't work | Prices as literals | Prices = '01_Macro' active row |
| S&U ≠ 0 | term_out not in gap | S&U = rc_draw + new_term |
| __pycache__ stale | Old bytecode | `python3 -B` always |
| 02_Hist empty | fill_data writes here | Run fill_data after build_model |
| Literal in calc sheet | fill_data overwrites formula | Disable overwrite in fill_data |

---

## Checklist

- [ ] МСФО данные извлечены (IS/BS/CF × 3 года)
- [ ] Долговой портфель (20 инструментов + Other + KeyRate)
- [ ] Сегменты (vol/price × 3 года × 3 сегмента)
- [ ] project.yaml создан
- [ ] build_model.py: OK
- [ ] fill_data.py: OK
- [ ] **0 литералов в calc sheets** (count script)
- [ ] **Excel: ОШИБОК ВСЕГО = 0/0/0**
- [ ] **History checks: Rev/COGS/SGA/PPE/BS = 02_Hist**
- [ ] verify_model.py: ALL PASS
- [ ] Scenario 1 (Base): Cash = min_cash, Rating > D
- [ ] Scenario 3 (Severe): Cash = min_cash, penalty debt > 0
- [ ] Монотонность: Revenue↓ EBITDA↓ Rating↓ по сценариям
- [ ] **Модель самодостаточна** (не нужен external source file)

---

## Файлы проекта

| Файл | Строк | Назначение |
|------|-------|-----------|
| `scripts/build_model.py` | ~5800 | 31 лист, ~1760 формул, 0 литералов |
| `scripts/fill_data.py` | ~2700 | Одноразовый загрузчик → Raw_IFRS + 02_Hist |
| `scripts/verify_model.py` | ~350 | Block F: 3 сценария × identity + monotonicity |
| `scripts/styles.py` | ~160 | Цветовая схема |
| `reg.json` | ~300 keys | Row registry (auto-saved by build_model) |
| `docs/Model_Methodology.md` | | Полная методология v4.3 |
| `docs/AI_MODEL_BUILD_GUIDE.md` | | Этот документ |
