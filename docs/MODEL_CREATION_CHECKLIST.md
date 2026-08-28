# Чеклист создания финансовой модели
**stressTest_v2 Engine + Vertex Platform**
**Версия: 1.0 | 2026-08-28**

---

## Фаза 0: Подготовка данных

### 0.1 Сбор отчётности
- [ ] МСФО/US GAAP отчётность за 10-15 лет (IS/BS/CF)
- [ ] Примечания к FS: D&A split (owned/RoU), налоги (current/deferred), процентные расходы
- [ ] Долговые инструменты из примечаний: тип, ставка, валюта, дата погашения, остаток
- [ ] Операционные данные: производство (kt), цены реализации ($/t), capex breakdown
- [ ] Сегментная выручка: revenue × segments, volume × segments
- [ ] Разбивка COGS: labour, energy, materials, transport, MET, other

### 0.2 Заполнение шаблона template_v3
- [ ] `meta` — company_id, currency, db_unit, accounting_standard
- [ ] `history_is` — 25 метрик: revenue → net_income (label|db_metric|sign|unit|years)
- [ ] `history_bs` — 37 метрик: cash → total_equity
- [ ] `history_cf` — 29 метрик: net_income(CFO) → net_change_cash
- [ ] `debt_instruments` — все инструменты (id, type, rate, maturity, balance)
- [ ] `segments_financial` — segment × metric × years
- [ ] `operational_drivers` — driver × unit × years
- [ ] `macro_factors` — LME/FX/CPI/GDP × years
- [ ] `Cost_Breakdown` — labour, energy, materials, transport, other
- [ ] `Notes_DA` — depreciation_owned, depreciation_rou, amortization
- [ ] `Notes_Tax` — current_tax, deferred_tax, total
- [ ] `Notes_Finance` — interest_expense, interest_income, lease_interest
- [ ] `SGA_Split` — distribution, admin, ECL, other
- [ ] `Tax_DTA_DTL` — DTA/DTL по годам
- [ ] `Lease_Schedule` — RoU asset, lease liabilities
- [ ] `Provisions_Detail` — pension, restoration, legal
- [ ] `ppe_components` — category × value_type × year

### 0.3 Валидация данных
- [ ] BS identity: Total Assets = Total Liabilities + Total Equity (каждый год)
- [ ] IS: Revenue - COGS = Gross Profit ± 1M
- [ ] CF: Cash_open + CFO + CFI + CFF + FX = Cash_close ± 5M
- [ ] Debt: Sum(instruments) ≈ BS total_debt ± 5%
- [ ] Continuity: no gaps in years (2011-2025 complete)

---

## Фаза 1: Создание компании на Vertex

### 1.1 Vertex PG
- [ ] Компания создана в `stress_v2.companies`
- [ ] Версия модели создана через `POST /financial-model/companies/{id}/versions`
- [ ] version_tag, version_type, description заполнены

### 1.2 Загрузка данных в PG
- [ ] Historical IS/BS/CF загружены через ExcelLoader + PgRepository
- [ ] Debt instruments загружены (count > 0)
- [ ] Macro factors загружены в `macro_factor_data` (LME prices, FX, CPI)
- [ ] Operational drivers загружены в `preprocess_metrics`
- [ ] Notes data загружены (D&A, tax, cost_breakdown)

### 1.3 Macro Factor Registry
- [ ] Все используемые факторы зарегистрированы в `macro_factor_registry`
- [ ] factor_id в registry совпадает с project.yaml
- [ ] Данные есть за history + forecast период (или VECM/MR генерирует)

---

## Фаза 2: Конфигурация модели (project.yaml)

### 2.1 Revenue Model
- [ ] Тип: standard (OLS/EWA) или custom (segment Vol×Price)
- [ ] Сегменты определены (volume_method, price_method, price_factors)
- [ ] Volume history заполнена (production_kt or sales_kt)
- [ ] Price history: LME-linked или realized prices
- [ ] Capacity cap задан (если применимо)
- [ ] GDP elasticity calibrated

### 2.2 COGS Model
- [ ] Тип: clamp (min/max ratio) или component (commodity/energy/labour/other)
- [ ] da_in_cogs: true/false (IFRS: typically false)
- [ ] PPI uplift: enabled/disabled
- [ ] Dampening factor calibrated (OLS R²)

### 2.3 CapEx & PPE
- [ ] method: ratio_to_revenue или sustaining + growth
- [ ] sustaining_capex_da_ratio calibrated
- [ ] useful_life_years по отрасли
- [ ] Disposals ratio (history or constant)

### 2.4 Working Capital
- [ ] method: days (DSO/DIH/DPO)
- [ ] Days calibrated from history (preprocessor EWA)
- [ ] Cyclical elasticity parameters

### 2.5 Debt
- [ ] mode: optimizer (target ND/EBITDA) или schedule (per-instrument)
- [ ] target_net_debt_ebitda задан
- [ ] Refinancing settings (extend_years, rate_adjustment)
- [ ] min_st_debt_pct (WC floor)
- [ ] Interest treatment: separate_line или in_cogs

### 2.6 Tax
- [ ] Statutory rate (25% RU, 21% US, etc.)
- [ ] mode: full (current + deferred) или simple (effective rate)
- [ ] Payment timing: current_year или next_year
- [ ] NOL carryforward (if applicable)
- [ ] DT categories enabled (PPE, inventory, AR, AP)

### 2.7 Other
- [ ] Dividends: payout_ratio or % of FCF
- [ ] Lease: IFRS 16 enabled, discount rate
- [ ] Intangibles: additions + amortization rates
- [ ] Provisions: corkscrew enabled, categories
- [ ] Interest payable: payment timing
- [ ] Equity: buyback policy

### 2.8 Stress Scenarios
- [ ] 8-10 сценариев определены (commodity, FX, rate, energy, sanctions, severe, upside)
- [ ] macro_shocks привязаны к factor_ids из registry
- [ ] driver_shocks: avg_rate, dso_days, dih_days, cogs_pct

### 2.9 Rating
- [ ] Methodology: S&P/Moody's/Fitch
- [ ] Industry adjustment (-12% metals, etc.)
- [ ] Sovereign rating (BBB+ Russia)
- [ ] Weights: leverage/coverage/profitability/liquidity

### 2.10 Covenants
- [ ] Enabled/disabled
- [ ] Thresholds: ND/EBITDA max, ICR min, EBITDA margin min

---

## Фаза 3: Запуск и верификация модели

### 3.1 Первый прогон (base scenario)
- [ ] `POST /financial-model/versions/{id}/run` → status=done
- [ ] Revenue > 0 для всех прогнозных лет
- [ ] EBITDA margin в разумном диапазоне (10-60% по отрасли)
- [ ] Net income положительный (если нет — проверить interest/tax)
- [ ] BS diff = 0 (Total Assets = Total Liab + Equity)

### 3.2 Диагностика IS
- [ ] Revenue growth YoY: -10% to +15% (не резкие скачки)
- [ ] COGS/Revenue ratio стабилен (±5pp от history avg)
- [ ] SGA/Revenue ratio стабилен (±2pp)
- [ ] D&A/PPE ratio в диапазоне 5-15%
- [ ] Interest/Debt ratio = avg coupon ± spread
- [ ] Effective tax rate 20-30% (не 0% и не >50%)

### 3.3 Диагностика BS
- [ ] Cash > min_cash (≥ 0)
- [ ] PPE trajectory: grow with capex, shrink with D&A
- [ ] Total debt = sum of instruments
- [ ] Net debt / EBITDA в диапазоне 0-5x
- [ ] Equity positive (не negative → bankrupt)
- [ ] WC days в разумном диапазоне

### 3.4 Диагностика CF
- [ ] CFO > 0 (operating cash generation)
- [ ] CFI < 0 (capex investment)
- [ ] Cash bridge: open + CFO + CFI + CFF ≈ close
- [ ] Interest paid ≈ IS interest expense
- [ ] Tax paid ≈ IS current tax expense

### 3.5 Стресс-тесты
- [ ] Все сценарии запускаются без ошибок
- [ ] Revenue в стрессе ниже base (для downside scenarios)
- [ ] EBITDA margin компрессия в стрессе
- [ ] ND/EBITDA растёт при стрессе
- [ ] Ratings снижаются при стрессе
- [ ] Covenant breaches в severe сценарии

### 3.6 Рейтинг
- [ ] Base rating в ожидаемом диапазоне (BBB-A для investment grade)
- [ ] Rating trajectory стабилен или улучшается в base
- [ ] Stress ratings: -2 to -4 notch drop в severe

### 3.7 Ковенанты
- [ ] No breaches в base scenario
- [ ] Breaches в 1-2 severe scenarios
- [ ] Warning triggers срабатывают раньше breaches

---

## Фаза 4: Vertex Frontend

### 4.1 Model Wizard
- [ ] Data step: IS/BS/CF видны с историей
- [ ] Operations step: операционные драйверы
- [ ] Diagnostics step: data quality indicators
- [ ] Revenue/Expenses/Balance steps: config правильно отображается
- [ ] Macro step: факторы с историей и прогнозом
- [ ] Control Panel: все assumptions собраны
- [ ] Results step: charts, KPI, DCF/SOTP

### 4.2 Statements
- [ ] IS/BS/CF с историей (3-5 лет) + прогноз
- [ ] Единицы измерения (mUSD)
- [ ] Форматирование (отрицательные красным)

### 4.3 IssuerDetail
- [ ] Финансовые показатели видны
- [ ] Рейтинг отображается
- [ ] Ковенанты видны

---

## Фаза 5: Кредитный отчёт

- [ ] generate_credit_report.py для компании
- [ ] 9 разделов отчёта заполнены
- [ ] Все графики рендерятся
- [ ] Макро контекст из modelMacro
- [ ] Рыночный сигнал из impliedPD (если есть)
- [ ] Портфельный стресс из stressTest_complete

---

## Nornickel — Текущий статус

### Фаза 0: Подготовка данных
- [x] МСФО 2011-2025 (Databook 12m 2025, FS USD consolidation)
- [x] D&A split: total_da из EBITDA note, impairment отдельно
- [x] 10 debt instruments (RUB/USD/EUR/CNY, fixed+float)
- [x] 38 operational drivers из Databook
- [x] 5 segments: Ni, Cu, Pd, Pt, Other
- [x] 14 cost breakdown items
- [x] Template v3 заполнен: nornickel_v2_template_v3.xlsx

### Фаза 0.3: Валидация
- [x] BS identity проверена (smart folding, BS_diff=0)
- [x] IS: Revenue 2025 = $16.9B (Databook confirms)
- [ ] CF bridge validation
- [ ] Debt sum vs BS total_debt

### Фаза 1: Vertex PG
- [x] Компания создана (nornickel)
- [x] Version: 8b278956 (Q3_2026_base, draft)
- [x] Historical IS/BS/CF loaded (db_unit=USD, values in full USD)
- [x] 10 debt instruments loaded
- [x] Operational drivers 589 rows loaded
- [x] Notes data (cost_breakdown 238, notes_da 33, notes_tax 7)
- [x] Macro factors: lme_ni/cu/pd/pt_usd loaded (2009-2025, 17 years)
- [x] LME 2022-2025 from public annual averages (LME/LBMA)

### Фаза 2: Конфигурация
- [x] Revenue: custom segments (Ni/Cu/Pd/Pt/Other), Vol×Price, LME-linked
- [x] COGS: clamp mode (55-95%)
- [x] CapEx: ratio_to_revenue 8%
- [x] Debt: optimizer, target ND/EBITDA 2.5x
- [x] Tax: 25% statutory, full mode
- [x] Dividends: 75% payout
- [x] Covenants: enabled (ND/EBITDA ≤ 4.5, ICR ≥ 2.0)
- [x] Stress: 10 scenarios (nickel_downturn, pgm_crash, metals_bear, fx, energy, rate, sanctions, severe, upside, demand)
- [x] Rating: S&P, industry -12%
- [x] Factor names aligned with PG registry (lme_ni_usd etc.)
- [x] macro_ecm.yaml: metals_prices + pgm_prices VECM groups, MR for commodity

### Фаза 3: Запуск и верификация
- [x] Base model run → status=done, Revenue=$18.4B
- [x] Revenue > 0 ✅ (4 metal segments generating revenue)
- [ ] Revenue calibration: $18.4B vs actual $13.8B (LME uses 2021 levels, MR не прогнозирует)
- [ ] BS diff > 0 ($9.4B — нужен smart folding для NNK-specific BS items)
- [ ] Cash accumulation: $7B→$33B (dividends не выплачиваются?)
- [ ] Forecast 5yr vs config 3yr mismatch
- [ ] EBITDA margin фиксирован 45.8% (нужна динамика)
- [ ] Stress runs
- [ ] Rating runs
- [ ] 14-section notebook validation (BS/CF identity, regression, corkscrews)
