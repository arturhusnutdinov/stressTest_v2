# Математика корпоративной финансовой модели — полная спецификация (для начинающего специалиста)

> Версия: **v2.4** (Excel-книги rusal_v4 / nornickel_v4, 33 листа, ~1 800 формул; Python engine `engine/`, 2 компании-калибра: UC RUSAL, Nornickel).
> Дата: 19.11.2026. Источники формул: `templates/excel_v4/scripts/build_model.py`, `engine/model/core.py`, `engine/model/cogs_block.py`, `engine/model/segment_revenue.py`, `engine/model/schedules/debt.py`, `engine/rating/core.py`, `templates/excel_v4/config/macro_scenarios.yaml`, `docs/FORECAST_ADEQUACY_CORP.md`.
> Маркировка: **[ДАННЫЕ]** — факт из отчётности МСФО; **[ОЦЕНКА]** — расчёт модели; **[ПАР]** — параметр (Control_Panel / YAML-конфиг); **[НОРМ]** — константа методологии.
> Как читать формулы: обычный текст с символами Σ Δ ≤ ≥. Запись `cash(t−1)` читается «касса на конец прошлого года». Глоссарий — Приложение D.

---

# Часть 0. Введение

## 1. Что это за модель и зачем она нужна

**1.1. Назначение.** Модель прогнозирует финансовое состояние металлургической компании на 3 года вперёд (2026–2028) от последней годовой отчётности МСФО (2025). На выходе: прогноз трёх форм отчётности (баланс, прибыль, движение денег), ковенантный анализ, кредитный рейтинг с прогнозом (outlook), стресс-тесты (9 сценариев), обратный стресс, tornado, оценка (DCF/SOTP). Шаблон универсален: новая компания добавляется конфигом (`project.yaml`) и данными.

**1.2. Почему корпоративная модель — это не банковская.** В банковской модели (см. `bank_model/docs/MODEL_MATH_FULL.md`) всё замкнуто в регуляторные кольца: кредиты → RWA → норматив → капитал → снова кредиты, и книга решается итерациями Excel. Здесь конвенция другая — **«открывающие остатки» (opening-balance convention)**:

```
всё, что происходит в году t, опирается на ОСТАТКИ на конец года t−1:
  долг(t) = долг(t−1) + draw(t) − repay(t)       (не «долг на начало» внутри года)
  PPE(t)  = PPE(t−1) + capex(t) − depreciation(t)
  касса(t) = касса(t−1) + CFO(t) + CFI(t) + CFF(t)
```

Благодаря этому книга — **ациклический граф (DAG, 0 поперечных циклов)**: Excel считает каждую ячейку ровно один раз. Итерационный расчёт в книге **включён** (`calcPr iterate=1`, 1000 проходов, допуск 1e-4 — банковская конвенция, указание 20.11): при DAG он формально не задействуется, но (а) страхует от случайных колец при правках пользователя, (б) поддерживает seed-механику колец (ниже). Единственный «контур» внутри года — «проценты ↔ прибыль ↔ касса», и он решается не циклом, а **замкнутой формулой плага** (глава 13). Кольцевая зона дополнительно обёрнута в `IFERROR(формула, seed)` + релаксацию `X=(1−ω)·X+ω·g(X)` (ω=CP!L2, default 0.3): seed = значение Python engine из скрытого SEED-блока 17_Debt (защита холодного старта Excel от заморозки #DIV/0!), при нормальной работе обёртка прозрачна (неподвижная точка та же). Python-движок использует итерационный солвер (до 10 проходов, tol $1K) с snapshot-restore долговых инструментов — это эквивалентные математические объекты, сверяемые гейтом (глава 30).

**Почему не CFI-кольца в книге (устройство 20.11).** Проценты CFI-конвенции `AVG(open, close)` с года выпуска создавали контур `new_term → synth-int → NI → CF → cbrc → need → new_term`; с кinks `min_cash/defer` якоби-итерации Excel расходились (e+265) — релаксация не лечит, т.к. расходимость идёт через нелинейные пороги и сингулярность `rate↔avg_rate`. Поэтому в книге проценты — по opening-остаткам, проценты synthetic-транша начинаются с года после выпуска, ставка транша — от avg_rate прошлого года (репрайсинг с лагом 1Y); циклический solver остаётся в engine. Книга при этом математически эквивалентна: сверка гейтом (глава 30) подтверждена.

**1.3. Два движка — одна математика.**

| | Excel (основной продукт) | Python (параллельный движок) |
|---|---|---|
| Где | `model/<company>_v4.xlsx`, 33 листа | `engine/model/core.py`, блоки 5–19 |
| Порядок расчёта | DAG по opening-balance | последовательный проход по годам, итерации внутри года |
| Макро | стартовые точки сценариев из SSOT-YAML | тот же SSOT (`engine/macro/scenario_config.py`) + VECM/MR для прочих факторов |
| Сверка | `sync_gate_corp.py`: структура ±3 п.п., уровни ±20% | та же команда, engine-сторона из БД |

**1.4. Карта книги.**

| лист | роль | глава |
|---|---|---|
| 01_Macro | 3 макросценария + источники, OLS-блок | 7 |
| 11_Segments / 10_Revenue | объёмы × цены по сегментам, recon-линия | 8 |
| 12_COGS | компонентная себестоимость | 9 |
| 15_PPE / 16_WC / 18_Lease / 19_Tax | corkscrew-листы | 10–12 |
| 17_Debt | расписание долга, S&U, плаг фондирования | 13 |
| 20_BS / 21_PL / 23_CF / 24_Equity | три формы + капитал | 14–16 |
| 30_Ratios / 32_Covenants | метрики, ковенанты | 17 |
| 31_Score / **34_Rating** | скоркарта и итоговое присвоение | 18 |
| 33_RevStress / 40_Scen | обратный стресс, tornado, сценарии | 19 |
| 35_Valuation | DCF + SOTP | 20 |
| 90_Checks | все тождества = 0 | 21 |

## 2. Нотация и соглашения

**2.1. Время.** C…E = 2023…2025 (история, 3 отображаемых года; полная история 2011–2025 — на 02_Hist), F…H = 2026…2028 (прогноз). E = последний факт. `(t−1)` — год назад; `Δx(t) = x(t) − x(t−1)`.

**2.2. Сегменты.** RUSAL: primary_al (алюминий, prod-объём), alumina, other (VAP/фольга — через recon-линию). Nornickel: nickel, copper, PGM (микс Pd+Pt). Индекс `s` — по сегментам, `w_s` — доля сегмента.

**2.3. Знаки.** Расходы в модели положительны в CP/Uses и отрицательны в П&Л (естественный знак отчётности); `_load_pl` и `link_hist_to_ifrs` нормализуют через ABS. Долг — положительный баланс. Макро-индексы CPI/PPI — цепные, base = 100.

**2.4. Единицы.** Млн USD (mln), объёмы — kt (тыс. тонн), цены — $/т (в историях сегментов иногда tUSD = $/т × 1000 — loader нормализует). Ключевое правило: в компонентном COGS `kt × $/т = тыс. $` → обязателен перевод в тонны (×1000), иначе занижение в 1000 раз (реальный дефект 19.11, пойман клампом).

---

# Часть I. Пространство состояний и параметры

## 3. Состояние модели (YearState)

Python: датакласс `YearState` (~120 полей). Минимальный набор, достаточный для воспроизведения:

```
Отчёт о прибылях:  revenue, cogs, gross_profit, sga, distribution_expenses,
                   other_operating_expenses, ebitda, total_da, ebit,
                   interest_expense, interest_income, earnings_from_investees,
                   other_financial_costs, ebt, current_tax, deferred_tax, net_income
Баланс:            cash, ar, inventory, ap, other_ca, ppe_gross, ppe_accum_dep,
                   ppe_net, intangibles, goodwill, investments_lt, other_nca,
                   short_term_debt, long_term_debt, lease_liab, other_cl, other_ncl,
                   equity (share_capital, apic, retained_earnings, aoci)
ОДДС:              cfo_total, cfi_total, cff_total, capex, dividends_paid, ...
Служебное:         year, bs_identity, cf_bridge, _cash_estimate, _actual_cfo_est
```

Инварианты состояния (`full_validation()`, глава 21):
```
bs_identity:   total_assets − total_liabilities − total_equity = 0
cf_bridge:     cash(t) − cash(t−1) − (CFO + CFI + CFF) = 0
cash_bs_cf:    cash(БС) = cash(ОДДС)
```

## 4. Параметры

**4.1. Control_Panel (Excel)** — ~130 параметров в 12 секциях (A. Макросценарий … L. Рейтинг). Примеры с ролями:
`min_cash` [ПАР], `rc_limit`, `rc_rate`, `sweep_pct`, `target_leverage`, `maint_share`, `wc_lambda`, `sc_w_*` (веса скоркарты), `sc_th_*` (пороги шкалы), `sc_lev_slope/max`, `sc_cov_scale/max`, `cbr_key_rate_forecast`, `penalty_rate`, `cp_alumina_lme_ratio`, `day_count` [НОРМ 365].

**4.2. YAML-конфиги** (книга + engine читают одно):
```
templates/excel_v4/config/macro_scenarios.yaml  — SSOT макросценариев (base/stress/severe ×
                            факторы, источники, винтаж; ols_supplement; lme_al_history)
templates/excel_v4/config/external_ratings.yaml — фактические рейтинги АКРА/НКР/Эксперт РА
templates/excel_v4/config/business_risk.yaml    — баллы Business Risk Profile с обоснованиями
companies/<co>/configs/project.yaml             — режимы блоков (cogs component_mode, debt
                            optimizer, сегменты с price_beta/price_anchor/price_mix_weights)
```

**4.3. Правило аудита**: литералы в формулах допустимы только из {0, 1, 2, 3, 4, 6, 12, 100, 0.5} и структурные константы (помечены [НОРМ]). Всё остальное — параметр с тегом источника.

---

# Часть II. Макро-модуль

## 5. Макросценарии и SSOT

**5.1. Единый источник.** Все стартовые точки сценариев — `config/macro_scenarios.yaml` (винтаж 18.11.2026). Каждое значение имеет `source` (ЦБ/Минфин/WB CMO/LME/Westmetall/ECB staff с URL) и тег. Книга читает через `scripts/macro_config.py` (fill_data пишет значения + источники в 01_Macro кол. J/K); engine — `engine/macro/scenario_config.py` (метод `scenario_base(yaml …)`, только base).

**5.2. Три сценария (книга).** Base = консенсус/официальные прогнозы; Stress = коммодити −20%, FX +15-20%, инфляция +2 п.п.; Severe = коммодити −40% (чисто ценовой шок, FX = base для rusal). Алумина — производная: `alumina = LME_Al × cp_alumina_lme_ratio` (0.134 = факт 2025).

**5.3. Base-пути (факты на винтаж 18.11.2026).**

| фактор | base 26/27/28 | источник-якорь |
|---|---|---|
| LME Al, $/т | 3250 / 3050 / 2900 | YTD-2026 ≈ 3270 (Westmetall дневные), WB CMO Oct-26 |
| USD/RUB | 85 / 95 / 99 | опрос ЦБ 81.2; Минфин 92.2; МЭР 100.2→106 |
| ключевая, % | 14.6 / 11.5 / 9.0 | ЦБ 23.10.2026 |
| Euribor 6M, % | 2.6 / 2.6 / 2.3 | ECB staff Sep-26 |
| Brent | 72 / 70 / 68 | опрос ЦБ $70; Минфин Urals $53 (2027) |

**5.4. Методы прогноза факторов (engine, вне SSOT).**
```
VECM-группы:   cpi_ru, ppi_ru (Johansen, длинные ряды)
EWA:           dxy, gdp_world, gdp_us  (halflife 5)
MeanRevision:  brent_usd, lme_al_usd (κ=0.12, HL=5.6л на 40-летней истории)
MR-коммодити в стрессах: κ=0.5 (bear), rw_drift P50-P95 (bull)
sanity-fallback: flat(last) — ЗАПРЕЩЁН в base (гейт плаузибилити: flat-путь в base = дефект)
```

**5.5. Дедупликация рядов.** Одно экономическое понятие = одно значение в base: USD/RUB пишется и в `usd_rub`, и в `fx_usdrub`; Brent — в `brent` и `brent_usd` (маппинг `BOOK_TO_ENGINE` в scenario_config.py).

**5.6. История LME.** Номинальные годовые средние cash-settlement (Westmetall): `lme_al_history` в YAML 1990–2026 (2026 = YTD по 17.11 ≈ 3270, [ДАННЫЕ]). Исправлен дефект −25% (драйвер CSV был занижен: 2021 = 1783 vs 2484) — tools/fix_lme_history.py.

## 6. Эконометрика в книге (01_Macro)

OLS-блок Δln(revenue) ~ α + β·Δln(factor) на 2018–2025 (N=7): SLOPE/INTERCEPT/RSQ/STEYX — **формулами Excel** над введёнными рядами (β честно показан со значимостью; для RUSAL β≈0.65, t≈1.6 — слабо). Номинальные годовые средние для факторов — `ols_supplement` YAML. Прогнозные цены сегментов НЕ идут через OLS (см. 8.2) — OLS-блок диагностический.

---

# Часть III. Операционные блоки

## 7. Выручка: Revenue = Σ_s (Vol_s × Price_s) + Recon

**7.1. Сегменты.** Каждый сегмент: объём (kt) × цена ($/т). RUSAL: primary_al (объём = production_kt, потолок 4100 kt [ДАННЫЕ nameplate]), alumina, other; Nornickel: nickel, copper, PGM.

**7.2. Цена сегмента (связка с макро).** Конвенция книги: **реализованная цена прогноза = LME-путь** (премия к LME обнуляется — якорь на LME-базисе):
```
price_s(t) = anchor_s × Π_{τ≤t} (F_s(τ)/F_s(τ−1))^β_s        (chain-link)
  β_s = price_beta = 1.0  [ПАР]   — цена 1:1 к фактору (без OLS-демпфинга)
  anchor_s = price_anchor = LME-базис базового года          [ПАР]
  F_s = макрофактор (lme_aluminium / lme_alumina / lme_ni_usd …)
PGM (Pd+Pt): бленд-фактор  mix(t) = 0.72·Pd(t) + 0.28·Pt(t)  (веса pgm_mix [ДАННЫЕ 2023-25]),
  цена = anchor_PGM × mix(t)/mix(2025), anchor_PGM = 960 (realized 2025)
```
Engine-допуск: `price_mix_weights` строит бленд-ряд и chain-link'ит по нему с β=1 (segment_revenue.py).

**7.3. Объёмы.** Book: carry-forward last fact (RUSAL 3918 kt; Норникель по сегментам). Engine: volume_method из YAML (ewa) + **потолок спроса**: рост объёма ≤ GDP_world-рост × 0.8 (эластичность спроса алюминия) + capacity cap 4100 kt.

**7.4. Recon-линия (прочая выручка).** Книга и engine единообразно:
```
recon(2025) = total_факт − Σ seg_rev(2025)        [ДАННЫЕ остаток: VAP/фольга/перепродажа]
recon(t)    = recon(t−1) × Σseg_rev(t) / Σseg_rev(t−1)   (растёт за сегментами)
```
Dummy-сегменты (volume ≈ 1, «other» RUSAL) сворачиваются в recon — иначе их EWA-рост (+4%/г) расходится с книжным ростом recon. Итог: total_rev(t) = Σseg_rev(t) + recon(t). Эта конструкция (P1a, 19.11) сблизила движки: Revenue Δ0.4–1.2%.

## 8. COGS

**8.1. Компонентный режим (RUSAL, `component_mode: true`).** Чистая сумма без re-anchoring (book-faithful, Δ0.3% к книге):
```
prod_t = production_kt × 1000                      (тонны! [НОРМ конверсия])
Material(t)   = prod_t × (1.93 × 0.134 × LME_Al(t) + fixed)      $/т
                fixed = material_usd_t − 1.93 × alumina_realized_base
                alumina_realized_base = LME_alumina_hist(base) × 1.5214   (премия 537/353)
Purchases(t)  = prod_t × 332 × LME_Al(t)/LME_Al(base)            (перепродажа по LME)
Energy(t)     = E_base × power_idx(t) × fx_blend(t) × vol_adj
Labour(t)     = L_base × cpi_idx(t)   × fx_blend(t) × vol_adj
Other(t)      = O_base × ppi_idx(t)  × vol_adj
fx_blend(t)   = (usdrub(base)/usdrub(t))^0.7                      (доля FX-эффекта 0.7 [ПАР])
```
`$/t` выводятся из долей (`material_share 0.4517, purchases_share 0.1061, energy_share_c 0.2527, labour_share_c 0.0816, other_share_c 0.1079` [ДАННЫЕ 12_COGS note 6a]) × base_cogs/prod_base — воспроизводит калибровку 2025 точно и консистентна для любого базового окна. Абсолютный кламп: [0.5×, 1.5×] base_cogs.

**8.2. Режим доли (Nornickel).** `cogs_pct = 0.583` [ПАР incl-DA]: engine вычитает долю амортизации (`cogs_pct − dep_to_rev`), т.к. `da_in_cogs: false` — двойное исключение запрещено. Книга: ratio 48% ex-DA (EWA 2023-25).

**8.3. Ограничения (обе).** Кламп ratio [min 0.45, max 0.90] [ПАР]; в стрессе cost_shock (P2): ppi +12%, cpi +8%, power +30% (RUSAL через компоненты; Nornickel `cogs_pct +6 п.п.`).

## 9. SGA и прочие операционные

```
sga(t) = sga_pct × rev(t) × (1 + cpi_uplift),  sga_pct из margin_ratios (EWA)
Nornickel [ПАР]: sga_pct = 0.035 net-опекс (SGA 11.3% − прочий операционный ДОХОД 7.8%)
дробление (split-режим): distribution/admin/ECL/other_opex долями от total_sga
other_opex: метод из forecast_methods (last/ewa/zero — конфиг компании)
associates: method last (книжная конвенция — последний факт; EWA запрещён: раздувал до 872 vs 666)
impairment: forecast = 0 (разовые не прогнозируются); hist — факт
```

## 10. PPE и CapEx (corkscrew + иерархия Uses)

```
gross(t)  = gross(t−1) + capex(t) − disposals(t),   disposals = capex × disp_pct
dep(t)    = dep_open(t−1) + charge(t) − dep_disp(t)  (charge: когорты/ставка)
net(t)    = gross(t) − dep(t)                       (сверка: PPE check = 0)
capex_plan(t) = MAX(dep(t−1) × sustaining_ratio, rev(t) × da_rate × capex_floor)
```

**Иерархия Uses (D1, 18.11)** — отложенный проектный CapEx при дефиците кассы (ациклично):
```
cbrc_plan(t)   = cash(t−1) + CFO + CFF_no_RC − capex_plan          (плановый вариант)
defer(t)       = MIN(capex_plan × (1 − maint_share), MAX(0, min_cash − cbrc_plan))
capex(t)       = capex_plan − defer
funding_need   = MAX(0, min_cash − cbrc_plan) − defer               (после отложения)
```
Идея: реальный казначей режет дискреционный CapEx раньше, чем берёт штрафной долг; в base-defer = 0 (кассы хватает), механика — страховка стресса.

## 11. Оборотный капитал (частичная подстройка)

```
DSO/DIH/DPO(t) = days(t−1) + λ_t × (target_CP − days(t−1))         (D4)
  λ = wc_lambda = 0.6; год 2: MIN(1, 2λ); год 3: 1                   [ПАР CP.wc_lambda]
  target_CP = EWA 3 лет из 03_Assump
AR = rev × DSO/365;  INV = |COGS| × DIH/365;  AP = |COGS| × DPO/365   (day_count CP [НОРМ])
NWC = AR + INV − AP;  ΔNWC(t) = NWC(t) − NWC(t−1)  (в CFO со знаком)
```
Эластичности (engine, калиброваны OLS на RUSAL 2011-25, constants.py): DSO 0.87, DIH 0.36, DPO 0.64.

## 12. Аренда и налог

**Lease (IFRS 16).** ROU + liability: `rou_close = rou_open + additions − amort`; финансовый лизинг — principal + interest отдельно; safety caps: amort/payment ≤ открывающий остаток (защита от отрицательного ROU).

**Tax (IAS 12).**
```
current_tax = rate × MAX(0, EBT − NOL_used − accel_dep_excess)     rate = 0.25 [НОРМ РФ 2025+]
deferred    = −(ΔDTL − ΔDTA)
NOL:        used = MIN(nol_open, EBT × 0.8) → DTA; carryforward engine (Nornickel даёт эфф. ~11.5% в 2026)
DT-категории: PPE/Inv/AR/AP × ставки категорий; DTA valuation allowance при EBT < 0
оплата: RUSAL — текущим годом; US Steel — следующим (timing-конфиг)
```

## 13. Долг: инструменты, оптимизатор, плаг фондирования

**13.1. Инструменты.** Долг = набор инструментов (debt_instruments): opening, rate (спред для флоатеров), rate_type, base_rate_factor (`cbr_key_rate` / `euribor_6m`), maturity, amortization_profile. Конвертер в optimizer-state передаёт rate_type + base_rate_factor (фикс 19.11: раньше терялись — все флоатеры были fixed).

**13.2. Проценты по инструментам.**
```
effective(i,t) = spread_i + base(i,t)
  base = cbr_key_rate_forecast(t)  если base_rate_factor = cbr_key_rate     (SSOT: 14.6/11.5/9.0)
  base = euribor_6m(t)             если base_rate_factor = euribor_6m        (2.6/2.6/2.3)
  base = 0 (спред = all-in)        для fixed и неподдержанных базисов (SOFR)
interest(i,t) = AVG(open_i(t), close_i(t)) × effective(i,t)
```
Исторический anchor: avg rate по факту (RUSAL 8.01%); штрафная ставка penalty_rate [ПАР] при закрытом гейте.

**13.2a. Конвенции книги (excel_v4) — отличаются от engine намеренно (устройство 20.11).** Чтобы книга оставалась DAG и сходилась с холодного старта:
```
DT.interest_term(книга) = term_open(t) × avg_rate(t)          (opening-balance)
synthetic-транш:        проценты с года, СЛЕДУЮЩЕГО за выпуском (год t: = 0)
                        ставка транша = avg_rate(t−1) + spread_base + spread_step × MAX(0, ND/EBITDA(t) − target)
                          (репрайсинг с лагом 1Y: same-year rate↔avg_rate = сингулярность)
RC interest:            rc_open × (KeyRate + spread)           (opening, как в engine)
```

**13.3. Гейт рынка срочного долга.**
```
gate(t) = AND(new_debt_available=1, NOT covenant_breach(t−1), ICR(t−1) ≥ cov_icr, EBITDA(t) > 0)
  EBITDA ≤ 0 → рынок закрыт полностью (ни штрафного транша)  [защита от рефинансирования убытков]
```

**13.4. Потребность и плаг (closed-form, без итераций).**
```
cbrc(t)      = cash(t−1) + CFO(t) + CFI(t) + CFF_no_RC(t)         (ДС до решений по RC)
need₀(t)     = MAX(0, min_cash − cbrc_plan(t))                    (D1: от планового CapEx)
RC_draw(t)   = MIN(free_limit, need₀ − defer)                     (free_limit = rc_limit − rc_open)
term_out(t)  = IF(utilization > rc_trigger, RC − trigger×limit, 0) (конверсия в транш)
new_term(t)  = IF gate: need − RC_draw + term_out;  IF NOT gate: MIN(остаток, pen_limit)
voluntary(t) = MIN(доступная_ликвидность × sweep, MAX(lev-driven, excess_cash))
             при NI > 0 и нет breach; LT-погашение с премией prepay_premium
FX-reval:     Δdebt = debt_RUB-share × ΔRUB + debt_CNY-share × ΔCNY (SUMPRODUCT по Raw_IFRS)
residual-инструмент: gap между Σ инструментов и BS-total долга (backtest-окна: пропорциональная нормализация к BS-total при расхождении >5×)
```

**13.5. Итерационное ядро (engine) и зеркало в книге.** Внутри года: CFO зависит от NI, NI от процентов, проценты от closing balances → solver: до 10 итераций, tol $1K, **snapshot-restore** инструментов между итерациями (иначе мутации накапливаются — дефект «раздувающегося долга», закрыт 18.11). Книга этот контур не итерирует: opening-balance конвенции (13.2a) + closed-form плаг делают её DAG; итерационный режим Excel включён как страховка и для seed-механики. История устройства: попытка 19–20.11 перенести CFI-кольца (`AVG(open,close)` с года выпуска) в книгу дала расходимость якоби-итераций (e+265) через min_cash/defer-кinks — экспериментально показано замораживанием пар `interest_term`/`new_term`; финальное решение — кольца только в engine, книга DAG. Оба подхода сошлись в sync-гейте (глава 30).

## 14. Баланс и прибыль (тождества)

```
TA = cash + AR + INV + other_ca + PPE_net + intangibles + goodwill + investments_lt + other_nca
TL = STD + LTD + lease + other_cl + provisions + other_ncl
TE = share_capital + APIC + retained_earnings + AOCI
BS:  TA − TL − TE = 0                        (проверка 90_Checks, Δ=0 все годы)
RE(t) = RE(t−1) + NI(t) − dividends(t) − buybacks(t)
AOCI(t) = AOCI(t−1) + FX-переоценка долга (через 17_Debt fx_reval)
EBITDA = gross_profit + sga (+ other_opex_income, если Nornickel: sga net-конвенция)
EBIT   = EBITDA − D&A;  EBT = EBIT + associates + interest_income − interest − other_fin
NI     = EBT − current_tax − deferred_tax
```

## 15. ОДДС (косвенный метод, тождество по построению)

```
CFO = NI + D&A + deferred_tax + ΔWC + Δtaxes_payable + Δinterest_payable + прочие не-движения
CFI = −capex + disposal_proceeds + associates_disposal
CFF = Δdebt(draw−repay) − dividends − lease_principal + equity_issuance
cash(t) = cash(t−1) + CFO + CFI + CFF     (cf_bridge = 0)
```
CF-полнота: non-WC корректировки (Δother_ncl, Δother_nca, restricted_cash) — v2.2.0, без плагов.

## 16. Капитал

Corkscrew капитала — через retained earnings (глава 14) и AOCI; dividends: payout_policy из конфига (RUSAL 0 при высоком леверидже — политика En+; Nornickel 50%+ ЧП). Equity issuance/buyback — событийные input. Ковенанты (32_Covenants): ND/EBITDA ≤ 4.5, ICR ≥ 2.0 (RUSAL); 3.0/2.0 (Nornickel) — headroom и breach-флаги; acceleration: при breach instrument → ST-reclass.

---

# Часть IV. Рейтинг (полный цикл присвоения)

## 17. Скоркарта (31_Score) — финансовая половина

Четыре фактора, суб-скоры 0-100, веса [ПАР CP.sc_w_*]:
```
Leverage 35%:  IF(EBITDA≤0, 5, MAX(5, MIN(cp_lev_max, cp_lev_max − ND/EBITDA × cp_lev_slope)))
Coverage 30%:  MAX(5, MIN(cp_cov_max, ICR × cp_cov_scale))
Profit 20%:    MAX(5, MIN(cp_prof_max, MIN(margin, cycle_avg × 1.5) × cp_prof_scale))   (TTC-кап)
Liquidity 15%: MAX(5, MIN(cp_liq_max, CR × cp_liq_scale))
base = Σ w_k × score_k;  final = CLAMP(base + ind_adj + size_adj, 0, 100)
ind_adj = −6 [ПАР], size_adj = +2 [ПАР]   (engine по умолчанию −12 — расхождение в работе)
Rating = INDEX(шкала, MATCH(final, пороги, −1)); пороги CP.sc_th_* (AAA≥90 … B-≥18, иначе D)
```
Шкала-lookup на 34_Rating (18 ступеней): `B = S&P | C = min score (ссылки CP) | D = notch | E = RU`.

## 18. Итоговое присвоение (34_Rating)

**Три опоры** (все — рейтинги скоркарты, но на разных данных):
```
П1 Текущий     = Rating(2025)                        — факт отчётности
П2 Прогнозный  = worst(Rating(2026..2028) base)      — max нотча
П3 Стрессовый  = worst(Rating(2026..2028) Stress)    — из снимков 40_Scen; Severe не входит
n_i = MATCH(П_i, шкала)                              (notch 1..18)
```

**Четвёртая опора — Business Risk Profile** (конфиг с обоснованиями):
```
biz_score = Σ_i w_i × b_i × 10,   b_i ∈ [1,10]  [ОЦЕНКА с обоснованием]
  измерения: страна/отрасль 0.25, конкурентная позиция 0.35, диверсификация 0.20, финполитика 0.20
adj = CLAMP(ROUND((biz_score − 55)/15), −2, +2)      (+ улучшает)
```

**Присвоение:**
```
ИТОГОВЫЙ нотч = CLAMP( MEDIAN(n1, n2, n3) − adj, 1, 18 )
ИТОГ (intl) = Шкала[notch];  ИТОГ (RU) = RU[notch]
RU-маппинг: intl → RU через суверенный якорь: BBB+ intl = AAA(RU), нотч ниже суверена = нотч вниз (потолок AAA(RU)) — как engine intl_to_national
Суверенный потолок: intl ≤ BBB+ (РФ)
Headroom = 18 − итоговый нотч
```

**Прогноз (outlook), 6-24 мес:**
```
Δ = n1 − n2  (текущий − прогнозный)
Δ ≥ +3 и (n3 − итог) < 3  → «Позитивный»
Δ ≥ +3 и (n3 − итог) ≥ 3  → «Развивающийся»     (событийный оверрайд)
Δ ≤ −3                    → «Негативный»
иначе                     → «Стабильный»
пороги 3/−3/3 — input-ячейки [ПАР]
```

**Сверка с агентствами** (раздел F): фактические АКРА/НКР/Эксперт РА (config/external_ratings.yaml, [ДАННЫЕ] с URL), отклонение модели в RU-нотчах, модельный outlook напротив прогнозов агентств. Статус 19.11: RUSAL +2 (в допуске), Nornickel 0; outlook: RUSAL «Развивающийся» vs АКРА «Стабильный», Nornickel «Стабильный» = НКР.

## 19. Стресс-механика

**Сценарии (engine, 9-10):** macro_shocks (факторы ×%) + driver_shocks (avg_rate +2 п.п., cogs_pct +6 п.п., DSO/DIH ×%). Полный пересчёт 3-statement на каждый сценарий; cost_shock (P2) — ppi +12/cpi +8/power +30. **Книга**: 3 сценария через CP!C5 (снимки на 40_Scen).
**Обратный стресс (33_RevStress):** bisection по шоку Revenue до нарушения ковенанта ND/EBITDA ≤ порог (RUSAL −57%, Nornickel −74%).
**Tornado:** ±1σ по ставке/выручке/COGS/FX → ΔEBITDA, ΔNI, ΔND/EBITDA.

## 20. Оценка (35_Valuation)

DCF: FCFF = EBIT×(1−t) + D&A − capex − ΔNWC; дисконтирование по WACC (CP); terminal value Gordon. SOTP (Норникель): по сегментам. Ссылки на годы строго через REG (дефект «чужой год» E2 закрыт).

---

# Часть V. Ограничения системы (формально)

```
1. TA − TL − TE = 0                          (все годы; 90_Checks + full_validation)
2. cash(t) − cash(t−1) − (CFO+CFI+CFF) = 0   (cf_bridge)
3. PPE: net = gross − accum_dep              (corkscrew)
4. Debt: close = open + draw − repay ± FX    (corkscrew, по инструментам)
5. RE: close = open + NI − div               (corkscrew)
6. RC_close ≤ RC_limit;  penalty ≤ pen_limit
7. gate закрыт при EBITDA ≤ 0 → new_term = 0
8. volume ≤ capacity (4100 kt) и ≤ demand (GDP×0.8)
9. deferral: capex ≥ maint-компонента        (D1: проектный режется первым)
10. клампы: COGS ∈ [0.5, 1.5]×base; cogs_ratio ∈ [0.45, 0.90]; sanity bounds engine
    (assets ≤ 1e12, interest/rev ≤ 0.5, debt/rev ≤ 10) — fail-fast E7
11. ковенанты: ND/EBITDA ≤ 4.5 (3.0 NN), ICR ≥ 2.0 — breach → acceleration
12. WC-дни: сходимость к target за 2-3 года (λ-путь), не скачок
```

---

# Часть VI. Калибровка и ключи

## 21. Реестр калибровок

| параметр | значение | метод | источник |
|---|---|---|---|
| COGS-доли (5 компонентов) | 45.2/10.6/25.3/8.2/10.8% | факт 12_COGS note 6a | [ДАННЫЕ] МСФО |
| alumina_lme_ratio | 0.134 | факт 2025 = 353/2561 | [ДАННЫЕ] |
| alumina_premium | 1.5214 | realized/LME = 537/353 | [ДАННЫЕ] |
| fx_passthrough | 0.7 | CP книги | [ПАР] |
| WC-эластичности DSO/DIH/DPO | 0.87/0.36/0.64 | OLS Δdays ~ Δrev, n=12-14 | RUSAL 2011-25 |
| PGM-микс 0.72/0.28 | — | доли PGM-выручки 2023-25 | [ДАННЫЕ] |
| скоркарта: веса 35/30/20/15; пороги 90…12; adj −6/+2 | — | калибровка US Steel 2024 (BB+/Ba1) | [ПАР] + 1 точка |
| business risk баллы/весы | конфиг | экспертные [ОЦЕНКА] с обоснованием | config |
| capex: sustaining ×DA (≈2.0-2.2), growth 5% Δrev | — | медиана 2021-25 | [ДАННЫЕ] |
| налог 0.25 | — | НК РФ 2025+ | [НОРМ] |
| capacity 4100 kt | — | nameplate | [ДАННЫЕ] |
| макро base | см. 5.3 | консенсус/официальные | URLs в YAML |

## 22. Ключи и маппинг

```
Excel-фактор → engine-фактор: BOOK_TO_ENGINE (scenario_config.py) с дедупом
  USD/RUB → usd_rub + fx_usdrub; Brent → brent + brent_usd
история LME: lme_al_history (YAML) → macro_factors (scope global) — tools/fix_lme_history.py
Vertex → SQLite: tools/export_vertex_to_mart.py (versions→history/debt/preprocess/LME-сеед)
сегменты: book-name ↔ yaml-key (name_map в fill_data); engine segs из project.yaml
YAML hist: числа через preprocessor, не в конфигах (конвенция проекта)
```

## 23. Верификационная батарея

```
build → fill → finalize (живой Excel recalc, ПОСЛЕДНИЙ шаг; закрывает чужие
        книги и адресует workbook по имени — защита от app-resume, фикс 20.11)
audit_corp_model.py        — 27 PASS, 0 FAIL ×2 (E7 sanity, H4 цвета, G1 OLS)
90_Checks                  — все тождества = 0 (BS/CF/PPE/Debt/Equity/S&U);
                             0 ячеек-ошибок Excel (#DIV/0! и пр.)
sync_gate_corp.py          — структура ±3 п.п. жёстко, уровни ±20% мягко (PASS ×2)
plausibility_corp.py       — V.1-V.9 адекватности прогноза (PASS, WARN в MODEL_CARD)
scripts/backtest.py        — engine, temp-БД, look-ahead isolation; Excel-зеркало --backtest
pytest                     — 91 тест (вкл. test_dag: DAG-гейт + iterate=1 + whitelist
                             колец; self-обёртки релаксации не считаются кольцами)
verify_model.py            — behavioral: монотонность, operating leverage, gate при EBITDA<0
Статус 20.11: книги сходятся с холодного старта (BS identity = 0 все годы),
              проценты книги vs engine Δ1–2.3% (rusal), рейтинги = АКРА (откл. 0)
```

---

# Приложения

## A. Инварианты, которые не должны нарушаться никогда

1. `BS identity = 0`, `CF bridge = 0` — все годы, обе формы представления.
2. Corkscrew-замыкания: PPE / Debt / Equity / Lease / Tax — `close = open + flows ± FX`.
3. RC ≤ limit; penalty = 0 в base (исчезновение штрафного транша — сигнал проверить gate).
4. Нет flat-макропутей в base (каждый фактор с методом и источником).
5. Формулы ≤ 300 символов; литералы только структурные [НОРМ].
6. Источники у 100% макропрогнозных ячеек (01_Macro J/K, теги).
7. Движки: структура P&L в ±3 п.п. (sync gate).
8. External ratings: отклонение модели от агентств — в листе, не в голове.

## B. Словарь символов

| символ | смысл |
|---|---|
| t, (t−1) | текущий / предыдущий год |
| LME_Al(t) | цена LME алюминий, базовый сценарий |
| F_s(t) | макро-фактор цены сегмента s |
| anchor_s | стартовый якорь цены сегмента (LME-базис базового года) |
| mix(t) | PGM-бленд 0.72·Pd + 0.28·Pt |
| recon(t) | прочая выручка (VAP/фольга/перепродажа) |
| fx_blend | (USDRUB_base/USDRUB_t)^0.7 — ослабление рубля снижает USD-затраты |
| cbrc | денежные средства до решений по revolver (cash before RC) |
| defer | отложенный проектный CapEx (иерархия Uses) |
| gate | гейт рынка срочного долга (1=открыт) |
| n1..n3 | нотчи опор П1..П3 на шкале 1..18 |
| adj | бизнес-корректировка итогового нотча (±2) |
| λ (wc_lambda) | скорость нормализации WC-дней, 0.6 |
| β_s (price_beta) | эластичность цены сегмента к фактору, 1.0 |
| EWA / MR / VECM | экспоненциальное взвешивание / mean reversion / векторная коррекция ошибок |
| TTC / PIT | through-the-cycle / point-in-time |

## C. Глоссарий (для начинающего специалиста)

**Сorkscrew («штопор»)** — винтовое ведение остатка: `конец = начало + приход − расход`. Стандарт учёта движимых величин (ОС, долг, капитал): если он не сходится — где-то потерялась проводка.

**Chain-link (цепное связывание)** — прогноз цены как произведение годовых темпов: `P(t) = P(0) × Π (1+g)`. Здесь g = β × Δln(макрофактор): цена движется за LME с эластичностью β.

**Recon-линия** — «остальная» выручка, которую нельзя отнести к моделируемым сегментам (фольга, перепродажа металла). База = факт минус сегменты; дальше растёт вместе с сегментами.

**Opening-balance convention** — все расчёты года опираются на остатки начала года, а не на внутригодовые «текущие» значения. Делает модель ацикличной (DAG): нет ячеек, которые ссылаются сами на себя.

**Плаг (plug)** — переменная, закрывающая неувязку по замкнутой формуле (не подбором). Здесь: потребность в фондировании `need = MAX(0, min_cash − касса_до_решений)` — каска всегда ≥ минимума, разница покрывается RC/траншем.

**Гейт рынка долга** — условие, при котором компания вообще может занять: нет ковенант-бр, ICR выше порога, EBITDA положительна. Моделирует реальность: убыточному эмитенту рынок закрыт.

**S&U (Sources & Uses)** — таблица «откуда деньги / куда уходят» в 17_Debt. Иерархия Uses (D1): обязательные платежи → поддерживающий CapEx → проектный CapEx (режется при дефиците) → дивиденды.

**TTC vs PIT** — «через цикл» vs «по факту точки». Агентства нормализуют метрики к среднецикловым (TTC), модель в точке (PIT) — отсюда системная разница в рейтингах.

**Нотч (notch)** — одна ступень рейтинговой шкалы (BBB+ → BBB). Корректировки и отклонения измеряются в нотчах.

**Суверенный потолок** — практика: рейтинг эмитента редко выше суверена страны. РФ: BBB+ intl = AAA(RU); ниже — нотч в нотч.

**Sanity bounds** — предохранители от вырождения (долг/выручка ≤ 10, активы ≤ 1e12): при пробое прогон останавливается (fail-fast), а не молча пишет мусор.

**SSOT (single source of truth)** — один файл-источник значений (macro_scenarios.yaml), из которого питаются оба движка; в книге и БД значения не правятся руками.

---

> История версий: v1 (август 2026, первый аудит) → v2.2 (BS no-plug, CF-полнота) → v2.3 (сегментная выручка, ковенанты, cost_shock-задел) → **v2.4 (18-19.11: макро-SSOT с источниками, компонентный COGS, иерархия Uses, PGM-микс, Euribor-базис, plausibility-гейт, 34_Rating: три опоры + Business Risk + outlook + сверка с агентствами)**.
