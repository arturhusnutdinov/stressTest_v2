# Спецификация: Excel-шаблон и загрузчик v2.0
**stressTest v2 · Апрель 2026 · Статус: К реализации**

---

## 1. Цель и контекст

### Задача
Создать универсальный Excel-шаблон и загрузчик для сбора исторических данных любой компании с последующей загрузкой в `data_mart_v2.db`. Шаблон должен обеспечивать консистентность исторических данных с прогнозными формами движка.

### Тест приёмки
Round-trip на US Steel:
1. Экспорт из `data_mart_v2.db` → `us_steel_template.xlsx`
2. Загрузка из xlsx обратно в чистую БД
3. Прогон движка: BS=0, CF=0, Stress pass
4. Чекап: 0 метрик потеряно, 0 алиасов не разрешено, 0 знаков перевёрнуто

### Принципы
- **Универсальность**: один шаблон для любой компании (GAAP/IFRS, metals/steel/other)
- **Алиасы**: аналитик пишет как удобно → загрузчик приводит к каноническому имени
- **Полнота**: шаблон покрывает все 117 атрибутов `YearState` + Notes
- **Трассируемость**: каждое поле в Excel → таблица БД → атрибут движка
- **Идемпотентность**: повторная загрузка не создаёт дублей

---

## 2. Структура шаблона

### 2.1 Листы шаблона (32 листа)

```
МЕТАДАННЫЕ
  meta                   — версия, компания, валюта, стандарт учёта, периоды

ОСНОВНЫЕ ФОРМЫ (заполняет аналитик)
  history_is             — Income Statement, все строки IS
  history_bs             — Balance Sheet, все строки BS  
  history_cf             — Cash Flow Statement, все строки CF

SCHEDULES (детализация к основным формам)
  schedule_ppe           — PPE corkscrew: gross/accum/dep/additions/disposals
  schedule_leases        — IFRS 16: ROU assets, lease liabilities, payments
  schedule_tax           — DTA/DTL corkscrew, tax rate reconciliation
  schedule_wc            — WC corkscrew: AR/Inv/AP opening-closing-delta
  schedule_interest      — Interest corkscrew: accrued/paid/payable
  schedule_equity        — Equity corkscrew: RE/APIC/OCI/NCI/dividends

ДОЛГ (детализация)
  debt_instruments       — Каждый инструмент отдельной строкой
  debt_cashflows         — График платежей principal/interest по инструментам
  debt_covenants         — Финансовые ковенанты по кредитным соглашениям
  debt_maturity_ladder   — Ladder погашений: год × тип инструмента

ОПЕРАЦИОННЫЕ ДАННЫЕ
  segments_financial     — P&L по сегментам (revenue/COGS/EBITDA/EBIT)
  segments_operational   — KPI в натуральных единицах (kt, $/t, %)
  macro_factors          — Макро-факторы история (LME, FX, commodities)
  macro_forecasts        — Прогноз макро по сценариям
  production_kpi         — Производственные KPI (только для компаний с production)

СЛОВАРИ (не трогать руками)
  dict_metrics           — Канонические метрики + алиасы + описания
  dict_debt_types        — Типы долговых инструментов и параметры
  dict_segments          — Типы сегментов компании
  dict_units             — Единицы измерения
  dict_sign_convention   — Правила знаков по стандарту учёта

СЛУЖЕБНЫЕ (заполняются автоматически или загрузчиком)
  balancing_adj          — Балансирующие поправки (auto)
  data_quality_report    — Отчёт о качестве данных (auto после загрузки)
  loading_log            — Лог загрузки: что попало куда, алиасы resolved
```

---

## 3. Канонические формы (history_is/bs/cf)

### 3.1 Формат ячеек

```
Строка 1:  заголовок листа + инструкция
Строка 2:  "metric" | 2010 | 2011 | ... | 2024 | 2025
Строки 3+: <metric_name> | <value> | <value> | ...
```

**Правила:**
- Первый столбец = canonical metric name (или алиас из dict_metrics)
- Значения в единицах, указанных в `meta.base_unit` (mUSD по умолчанию)
- Знаки: расходы/liabilities = отрицательные (единая конвенция)
- Пустая ячейка = данных нет (NaN), не 0
- Нули хранить явно как 0

### 3.2 history_is — полный список метрик

```yaml
# IS — Income Statement (сверху вниз по P&L)

# Выручка
revenue:              "Выручка (Revenue / Net Sales)"          required: true
revenue_segment_*:    "Выручка по сегменту (через *)"          required: false

# Себестоимость и валовая прибыль
cogs:                 "Себестоимость (Cost of Sales / COGS)"   required: true
gross_profit:         "Валовая прибыль"                        calculated: revenue + cogs

# Операционные расходы
distribution_expenses: "Коммерческие расходы"                  required: true  # Rusal!
sga:                  "G&A / Administrative expenses"           required: true
rnd:                  "R&D"                                     required: false
other_operating:      "Прочие операционные расходы (нетто)"    required: false
asset_impairment:     "Обесценение активов"                     required: true  # volatile!
credit_losses:        "Ожидаемые кредитные убытки"             required: false

# D&A (хранить компоненты + суммарное)
dep_ppe:              "Амортизация ОС (owned assets)"           required: true
dep_rou_finance:      "Амортизация ROU finance lease"           required: false  # IFRS 16
dep_rou_operating:    "Амортизация ROU operating lease"         required: false  # IFRS 16
amort_intangibles:    "Амортизация НМА"                         required: true
total_da:             "D&A суммарно"                            calculated: dep_ppe + dep_rou + amort

# Результат операционной деятельности
ebit:                 "EBIT (операционная прибыль)"             calculated: gross_profit - opex - da
ebitda_standard:      "EBITDA = EBIT + D&A"                    calculated: ebit + total_da
ebitda_adjusted:      "Adjusted EBITDA (с non-cash items)"     required: false  # если компания раскрывает

# Ниже EBIT
interest_income:      "Процентные доходы"                       required: true
interest_expense:     "Процентные расходы"                      required: true
lease_interest:       "Проценты по аренде (IFRS 16)"           required: false
earnings_from_investees: "Доля в прибыли ассоциатов"           required: true  # Rusal: Норникель
fx_gain_loss:         "Курсовые разницы"                        required: false
other_non_operating:  "Прочие доходы/расходы"                  required: false
ebt:                  "Прибыль до налогов"                      calculated: ebit + below_ebit

# Налоги
current_tax:          "Текущий налог на прибыль"               required: true
deferred_tax_expense: "Изменение отложенного налога"           required: true

# Итоговые строки
tax_expense:          "Налог суммарно"                          calculated: current + deferred
net_income:           "Чистая прибыль"                         required: true
minority_interest:    "Доля меньшинства (NCI)"                 required: false
net_income_attributable: "ЧП, атрибутируемая акционерам"      calculated

# EPS
eps_basic:            "EPS базовый"                             required: false
eps_diluted:          "EPS разводнённый"                        required: false
shares_basic:         "Акции в обращении (basic), млн"         required: false
shares_diluted:       "Акции разводнённые, млн"                required: false
```

### 3.3 history_bs — полный список метрик

```yaml
# BS — Balance Sheet

# Оборотные активы (Current Assets)
cash:                       "Денежные средства и эквиваленты"  required: true
restricted_cash:            "Ограниченные ден.средства"         required: false
short_term_investments:     "Краткосрочные инвестиции"          required: false
accounts_receivable:        "Торговая дебиторка (нетто)"        required: true
inventory:                  "Запасы"                             required: true
prepaid_expenses:           "Авансы выданные"                   required: false
current_tax_receivable:     "НДС и прочие налоги к возврату"    required: false
other_ca:                   "Прочие оборотные активы"            required: false
total_ca:                   "Итого оборотные активы"             calculated

# Внеоборотные активы (Non-Current Assets)
ppe_gross:                  "ОС по первоначальной стоимости"    required: true  # из Notes!
ppe_accum_dep:              "Накопленная амортизация ОС"        required: true  # из Notes!
ppe_net:                    "ОС балансовая стоимость"           calculated: gross + accum
rou_asset_finance:          "ROU актив (finance lease)"         required: false  # IFRS 16
rou_asset_operating:        "ROU актив (operating lease)"       required: false  # IFRS 16
goodwill:                   "Гудвилл"                           required: false
intangibles:                "НМА (нетто)"                       required: false
investments_associates:     "Инвестиции в ассоциатов"           required: true  # Rusal: Норникель
investments_jv:             "Инвестиции в СП"                   required: false
long_term_investments:      "Долгосрочные финансовые инвестиции" required: false
dta:                        "Отложенный налоговый актив (DTA)"  required: true
other_nca:                  "Прочие внеоборотные активы"        required: false
total_nca:                  "Итого внеоборотные активы"         calculated
total_assets:               "ИТОГО АКТИВЫ"                      required: true  # BS check!

# Текущие обязательства (Current Liabilities)
short_term_debt:            "Краткосрочный долг + тек.часть ДСД" required: true
accounts_payable:           "Торговая кредиторка"               required: true
accrued_liabilities:        "Начисленные обязательства"         required: false
deferred_revenue:           "Отложенная выручка"                required: false
taxes_payable:              "Налог к уплате"                    required: false
lease_liab_current:         "Обязательство по аренде (тек.)"    required: false  # IFRS 16
customer_advances:          "Авансы полученные"                  required: false
other_cl:                   "Прочие текущие обязательства"       required: false
total_cl:                   "Итого текущие обязательства"        calculated

# Долгосрочные обязательства (Non-Current Liabilities)
long_term_debt:             "Долгосрочный долг"                 required: true
lease_liab_noncurrent:      "Обязательство по аренде (долг.)"   required: false  # IFRS 16
dtl:                        "Отложенное налоговое обязательство" required: true
employee_benefits:          "Обязательства по вознаграждениям"  required: false
provisions:                 "Резервы"                            required: false
other_ncl:                  "Прочие долгосрочные обязательства"  required: false
total_ncl:                  "Итого долгосрочные обязательства"   calculated
total_liabilities:          "ИТОГО ОБЯЗАТЕЛЬСТВА"               required: true  # BS check!

# Капитал (Equity)
share_capital:              "Уставный капитал"                  required: false
apic:                       "Добавочный оплаченный капитал"     required: false
retained_earnings:          "Нераспределённая прибыль"          required: true
treasury_stock:             "Казначейские акции"                required: false
aoci:                       "Прочий совокупный доход (OCI)"     required: false
minority_interest_bs:       "Доля меньшинства в капитале"       required: false
total_equity:               "ИТОГО КАПИТАЛ"                     required: true  # BS check!
```

### 3.4 history_cf — полный список метрик

```yaml
# CF — Cash Flow Statement (IFRS indirect method)

# CFO — Операционная деятельность
# Начало моста
net_income:                 "Чистая прибыль (начало CFO)"       required: true

# Non-cash add-backs
dep_ppe_cfo:                "Амортизация ОС (add-back)"         required: true
dep_rou_cfo:                "Амортизация ROU (add-back)"        required: false
amort_intangibles_cfo:      "Амортизация НМА (add-back)"        required: false
impairment_cfo:             "Обесценение (add-back)"            required: false
share_of_associates_cfo:    "Доля ассоциатов (reversal)"        required: false  # Rusal!
fx_loss_cfo:                "Курсовые убытки (add-back)"        required: false
gain_loss_disposal_cfo:     "Убыток/прибыль от выбытия"         required: false
deferred_tax_cfo:           "Изменение DTA/DTL"                 required: true
other_noncash_cfo:          "Прочие неденежные корректировки"   required: false

# WC движение
wc_ar_delta:                "Изменение дебиторки"               required: false
wc_inventory_delta:         "Изменение запасов"                 required: false
wc_ap_delta:                "Изменение кредиторки"              required: false
wc_other_delta:             "Изменение прочего WC"              required: false
wc_delta:                   "WC изменение суммарно"             required: true

# IFRS-специфичные выплаты (классифицируются в CFO по IFRS)
interest_paid:              "Проценты уплаченные"               required: true  # IFRS в CFO
interest_received:          "Проценты полученные"               required: false
tax_paid:                   "Налог уплаченный"                  required: true
dividends_received_cfo:     "Дивиденды полученные (IFRS → CFO)" required: false

cfo_total:                  "ИТОГО CFO"                         required: true

# CFI — Инвестиционная деятельность
capex:                      "Капитальные затраты (outflow)"     required: true
capex_intangibles:          "CapEx на НМА"                      required: false
proceeds_ppe:               "Выручка от продажи ОС"             required: false
acquisitions:               "Приобретения бизнеса"              required: false
disposals:                  "Выбытие бизнеса"                   required: false
investments_made:           "Инвестиции (loans/securities out)" required: false
investments_returned:       "Возврат инвестиций"                required: false
dividends_received_cfi:     "Дивиденды от ассоциатов (→ CFI)"  required: false  # Rusal!

cfi_total:                  "ИТОГО CFI"                         required: true

# CFF — Финансовая деятельность
debt_proceeds:              "Привлечение долга"                 required: false
debt_repayments:            "Погашение долга"                   required: false
fin_lease_principal:        "Погашение обязательств по аренде"  required: false  # IFRS 16
dividends_paid:             "Дивиденды выплаченные"             required: false
share_issuance:             "Выпуск акций"                      required: false
share_buyback:              "Выкуп акций"                       required: false
other_cff:                  "Прочие CFF"                        required: false

cff_total:                  "ИТОГО CFF"                         required: true

# Мост к кассе
fx_effect_on_cash:          "Курсовой эффект на денежные"       required: false
net_change_cash:            "Изменение денежных средств"        calculated
cash_beginning:             "Денежные на начало периода"        required: false
cash_ending:                "Денежные на конец периода"         check: = BS.cash
```

---

## 4. Долговой блок — детализация

### 4.1 debt_instruments — структура

```
Столбцы:
instrument_id         — уникальный ID (SNAKE_CASE, без пробелов)
instrument_name       — читаемое название
instrument_type       — canonical type (см. 4.2)
sub_type              — уточнение типа (term_a, term_b, revolver_rbl, etc.)
currency              — ISO 4217 (USD, EUR, CNY, RUB, GBP...)
opening_balance       — остаток на дату base_year_end ($M)
committed_amount      — лимит для линий (revolvers, RCF)
drawn_amount          — выбранная сумма для линий
maturity_date         — дата погашения (YYYY-MM-DD)
rate_type             — fixed / floating / zero
interest_rate         — ставка (decimal: 0.065 = 6.5%)
reference_rate        — SOFR / LIBOR / EURIBOR / CBR / LPR1Y / etc.
spread                — спред над reference rate (decimal)
payment_schedule      — bullet / equal_principal / annuity / custom / revolving
amort_start_date      — начало амортизации
amort_end_date        — конец амортизации
callable_flag         — 0/1
call_date             — дата первого call
put_flag              — 0/1
secured_flag          — 0/1
collateral_desc       — описание обеспечения
covenant_group_id     — ссылка на группу ковенантов (→ debt_covenants)
priority_rank         — старшинство (1=senior secured, 2=senior, 3=sub)
issuer                — SPV или сама компания
governing_law         — English / Russian / NY / etc.
isin                  — ISIN если облигация
listing               — биржа если листингованная
notes                 — комментарии аналитика
```

### 4.2 Канонические типы инструментов

```yaml
instrument_types:

  # Банковский долг
  revolver:
    description: "Возобновляемая кредитная линия (RCF/RBL)"
    payment_schedule: revolving
    rate_types: [floating]
    models_as: revolving_credit
    key_params: [committed_amount, drawn_amount, maturity_date, spread]

  term_loan_a:
    description: "Амортизирующий срочный кредит (TLA)"
    payment_schedule: [equal_principal, annuity, custom]
    rate_types: [floating, fixed]
    models_as: amortizing_debt
    key_params: [opening_balance, amort_schedule, maturity_date, spread]

  term_loan_b:
    description: "Bullet-погашение с PIK или cash (TLB)"
    payment_schedule: bullet
    rate_types: [floating, fixed]
    models_as: bullet_debt

  bridge_loan:
    description: "Бридж-кредит (временное финансирование)"
    models_as: bullet_debt
    note: "Обычно рефинансируется → моделировать с refi_flag=true"

  # Рынки капитала
  bond:
    description: "Корпоративная облигация (bullet)"
    payment_schedule: bullet
    rate_types: [fixed]
    models_as: bullet_debt
    key_params: [opening_balance, interest_rate, maturity_date, isin]

  bond_floating:
    description: "Облигация с плавающим купоном (FRN)"
    payment_schedule: bullet
    rate_types: [floating]
    models_as: bullet_debt

  bond_convertible:
    description: "Конвертируемая облигация"
    models_as: bullet_debt
    note: "Учитывать equity dilution при конверсии"

  # Лизинг (IFRS 16)
  finance_lease:
    description: "Финансовая аренда (IFRS 16)"
    payment_schedule: [equal_principal, annuity]
    rate_types: [fixed]
    models_as: finance_lease_ifrs16
    cfo_treatment: principal→CFF, interest→CFO

  operating_lease:
    description: "Операционная аренда (IFRS 16)"
    models_as: operating_lease_ifrs16
    note: "ROU asset + liability, платежи в CFO"

  # Специальные
  vendor_finance:
    description: "Вендорное финансирование / supplier credit"
    models_as: amortizing_debt

  shareholder_loan:
    description: "Займ акционера"
    models_as: bullet_debt
    note: "Учесть субординацию"

  export_credit:
    description: "Экспортное кредитование (ECA-covered)"
    models_as: amortizing_debt
```

### 4.3 debt_cashflows — график платежей

```
Назначение: детальный график будущих платежей по каждому инструменту.
Нужен для: точного расчёта интереса, STD/LTD split, ковенантного теста.

Столбцы:
instrument_id     — ссылка на debt_instruments
period_date       — дата платежа (YYYY-MM-DD или YYYY-Qn или YYYY)
period_type       — annual / quarterly / monthly / bullet
cashflow_type     — principal / interest / fee / all-in
amount            — сумма ($M, положительная = outflow)
currency          — ISO 4217
fx_rate_assumed   — курс конвертации (если не USD)
amount_usd        — сумма в USD $M
cumulative_principal — нарастающим итогом
remaining_balance    — остаток после платежа
notes

Правила заполнения:
- Для bullet: одна строка с principal = opening_balance в maturity_date
- Для amortizing: строка на каждый период (annual/quarterly)
- Для revolving: не заполнять (моделируется отдельно через optimizer)
- Interest: опционально (загрузчик считает сам из rate × balance)
```

### 4.4 debt_covenants — ковенанты

```
Столбцы:
covenant_group_id     — группа (один кредитный договор = одна группа)
covenant_name         — имя ковенанта
covenant_type         — financial / information / negative_pledge / other
metric                — canonical метрика (nd_ebitda, icr_ebitda, etc.)
test_direction        — max / min
threshold             — числовой лимит
test_frequency        — quarterly / semi-annual / annual
waiver_history        — были ли waiver (Y/N + дата)
cure_period_days      — срок на исправление
cross_default_flag    — 0/1 (крест-дефолт с другими)
applicable_instruments — список instrument_id через запятую
notes
```

---

## 5. Словарь алиасов (dict_metrics)

### 5.1 Структура

```
Столбцы:
category              — IS / BS / CF / KPI / MACRO
statement_type        — income_statement / balance_sheet / cash_flow / operational
canonical_metric      — каноническое имя (= имя в БД и движке)
description_ru        — описание на русском
description_en        — описание на английском
accepted_aliases      — через ; список принимаемых алиасов
sign_convention_gaap  — +1 (положительное = доход/актив) или -1
sign_convention_ifrs  — аналогично
required_for_model    — yes / no / conditional
calculated_from       — формула если расчётное
used_in_engine        — имя атрибута YearState
```

### 5.2 Ключевые алиасы (примеры)

```yaml
# IS алиасы
revenue:
  aliases: [net_sales, revenues, total_revenue, net_revenue, sales,
            total_revenues, выручка, нетто_продажи]

cogs:
  aliases: [cost_of_sales, cost_of_revenue, cost_of_goods_sold,
            cost_of_revenue_total, себестоимость, стоимость_продаж]

sga:
  aliases: [sg_and_a, selling_general_administrative, administrative_expenses,
            admin_expenses, general_and_administrative, sgna,
            административные_расходы]

distribution_expenses:
  aliases: [selling_expenses, distribution_costs, коммерческие_расходы,
            расходы_на_дистрибуцию]

dep_ppe:
  aliases: [depreciation, depreciation_owned, depreciation_of_ppe,
            depreciation_and_amortization, amortization_of_ppe,
            амортизация_ос]

deferred_tax_expense:
  aliases: [deferred_tax, deferred_income_tax, deferred_tax_credit,
            deferred_income_tax_credit, отложенный_налог]

earnings_from_investees:
  aliases: [share_of_profits_of_associates, equity_in_earnings,
            share_of_associates, equity_method_income,
            доля_в_прибыли_ассоциатов, доля_ассоциатов]

# BS алиасы
accounts_receivable:
  aliases: [trade_receivables, receivables, ar, net_receivables,
            дебиторская_задолженность, торговая_дебиторка]

ppe_gross:
  aliases: [property_plant_equipment_gross, pp_and_e_gross,
            propertyplantandequipment_gross, ос_по_первоначальной]

ppe_accum_dep:
  aliases: [accumulated_depreciation, accumulated_amortization,
            accumulateddepreciation, накопленная_амортизация]

investments_associates:
  aliases: [investments_in_associates, equity_method_investments,
            investments_lt, long_term_investments, investments_jv,
            инвестиции_в_ассоциаты]

# CF алиасы
interest_paid:
  aliases: [interest_expense_cf, finance_expenses_paid,
            interest_paid_net, проценты_уплаченные]

dividends_received_cfi:
  aliases: [dividends_from_associates, dividends_from_jv,
            dividends_received, дивиденды_от_ассоциатов]

wc_delta:
  aliases: [change_in_working_capital, working_capital_change,
            изменение_оборотного_капитала]
```

---

## 6. Правила знаков

### 6.1 Единая конвенция (IS_INCOME_SIGN = natural)

```
Доходы/выручка:     ПОЛОЖИТЕЛЬНЫЕ (+)
Расходы:            ОТРИЦАТЕЛЬНЫЕ (-)
Активы BS:          ПОЛОЖИТЕЛЬНЫЕ (+)
Обязательства BS:   ОТРИЦАТЕЛЬНЫЕ (-)
Капитал BS:         ПОЛОЖИТЕЛЬНЫЙ (+)

CFO:  притоки (+), оттоки (-)
CFI:  CapEx = отрицательный, поступления = положительные
CFF:  привлечение = положительное, погашение = отрицательное
```

### 6.2 В dict_sign_convention

```
Лист фиксирует convention компании. Загрузчик нормализует при загрузке.
Если аналитик заполнил расходы как положительные — загрузчик перевернёт.
```

---

## 7. EBITDA — двойное хранение

```yaml
# В history_is:
ebitda_standard:
  description: "EBITDA = EBIT + D&A (стандартное определение)"
  type: calculated
  formula: "ebit + total_da"
  stored_in_db: false  # рассчитывается движком
  note: "Загрузчик проверяет: |xlsx_value - calculated| < 1% tolerance"

ebitda_adjusted:
  description: "Adj.EBITDA как раскрывает компания (может включать impairment, associates, etc.)"
  type: input
  stored_in_db: true
  note: "Хранится как отдельная метрика 'ebitda_adjusted'. Не используется для ND/EBITDA ковенанта."
  reconciliation: "Лист показывает бридж: EBITDA_std → Adj → bridge items"
```

---

## 8. Чекап (data_quality_report)

После загрузки автоматически генерируется лист `data_quality_report`:

```
8.1 Alias Resolution Log
  metric_in_xlsx | resolved_to | status
  dep_ppe        | dep_ppe     | ✅ canonical
  depreciation   | dep_ppe     | ✅ alias resolved
  sgna           | sga         | ✅ alias resolved
  foobar         | —           | ❌ UNKNOWN — не загружено

8.2 Coverage Matrix
  metric | 2011 | 2012 | ... | 2024 | coverage% | required
  revenue| ✓    | ✓    | ... | ✓    | 100%      | CRITICAL
  capex  | ✓    | ✓    | ... | ✓    | 100%      | CRITICAL
  dta    | —    | —    | ... | ✓    | 43%       | optional

8.3 BS Identity Check (каждый год)
  year | total_assets | total_liabilities | total_equity | balance | status
  2020 | 17,378       | 10,835            | 6,543        | 0       | ✅
  2021 | 20,906       | 10,382            | 10,524       | 0       | ✅

8.4 EBITDA Reconciliation Check
  year | ebit | total_da | ebitda_std_calc | ebitda_in_xlsx | delta | status
  2024 | 368  | 512      | 880             | 1,494          | 614   | ⚠ check adj items

8.5 Sign Convention Check
  Проверяем: cogs < 0, interest_expense < 0, total_equity > 0, etc.

8.6 Debt Instruments Check
  sum(opening_balance) | BS.short_term_debt + BS.long_term_debt | gap
  7,921M               | 7,921M                                 | 0M ✅

8.7 Missing Critical Metrics
  🔴 CRITICAL: deferred_tax_expense — нет данных (есть алиас deferred_tax → resolved)
  🟡 WARNING:  wc_delta — нет данных (расчитывается из AR/Inv/AP, но компоненты пусты)
  ⚪ INFO:     rnd — не заполнено (не критично)

8.8 Engine Readiness Score
  IS: 22/27 критичных метрик ✅
  BS: 18/20 критичных метрик ✅
  CF: 12/15 критичных метрик ⚠
  Debt: 31 инструментов ✅
  READY TO MODEL: YES (с предупреждениями по CF)
```

---

## 9. excel_loader.yaml — структура v2.0

```yaml
# excel_loader.yaml v2.0
version: "2.0"
template_version: "1.2.0"

# Метаданные компании (читаем из листа meta)
meta:
  sheet: "meta"
  fields:
    company_code:    {row_label: "company_code"}
    company_name:    {row_label: "company_name"}
    base_currency:   {row_label: "base_currency"}
    base_unit:       {row_label: "base_unit"}  # mUSD, USD, kUSD
    accounting_std:  {row_label: "accounting_standard"}  # GAAP / IFRS
    is_income_sign:  {row_label: "is_income_sign"}  # natural / credit_negative
    history_start:   {row_label: "history_start_year"}
    history_end:     {row_label: "history_end_year"}

# Словарь алиасов (загружается из листа dict_metrics)
alias_resolution:
  sheet: "dict_metrics"
  canonical_col: "canonical_metric"
  aliases_col: "accepted_aliases"
  aliases_separator: ";"
  case_insensitive: true
  strip_whitespace: true

# Правила знаков (по умолчанию; override из meta.is_income_sign)
sign_convention:
  mode: "natural"  # natural (расходы < 0) | credit_negative (все abs, знак из convention)
  expense_metrics:  # эти метрики должны быть отрицательными (если mode=natural)
    - cogs, distribution_expenses, sga, rnd, dep_ppe, amort_intangibles
    - total_da, interest_expense, tax_expense, asset_impairment
    - capex, debt_repayments, dividends_paid, share_buyback
  liability_metrics:  # в BS — отрицательные
    - short_term_debt, long_term_debt, accounts_payable, total_liabilities
    - lease_liab_current, lease_liab_noncurrent, dtl, employee_benefits

# Исторические формы отчётности
history_sheets:
  history_is:
    sheet: "history_is"
    format: "metric_first"  # строки = метрики, колонки = годы
    metric_col: 1           # первая колонка = имя метрики
    header_row: 2           # строка с годами
    data_start_row: 3
    year_range: [2010, 2030]
    db_table: "history_is"
    unit_multiplier_from_meta: true  # mUSD → × 1e6 в БД
    skip_rows_if:           # пропускаем строки-заголовки
      - starts_with: "───"
      - starts_with: "HISTORY"
      - is_empty: true
    calculated_metrics:     # загрузчик НЕ берёт из xlsx, считает сам
      - gross_profit
      - ebitda_standard
      - ebt
      - tax_expense
      - total_da           # = dep_ppe + dep_rou + amort_intangibles
      - total_ca           # = cash + ar + inventory + other_ca
      - total_nca          # = ppe_net + goodwill + intangibles + ...
      - total_cl
      - total_ncl
      - total_liabilities
      - net_change_cash    # = cfo + cfi + cff

  history_bs:
    sheet: "history_bs"
    format: "metric_first"
    metric_col: 1
    header_row: 2
    data_start_row: 3
    db_table: "history_bs"
    bs_identity_check: true  # проверять A = L + E после загрузки

  history_cf:
    sheet: "history_cf"
    format: "metric_first"
    metric_col: 1
    header_row: 2
    data_start_row: 3
    db_table: "history_cf"
    cf_check: true  # проверять CF bridges

# Schedules
schedule_sheets:
  schedule_ppe:
    sheet: "schedule_ppe"
    format: "metric_first"
    db_table: "history_bs"  # PPE данные идут в BS таблицу
    metric_mapping:
      propertyplantandequipment: ppe_gross
      accumulateddepreciation:   ppe_accum_dep
      depreciation_owned:        dep_ppe
      paymentstoacquireproperty: capex

  schedule_leases:
    sheet: "schedule_leases"
    format: "metric_lease_type_first"  # metric | lease_type | yr1 | yr2...
    db_table: "history_bs"  # + history_cf для cashflows

  schedule_tax:
    sheet: "schedule_tax"
    format: "metric_first"
    db_table: "history_bs"  # DTA/DTL в BS, expense в IS

  schedule_wc:
    sheet: "schedule_working_capital"
    format: "year_first"    # год | ar_open | ar_close | delta_ar | ...
    derives:                # загрузчик вычисляет и пишет в history_cf
      - {from: [ar_close, ar_open], formula: "close - open", to_cf: "wc_ar_delta"}
      - {from: [inventory_close, inventory_open], to_cf: "wc_inventory_delta"}
      - {from: [ap_close, ap_open], to_cf: "wc_ap_delta"}

  schedule_interest:
    sheet: "schedule_interest"
    format: "year_first"

# Долговой блок
debt_sheets:
  debt_instruments:
    sheet: "debt_instruments"
    format: "row_per_instrument"
    header_row: 2
    data_start_row: 3
    db_table: "debt_instruments"
    id_col: "instrument_id"
    cleanup_before_load: true  # DELETE WHERE company_id=? перед загрузкой
    normalize_id: true         # lowercase, replace spaces with _
    type_validation:           # проверять instrument_type из dict_debt_types
      sheet: "dict_debt_types"
      col: "instrument_type"
    required_cols:
      - instrument_name, instrument_type, currency, opening_balance, maturity_date
    balance_check:             # сверять с BS
      bs_metric_ltd: long_term_debt
      bs_metric_std: short_term_debt
      tolerance_pct: 2.0       # допустимое расхождение %

  debt_cashflows:
    sheet: "debt_cashflows"
    format: "row_per_cashflow"
    db_table: "debt_cashflows"
    cleanup_before_load: true
    required_cols:
      - instrument_id, period_date, cashflow_type, amount, currency

  debt_covenants:
    sheet: "debt_covenants"
    db_table: "debt_covenants"

# Сегменты
segment_sheets:
  segments_financial:
    sheet: "segments_financial"
    format: "segment_metric_years"  # segment_name | metric | yr1 | yr2...
    db_table: "revenue_segments"
    segment_validation:
      sheet: "dict_segments"
      col: "segment_name"

  segments_operational:
    sheet: "segments_operational"
    format: "segment_metric_years"
    db_table: "preprocess_metrics"
    metric_group: "production_kpi"

# Макро
macro_sheets:
  macro_factors:
    sheet: "macro_factors"
    format: "factor_geography_years"  # factor_name | geography | yr1...
    db_table: "macro_factors"

  macro_forecasts:
    sheet: "macro_forecasts"
    format: "factor_scenario_years"   # factor_name | scenario | yr1...
    db_table: "macro_forecasts"

# Production KPI (только для production companies)
kpi_sheets:
  production_kpi:
    sheet: "production_kpi"
    enabled_if_meta: "has_production_kpi"
    format: "metric_unit_years"  # metric | unit | yr1...
    db_table: "preprocess_metrics"
    metric_group: "production_kpi"

# Валидации после загрузки
post_load_checks:
  - bs_identity:       {years: all, tolerance: 1.0}
  - ebitda_std_check:  {tolerance_pct: 5.0, flag_if_exceeded: warning}
  - debt_balance_check:{tolerance_pct: 2.0}
  - sign_check:        {critical_metrics: [cogs, capex, long_term_debt]}
  - coverage_check:    {min_years: 5, critical_metrics: [revenue, ebit, net_income]}
  - alias_resolution:  {fail_on_unknown: false, log_all: true}

# Экспорт (для round-trip теста)
export:
  enabled: true
  format: "metric_first"
  include_calculated: false   # не экспортировать расчётные строки
  include_empty_rows: true    # экспортировать все строки шаблона (пустые = пусто)
  year_range: [2011, 2024]
```

---

## 10. Round-trip тест US Steel

### Процедура
```
1. EXPORT: DB → Excel
   python3 tools/export_to_excel.py --company us_steel --output us_steel_test.xlsx

2. CLEAR: очистить данные US Steel из БД (history_is/bs/cf + debt_instruments)
   python3 tools/clear_company.py --company us_steel --confirm

3. IMPORT: Excel → DB
   from engine.loader.excel import ExcelLoader
   ExcelLoader('us_steel', 'us_steel_test.xlsx', 'companies/us_steel/configs/excel_loader.yaml').load(repo)

4. CHECKUP: запустить data_quality_report
   python3 tools/check_data_quality.py --company us_steel

5. MODEL: прогнать движок
   build_model('us_steel', run_preprocessor=True, run_model=True)

6. VERIFY: все проверки должны пройти
   BS=0, CF=0, Stress 1/1
   Метрик до: N, метрик после: N (0 потеряно)
   Алиасов resolved: X, unknown: 0
   Знаков перевёрнуто: 0
```

### Критерии приёмки
```
✅ PASS:
  - BS diff = 0 во все годы прогноза
  - CF diff = 0
  - Stress сценарий работает
  - 0 метрик потеряно при round-trip
  - 0 алиасов не разрешено
  - data_quality_report: Engine Readiness = YES

❌ FAIL:
  - BS diff > 0
  - Любая критичная метрика отсутствует после reload
  - Знак перевёрнут (cogs стал положительным и т.д.)
```

---

## 11. Реализация — задание для Claude Code

### Последовательность шагов

```
ШАГ 1: Создать tools/export_to_excel.py
  - Читает из data_mart_v2.db (history_is/bs/cf + debt_instruments + macro_factors)
  - Генерирует xlsx по шаблону v2.0
  - Включает все метрики из YearState (117 атрибутов)
  - Заполняет dict_metrics с алиасами
  - Записывает в companies/{company}/data/{company}_template.xlsx

ШАГ 2: Обновить engine/loader/excel.py
  - Читает excel_loader.yaml v2.0
  - Реализует alias resolution из dict_metrics листа
  - Реализует sign convention check + auto-flip
  - Реализует post_load_checks
  - Генерирует data_quality_report
  - Поддерживает все форматы: metric_first, year_first, segment_metric_years

ШАГ 3: Обновить excel_loader.yaml для US Steel и Rusal
  - Включить полный список алиасов
  - Настроить sign_convention
  - Указать debt_instruments параметры

ШАГ 4: Round-trip тест US Steel
  - Экспорт → очистка → импорт → чекап → прогон модели
  - Все критерии приёмки должны пройти

ШАГ 5: Применить к Rusal
  - Экспорт данных из БД в новый шаблон
  - Проверить data_quality_report
  - Исправить проблемы выявленные в аудите (PPE, EBITDA, сегменты)
```

---

*Версия: 1.0 · Апрель 2026 · stressTest v2*
