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

## 5. Прогноз

| Показатель | 2025 | 2026E | 2027E | 2028E |
|-----------|------|-------|-------|-------|
| Выручка, M$ | 14,812 | 15,641 | 15,362 | 15,082 |
| EBITDA, M$ | 1,053 | 1,313 | 1,407 | 1,256 |
| Чистая прибыль | -455 | 242 | 114 | -39 |
| EBITDA margin | 7.1% | 8.4% | 9.2% | 8.3% |
| ND/EBITDA | 7.7x | 7.2x | 7.4x | 9.3x |
| ICR | — | 1.4x | 1.5x | 1.1x |
| Долг, M$ | 9,602 | 9,928 | 10,834 | 12,190 |
| Cash | 1,543 | 500 | 500 | 500 |
| Eff tax rate | — | 29% | 32% | 23% |
| Рейтинг | — | B+ | BB | B |

### Сценарии (из 40_Scen snapshots)

| | Base | Stress | Severe |
|---|---|---|---|
| EBITDA 2026 | 1,313 | 144 | -2,179 |
| NI 2026 | 242 | -1,532 | -3,695 |
| Rating | B+/BB/B | D/D/D | D/D/D |

### Экономическая интерпретация

**Base**: LME 2,800 — EBITDA margin ~8%, ковенанты нарушены (ND/EBITDA 7.2x vs порог 4.5x). Долг растёт за счёт RC draw и penalty financing. Cash = min_cash (500).

**Stress** (LME -20%): EBITDA около нуля, чистый убыток >1.5 млрд/год. Rating D. Долг неуправляем.

**Severe** (LME -40%): EBITDA глубоко отрицательная. Фактический дефолт.

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

### Батарея проверок (все PASS):
1. K1: 2191/2191 кэшированных формул
2. B2: 1015 формул пересчитаны, 0 расхождений
3. C1: 10/10 тождеств (BS, CF, PPE roll, Debt roll, Equity roll, ST/LT, Schedule, Interest, S&U, Iteration)
4. D4: Eff tax rate 29%/32%/23% — в диапазоне [0;50%]
5. E1: Сверка с историей O/P/Q = 0/0/0
6. F3: 43 литерала (was 204)
7. G1: SLOPE/RSQ/INTERCEPT + weak calibration flag
8. H1: 40_Scen 7 факторов, переключатель работает
9. H2: 0 констант в прогнозных колонках
10. I1: 0 непомеченных параметров CP
11. J1: Один статус на обложке ("⚠ КОВЕНАНТЫ НАРУШЕНЫ")

### Динамика аудитов v4-v9:
- **v4**: K1 cached, G1 OLS, H1 dynamic 40_Scen
- **v5**: HI cols O/P/Q (218+ refs), SGA 14.4%→7.65%
- **v6**: Cover status, CapEx sign, 17-step rating
- **v7**: Single cover status, all CP labeled
- **v8**: Nornickel OLS, CP summary cols
- **v9**: Tax rate normalized (DTA carry-forward), ratios history

---

## 9. Ключевые риски модели

1. **ND/EBITDA 7.2x**: ковенанты нарушены при ANY LME price. Модель предполагает debt availability (CP!C74=1) — это ключевое допущение.
2. **β незначим**: OLS на 7 годовых наблюдениях не определяет эластичность. Shrinkage смягчает, но не решает.
3. **Компонентный COGS**: alumina_norm и fixed_material — hard to verify, из отчётности напрямую не следуют.
4. **FX pass-through 70%**: экспертное допущение, чувствительность высокая.
5. **Reconciliation ~25%**: сегментная выручка покрывает 75% IS revenue. Оставшееся растёт пропорционально — грубо.
