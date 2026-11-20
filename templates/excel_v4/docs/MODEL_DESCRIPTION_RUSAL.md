# Модель UC RUSAL: полное описание

**Версия:** v5.8 (26 октября 2026)
**Тип:** корпорат, metals, 3 сегмента
**Горизонт:** 2026E-2028E (3 года)
**Валидация:** BS=0, 10/10 тождеств, 1015 формул пересчитаны (0 расхождений)
**Аудит:** 9 раундов (v4-v9+), все блокеры закрыты

---

## 1. Профиль компании

| Параметр | Значение |
|----------|---------|
| Полное название | UC RUSAL International PJSC |
| Отрасль | Metals & Mining (алюминий) |
| Листинг | MOEX, HKEX |
| Валюта модели | USD |
| Выручка 2025 | 14,812 M$ |
| EBITDA 2025 | 1,053 M$ (margin 7.1%) |
| Чистый долг 2025 | 8,059 M$ |
| Рейтинг (модельный) | B+ / BB / B (Base 2026-2028) |

### Сегменты выручки

| Сегмент | Драйвер | Доля | Объём (kt) |
|---------|---------|------|-----------|
| Primary Aluminium | LME Aluminium | ~65% | 3,883 |
| Alumina | LME Alumina | ~15% | 7,697 |
| Other (VAP, foil) | EWA | ~20% | — |

### Особенности бизнес-модели

1. **Commodity exposure**: выручка на 80% привязана к LME Aluminium (β=0.653, t=1.62)
2. **Высокий leverage**: ND/EBITDA 7.2x (2026E), ковенанты нарушены во всех прогнозных годах
3. **FX exposure**: 35% выручки в CNY, 26% в RUB, 55% затрат в RUB
4. **Компонентный COGS**: 6 компонентов (material 45%, energy 25%, purchases 11%, labour 8%, other 11%)
5. **Weak calibration**: β Revenue~LME статистически незначим (t=1.62 < 2.57), модель применяет shrinkage к 1.0

---

## 2. Макросценарий

| Фактор | Base | Stress (-20%) | Severe (-40%) |
|--------|------|---------------|---------------|
| LME Aluminium, $/t | 2,800 | 2,240 | 1,680 |
| LME Alumina, $/t | 568 | 455 | 341 |
| USD/RUB | 85 | 98 | 85 |
| USD/CNY | 7.0 | 7.3 | 7.0 |
| Brent, $/bbl | 70 | 56 | 42 |
| CPI RU | 7.0% | 9.0% | 12.0% |
| PPI RU | 3.0% | 5.0% | 8.0% |

Переключатель: Control_Panel!C5 (1=Base, 2=Stress, 3=Severe).
Механика: 01_Macro → IF(CP!C5=1,Base,IF(CP!C5=2,Stress,Severe)) → все расчётные листы.

---

## 3. Калибровка параметров

### 3.1 Из МСФО 2023-2025 (03_Assump EWA)

| Параметр | Значение | Формула | Источник |
|----------|---------|---------|---------|
| COGS ratio | 81.6% | AVERAGE(ABS(COGS/Rev) за 3 года) | МСФО ОПУ |
| SGA ratio | 7.65% | AVERAGE(SGA/Rev за 3 года) | МСФО ОПУ |
| DA rate | 9.10% | AVERAGE(DA/PPE_net за 3 года) | МСФО прим. 11 |
| CapEx / DA | 2.22 | AVERAGE(CapEx/DA за 3 года) | МСФО ОДДС |
| DSO | 38 дней | AVERAGE(AR/Rev×365) | МСФО ОФП/ОПУ |
| DIH | 143 дня | AVERAGE(INV/COGS×365) | МСФО ОФП/ОПУ |
| DPO | 49 дней | AVERAGE(AP/COGS×365) | МСФО ОФП/ОПУ |

### 3.2 Эконометрика (01_Macro, в книге)

| Параметр | Значение | Формула Excel |
|----------|---------|--------------|
| β (Revenue ~ LME Al) | 0.653 | SLOPE(Δln_Rev, Δln_LME) |
| R² | 0.310 | RSQ() |
| SE(β) | 0.403 | STEYX()/STDEV() |
| N | 7 | COUNT() |
| t-stat | 1.62 | β/SE (< 2.57 при df=5) |
| β adjusted (shrinkage) | 0.719 | β×w + 1×(1-w), w=MIN(1,t/2) |

### 3.3 Компоненты себестоимости (из МСФО прим. 6a)

| Компонент | Доля | Драйвер |
|-----------|------|---------|
| Material (alumina+raw) | 45.2% | Vol × alumina_price × norm |
| Purchases (primary Al) | 10.6% | Vol × LME |
| Energy | 25.3% | Vol × PPI × FX |
| Labour | 8.2% | Vol × CPI × FX |
| Other (transport) | 10.8% | Vol × PPI × FX |
| D&A in COGS | 0% | DA отдельно (вне COGS) |

### 3.4 Долговые параметры (из Raw_IFRS / договоров)

| Параметр | Значение | Источник |
|----------|---------|---------|
| RC лимит | 2,500 M$ | [ДОГОВОР] |
| RC ставка | 14% | [ДОГОВОР] + КС ЦБ |
| Min cash | 500 M$ | [ОЦЕНКА] |
| Spread base | 4% | [ДАННЫЕ] рыночный |
| Target ND/EBITDA | 3.5x | [ОЦЕНКА] |
| Commitment fee | 0.5% | [ДОГОВОР] |
| Penalty rate | 24% | [НОРМ] штраф при нарушении |

---

## 4. Ключевые формулы

### 4.1 Выручка
```
Method 1 (segment): Revenue = Σ(Vol × Price / 1000) + Reconciliation
Method 2 (macro_ols): Rev(t) = Rev(t-1) × exp(β_adj × Δln(LME))
β_adj = IF(t<2, β×w + 1×(1-w), β)  // shrinkage к 1.0
```

### 4.2 COGS (компонентный)
```
Material = Vol × (alumina_norm × alumina_price + fixed_$/t) / 1000
Energy = Vol × (1 + PPI) × (1 + FX_chg × pass_through)
COGS_total = Σ components × (1 + PPI_beta × PPI × dampening)
```

### 4.3 Долговой модуль (closed-form plug)
```
cash_before_RC = CFO + CFI + CFF_no_RC
need = MAX(0, min_cash - cash_before_RC)
RC_draw = MIN(need, RC_limit - RC_open)
new_term = MAX(0, need - RC_draw)  // penalty rate если ковенант нарушен
```

### 4.4 Налог (IAS 12)
```
Current = MAX(taxable × rate, EBT × min_rate)
Tax_dep = tax_gross / tax_UL × accel_factor
Deferred = ΔDTL(PPE timing) - ΔDTA(NOL + carry-forward)
Total = Current + Deferred  // на PL как -ABS(Total)
```

### 4.5 Рейтинг (S&P 4-factor, 17 ступеней)
```
Score = w_lev × Leverage + w_cov × Coverage + w_prof × Profitability + w_liq × Liquidity
Final = MAX(0, MIN(100, Score + ind_adj + size_adj))
Rating = IF(Final≥90,"AAA",IF(Final≥85,"AA+",... ,IF(Final≥12,"CCC","D")))
```

---

## 5. Прогноз (макровинтаж 2026-11-18: LME Al base 3 250/3 050/2 900, USD/RUB 85/95/99, ЦБ 14.6/11.5/9.0)

| Показатель | 2025 | 2026E | 2027E | 2028E |
|-----------|------|-------|-------|-------|
| Выручка, M$ | 14,812 | 17,792 | 16,697 | 15,876 |
| EBITDA, M$ | 1,053 | 3,920 | 3,429 | 2,883 |
| Чистая прибыль | -455 | 2,203 | 1,566 | 1,329 |
| EBITDA margin | 7.1% | 22.0% | 20.5% | 18.2% |
| ND/EBITDA | 7.7x | 1.7x | 1.8x | 2.1x |
| ICR | — | 4.2x | 3.8x | 3.3x |
| Долг, M$ | 9,602 | 9,743 | 8,438 | 8,154 |
| Cash | 1,543 | 3,101 | 2,269 | 2,152 |
| Eff tax rate | — | 25% | 26% | 26% |
| Рейтинг (нац. шкала) | — | A+(RU) | A+(RU) | A+(RU) |

### Сценарии (из 40_Scen snapshots)

| | Base | Stress | Severe |
|---|---|---|---|
| EBITDA 2026 | 3,920 | 2,243 | 406 |
| EBITDA 2028 | 2,883 | 1,311 | -447 |
| NI 2026 | 2,203 | 525 | -1,353 |
| Рейтинг | A-/A/A- | BBB/BBB/BB | CCC/CCC/CCC |

### Экономическая интерпретация

**Base**: LME Al 3 250 (≈YTD-2026 Westmetall) → восстановление EBITDA до 22% маржи после провала 2025 (cost-shock). Делеверидж до 1.7x (ковенант 4.5x с запасом), проценты ↓ по пути ЦБ. К 2028 LME к среднему (2 900) → прибыль снижается — направление корректно.

**Stress** (LME −20%): EBITDA 1.3–2.2 млрд, NI положительный, рейтинг BBB — компания переживает без дефолта.

**Severe** (LME −40% до ~1 740, уровень 2020): EBITDA 2028 уходит в минус, кэш на полу min_cash, рейтинг CCC — стресс-сценарий честный.

---

## 6. Корксрои (9 штук)

| # | Corkscrew | Лист | Формула |
|---|-----------|------|---------|
| 1 | PPE (Gross/Dep/Net) | 15_PPE | Open+CapEx-Disp→Close; Dep SL |
| 2 | Debt Term | 17_Debt | Open-Mand+Refi+New-Vol→Close |
| 3 | Debt RC | 17_Debt | Open+Draw-Repay→Close |
| 4 | Lease (ROU+Liab) | 18_Lease | IFRS 16 corkscrew |
| 5 | Equity (RE) | 24_Equity | Open+NI-Div-Buyback→Close |
| 6 | WC (AR/INV/AP) | 16_WC | DSO/DIH/DPO × Rev/COGS |
| 7 | Tax basis PPE | 19_Tax | Отдельный UL, timing diff |
| 8 | Intangibles | 20_BS | Open×(1-amort_rate)→Close |
| 9 | Provisions | 20_BS | Open+Accrual-Util→Close |

---

## 7. Блоки модели (32 листа)

| Блок | Листы | Статус |
|------|-------|--------|
| Ввод | 00_Guide, 00_Cover, Control_Panel, 01_Macro, 02_Hist, 03_Assump, 05_Drivers, Raw_IFRS | ✅ |
| Движок | 10_Revenue, 11_Segments, 12_COGS, 13_SGA, 14_OtherIS, 15_PPE, 16_WC, 17_Debt, 18_Lease, 19_Tax, 20_BS, 21_PL, 23_CF, 24_Equity | ✅ |
| Отчёт | 30_Ratios, 31_Score, 32_Covenants, 33_RevStress, 35_Valuation, 40_Scen | ✅ |
| Контроль | 90_Checks, Model_Output, _Debt_Schedule, Changelog | ✅ |

---

## 8. Аудит

### Батарея проверок (статус 20.11):
1. `audit_corp_model.py`: **27 PASS, 0 FAIL** (E7 sanity bounds, H4 цвета, G1 OLS, E2 сетка годов с whitelist параметров)
2. `90_Checks`: все 12 тождеств = 0 все годы (BS, CF, PPE/Debt/Equity roll, ST/LT, Schedule, Interest, S&U, RC limit); **0 ячеек-ошибок Excel**
3. `sync_gate_corp.py` (Excel vs Python engine): **PASS** — структура ±3 п.п., уровни ±20%
4. `pytest`: **91/91** (вкл. test_dag: DAG-гейт, iterate=1)
5. Рейтинги = АКРА: A+(RU), отклонение 0; стресс-миграция A-→CCC (severe)
6. Итерационный расчёт включён (calcPr iterate=1, 1000/1e-4); книга — DAG;
   кольцевая зона с seed-механикой (SEED-блок 17_Debt r105+, engine base) и
   релаксацией (CP!L2 ω=0.3); проценты: opening-balance, транши — с года после
   выпуска, репрайсинг ставки транша — лаг 1Y (устройство 20.11, см.
   `docs/MODEL_MATH_FULL.md` §13.2a/13.5)
7. Пайплайн: build → fill → **finalize** (живой Excel recalc — последний шаг,
   без него кэши пустые и книга неверифицируема)

### Динамика аудитов v4 → 2.5.0:
- **v4–v9 (окт 26)**: K1 cached, G1 OLS, 40_Scen dynamic, tax/DAA fixes
- **2.4.0 (18.11)**: макро-SSOT (macro_scenarios.yaml), D1 Uses-иерархия,
  D2 PGM-микс, D4 WC partial adjustment, история LME Al исправлена
- **2.5.0 (20.11)**: seed-механика колец, книга DAG при iterate ON,
  синтетические транши (проценты с года после выпуска, ставка лаг 1Y),
  finalize hardening, 0 FAIL по обеим книгам

---

## 9. Ключевые риски модели

1. **Леверидж чувствителен к LME**: base ND/EBITDA 1.7–2.1x (ковенант 4.5x с запасом), но severe (LME 1 740) уводит EBITDA в минус → CCC; вывод держится на восстановлении LME Al к 3 250 в 2026 (старт = YTD Westmetall ✓).
2. **β незначим**: OLS на 7 годовых наблюдениях не определяет эластичность. Shrinkage смягчает, но не решает.
3. **Компонентный COGS**: alumina_norm и fixed_material — hard to verify, из отчётности напрямую не следуют. Ratio-COGS не предсказывает cost-shock (бэктест EBITDA MAPE 26.4% в шоковые годы).
4. **FX pass-through 70%**: экспертное допущение, чувствительность высокая.
5. **Reconciliation ~25%**: сегментная выручка покрывает 75% IS revenue. Оставшееся растёт пропорционально — грубо.
6. **Дивидендная политика**: equity накапливает почти весь NI (payout занижен) — делеверидж и кэш завышены относительно реальной политики En+; смотреть чувствительность через CP.
