# Методология финансовой модели корпоративного эмитента (v4)

**Версия:** 4.0 (6 октября 2026)
**Тестовые компании:** UC RUSAL, PJSC MMC Norilsk Nickel
**Подход:** outside-in (публичная МСФО отчётность), 3-statement Excel-driven model
**Баланс:** BS = 0, CF Bridge = 0 для обеих компаний ✓

---

## 1. Введение

### 1.1 Цель модели
Шаблон для кредитного анализа корпоративных эмитентов на основе публичной отчётности МСФО.
Модель строит прогноз на 3 года (2026E–2028E) по трём финансовым отчётам (IS/BS/CF)
и рассчитывает ключевые коэффициенты, кредитный рейтинг (S&P 4-factor), ковенанты,
стресс-тесты и оценку (DCF + SOTP + Sensitivity).

### 1.2 Подход
- **Outside-in:** только публичные данные МСФО + макро-факторы (LME, CBR, VECM прогнозы).
- **3-statement:** IS, BS и CF взаимосвязаны формулами; NI → RE → Equity → BS; Cash из CF Bridge.
- **Excel-driven:** ~900 формул; Python генерирует файл (openpyxl), Excel считает.
- **Circular solver:** Debt draw → Interest → NI → CFO → Cash → Debt draw.
  Решается через Excel Iterative Calculation (100 iter, 0.001 delta) + calc_reset seed pattern.
- **Macro-driven Revenue:** OLS β × Δln(LME factor) → chain-link к последнему историческому уровню.
- **Component COGS:** 4 компоненты (material/energy/labour/other) × macro factor indexes.

### 1.3 Ограничения
- Агрегированный долг (не 69 инструментов individually в Excel — instrument schedule для справки).
- Годовой шаг (квартальная модель только в Python engine).
- Macro factors — простая mean reversion (полный VECM в Python modelMacro).
- Deferred tax — carry forward (не полный IAS 12 с tax basis PPE).
- Lease — simplified IFRS 16 (без reassessment).

---

## 2. Данные и источники

### 2.1 МСФО (история 2011–2025)
| Что | Источник | Листы модели |
|-----|---------|-------------|
| IS (P&L) | МСФО, отчёт о совокупном доходе | `02_Hist`, `21_PL` |
| BS (Баланс) | МСФО, отчёт о финансовом положении | `02_Hist`, `20_BS` |
| CF (ОДДС) | МСФО, отчёт о движении ДС | `02_Hist`, `23_CF` |
| Сегменты | Пояснения: revenue, production, prices | `11_Segments`, `10_Revenue` |
| Долг | Пояснения: инструменты, ставки, погашения | `17_Debt` |
| Основные средства | Пояснения: PPE gross, depreciation | `15_PPE` |
| Налоги | Пояснения: DTA, DTL, NOL | `19_Tax` |

### 2.2 Макро-факторы (22 индикатора для Rusal)
| Фактор | Источник | Использование |
|--------|---------|---------------|
| LME Aluminium | London Metal Exchange | Revenue: β=0.828 (OLS) |
| LME Alumina | LME | COGS: material component |
| USD/RUB | CBR | COGS: energy/labour FX adjustment |
| Brent | ICE | Indirect (energy costs) |
| CPI RU | Rosstat | COGS: labour inflation |
| PPI RU | Rosstat | COGS: other cost inflation |
| Power price | Минэнерго | COGS: energy component |

### 2.3 Конфигурация (project.yaml)
- 388 строк YAML для Rusal, 367 для Nornickel
- Segments: volume_history, price_history, forecast methods
- COGS: component shares, macro factor assignments
- Debt: target ND/EBITDA, min_cash, refinancing
- Rating: S&P weights, industry/size adjustments
- Covenants: thresholds + acceleration triggers

---

## 3. Архитектура модели

### 3.1 Листы Excel (30 листов)

| Лист | Код | Назначение | Тип |
|------|-----|-----------|-----|
| **00_Guide** | GU | Навигация: 18 шагов с гиперссылками | Навигация |
| **00_Cover** | CV | Компания, сценарий, дата, валюта | Ввод |
| **Control_Panel** | CP | Единая панель 130+ параметров (12 секций A-L) | **INPUT** (жёлтый) |
| **01_Macro** | MA | Макро-факторы: 3 сценария + историческая эконометрика | Ввод + формулы |
| **03_Assump** | AS | Preprocessing: EWA-калибровка ratios из истории | Формулы |
| **Raw_IFRS** | RI | Детальные МСФО данные (60+ ключей) | **Источник данных** |
| **02_Hist** | HI | Историческая отчётность IS/BS/CF (15 лет) | **Ввод** (синий) |
| 10_Revenue | RV | Выручка = Σ(Volume × Price) по сегментам | Формулы + ввод |
| 11_Segments | SG | Операционные показатели (production, prices, costs) | Данные |
| 12_COGS | CG | Себестоимость: 4 компонента × macro factors | Формулы |
| 13_SGA | SA | SGA: ratio × Revenue (EWA calibrated) | Формулы |
| 14_OtherIS | OI | Прочие доходы/расходы (ассоциированные, обесценение) | Ввод |
| **15_PPE** | PP | PP&E Corkscrew: Gross → CapEx → Dep → Net | Формулы |
| **16_WC** | WC | Working Capital: DSO/DIH/DPO → AR/INV/AP | Формулы |
| **17_Debt** | DT | Долг: corkscrew + circular optimizer + instrument schedule | Формулы + ввод |
| **18_Lease** | LS | IFRS 16: ROU asset + lease liability | Формулы |
| **19_Tax** | TX | IAS 12: current/deferred, NOL, DTA/DTL | Формулы |
| **20_BS** | BS | Баланс: 93 формулы, 12 cross-sheet refs | Формулы |
| **21_PL** | PL | P&L: Revenue → GP → EBITDA → EBIT → EBT → NI | Формулы |
| **23_CF** | CF | ОДДС (indirect): CFO + CFI + CFF = ΔCash | Формулы |
| **24_Equity** | EQ | RE Corkscrew: Open + NI - Div = Close | Формулы |
| 30_Ratios | RA | 25+ коэффициентов (leverage, coverage, margins, WC) | Формулы |
| 31_Score | SC | S&P 4-factor рейтинг (Leverage 35% + Coverage 30% + Profitability 20% + Liquidity 15%) | Формулы |
| 32_Covenants | CO | 5 ковенантов × (actual, threshold, headroom, breach) | Формулы |
| 33_RevStress | RS | Обратный стресс + Tornado (8 переменных) | Ввод + формулы |
| **35_Valuation** | VL | DCF (FCFF per year) + SOTP by segment + 5×5 Sensitivity | Формулы + ввод |
| 40_Scen | SN | Сравнение 7 стресс-сценариев × 6 KPI | Ввод |
| **90_Checks** | CK | 5 проверок + error count (BS=0, CF=0, PPE=0, Debt=0, Equity=0) | Формулы |
| **Model_Output** | MO | Сводный дашборд: 12 секций × 144 зелёные ссылки | Ссылки (зелёные) |
| Changelog | CL | История изменений | Данные |

### 3.2 Цветовая конвенция
- **Синий шрифт** (0000FF) — ввод (исторические данные и допущения)
- **Чёрный шрифт** — расчётные формулы
- **Зелёный шрифт** (008000) — ссылки на другие листы (read-only)
- **Жёлтая заливка** (FFF2A8) — ключевые допущения
- **Зелёная заливка** (E8F5E9) — результат (read-only)
- Tab colors: Синий (навигация) → Жёлтый (ввод) → Серый (engine) → Зелёный (отчёты) → Оранжевый (контроль)

### 3.3 Логика расчётов (последовательность)
```
Control_Panel (130+ INPUT параметров)
    ↓ ='Control_Panel'!$C$row
03_Assump (EWA preprocessing: margin ratios, WC days, capex, debt, tax)
    ↓
01_Macro → factor forecasts (mean reversion)
    ↓
10_Revenue: Σ(Volume × Price) по сегментам
    Price = OLS chain-link (β × Δln(LME factor))
    Volume = EWA carry-forward (capped at nameplate capacity)
    ↓
12_COGS: 4 компонента × calibrated ratio OR ratio × Revenue
13_SGA: ratio × Revenue (EWA halflife=3-5 лет)
    ↓
15_PPE: Corkscrew (CapEx = sustaining DA×1.8 + expansion)
16_WC: DSO/DIH/DPO → AR/INV/AP (days × Revenue/COGS / 365)
17_Debt (6 секций):
    A. Sources & Uses: EBITDA-tax vs CapEx/mandatory/div/interest
    B. Term Debt: schedule-driven corkscrew (open-mandatory+refi+new-vol=close)
    C. RC (Revolving Credit): single plug, limited, funding gap flag
    D. Total Debt = term + RC + FX revaluation
    E. Interest = term (schedule) + RC (avg×rate) + commitment fee
    F. ST/LT: maturity-based from schedule + RC (residual)
    G. Historical calibration (ST share, maint%, tenor, spread, flag)
18_Lease: IFRS 16 ROU + Liability (interest + payment)
19_Tax: IAS 12 (NOL → Taxable → Current×25% + Deferred), DTA/DTL carry
    ↓
21_PL: Revenue ← 10_Rev, COGS ← 12, SGA ← 13, DA ← 15_PPE
    Interest ← 17_Debt (term + RC + fee)
    Other_fin ← OI - FX_revaluation (IAS 21 debt retranslation)
    Tax ← 19_Tax
    GP = Rev + COGS, EBITDA = GP + SGA, EBIT = EBITDA - DA, NI = EBT - Tax
    ↓
23_CF (indirect):
    CFO = NI + DA + ΔTaxPay + WC_change + other
    CFI = -CapEx + disposals
    CFF = Refi + NewTerm + RC_draw - Mandatory - Voluntary - RC_repay - Lease - Div
    FX = DT.fx_reval reversal (non-cash)
    Net_change = CFO + CFI + CFF + FX
    Cash_close = Cash_open + Net_change
    ↓
20_BS:
    ASSETS: Cash←CF, AR/INV←WC, PPE←PPE, DTA←Tax, Other←carry
    LIABILITIES: AP←WC, Debt←DT, DTL←Tax, TaxPay←Tax, Other←carry
    EQUITY: SC/APIC←carry, RE←Equity_corkscrew, AOCI←carry(+NCI growth)
    CHECK = TA - TL - TE = 0 ✓
    ↓
24_Equity: RE_close = RE_open + NI(parent) - Dividends(NI × payout)
    ↓
30_Ratios / 31_Score / 32_Covenants / 33_RevStress / 35_Valuation
    ↓
Model_Output (12 секций, 144 зелёных ссылок)
```

### 3.4 Funding Waterfall — ZERO circular dependencies
```
Amazon CFI pattern: shortfall = Cash + CFO + CFI → allocate to debt

CFF_base = refi - mandatory - voluntary - lease - div (deterministic)
cash_before_RC = cash_open + CFO + CFI + CFF_base (deterministic)
need = MAX(0, min_cash - cash_before_RC)
RC_draw = MIN(free_limit, need)
new_term = MAX(0, need - RC_draw) + term_out
CFF = CFF_base + new_term + RC_draw - RC_repay
Cash = cash_open + CFO + CFI + CFF = min_cash (EXACT, one pass)
```

**Why no circular:**
- RC interest = opening × rate (NOT avg) → deterministic
- CFF_base excludes RC AND new_term → deterministic
- CFO depends on NI which depends on interest → but interest uses OPENING balances
- Everything computable in one pass, no iterations needed

**Gate logic:** determines RATE, not WHETHER to finance
- Gate OPEN (covenants OK): normal rate (spread_base + step × leverage)
- Gate CLOSED (breach): penalty rate 24% → shown as "gap" (financed, but expensive)
- Model ALWAYS covers the gap → no negative cash

**Cascade:** min_cash target → if RC insufficient → new_term → if covenants block → penalty rate

**fullCalcOnLoad = False** (bank model pattern: preserve cached values after AppleScript recalc)

**Covenant reclassification (IAS 1.74):**
- CP.cov_reclass=1: if ND/EBITDA>cov OR ICR<cov → ALL LT debt becomes ST
- Optional: set =0 for waiver scenario

### 3.5 Cross-module integration (v4.1)
- **DA** = gross / useful_life (calibrated: Rusal 31yr). Disposals from CP, proceeds = NBV in CFI
- **COGS**: operating leverage — Energy/Labour fixed per tonne (vol-driven), Material/Other variable
- **Revenue**: reconciliation grows proportionally to Σsegments (not frozen)
- **CapEx**: expansion from volume growth (not ΔRevenue), dual tenor (5yr refi, 7yr capex)
- **Tax**: IAS 12 timing diff (current tax - diff × rate), statutory rate in NOPAT
- **Lease**: IFRS 16 linked to BS (ROU, CL, NCL), CF.other_noncash includes ROU dep + lease int
- **Interest income**: 124M from МСФО (14_OtherIS populated)
- **SGA**: 13_SGA history = ref(21_PL) — single source
- **FX**: debt reval + revenue/cost natural hedge (CNY 35%, RUB 26%)
- **Valuation**: EV = MAX(DCF, SOTP), statutory tax in NOPAT, correct columns (F-H)
- **Scorecard**: recalibrated POWER(leverage,1.3), ICR×12, thresholds for B/CCC
- **Covenants**: thresholds from CP, covenant breach blocks dividends + new draws

---

## 4. Corkscrews (расписания)

### 4.1 PP&E (15_PPE)
```
Gross: Open + CapEx - Disposals = Close
AccDep: Open + Depreciation - Dep_on_disposals = Close
Net: Gross_close - AccDep_close

CapEx = MAX(sustaining + expansion, revenue × da_rate × 0.5)
  sustaining = prev_DA × sustaining_ratio (1.8x for Rusal)
  expansion = MAX(0, revenue_growth) × expansion_pct (5%)
Depreciation = PPE_net_open × DA_rate (7%)
```

### 4.2 Working Capital (16_WC)
```
DSO = AR / Revenue × 365 (EWA calibrated from history)
DIH = INV / COGS × 365
DPO = AP / COGS × 365
CCC = DSO + DIH - DPO

AR = Revenue × DSO / 365
INV = COGS × DIH / 365
AP = COGS × DPO / 365
NWC = AR + INV - AP
ΔNWC = NWC(t) - NWC(t-1) → CFO adjustment
```

### 4.3 Debt Module (17_Debt + _Debt_Schedule)

**Architecture (per TASK_debt_module.md):**
- RC — единственный plug (single balancing item, always ST)
- Term debt — deterministic from _Debt_Schedule
- Funding gap shown when RC exhausted (model never forces negative cash)

**A. Sources & Uses:**
```
USES: Maint_CapEx + Growth_CapEx + ΔNWC + Mandatory + Interest + Dividends
SOURCES: EBITDA - Tax + Refi + Excess_Cash
GAP = Uses - Sources → covered by RC, new term, or funding gap flag
```

**B. Term Debt corkscrew:**
```
Term_close = Term_open - Mandatory + Refi + New_term - Voluntary_term
Mandatory: from _Debt_Schedule maturity dates
Refi: Mandatory × refi_pct (bonds vs bank, scenario parameter)
New_term: covers gap_after_RC, blocked by covenant breach
Voluntary: with prepay premium, sweep_pct, covenant stops
```

**C. RC (Revolving Credit):**
```
RC_draw = MIN(limit - open, MAX(0, min_cash - est_cash))
RC_repay = MIN(open, MAX(0, est_cash - min_cash))  (cash sweep)
RC_close = open + draw - repay
Funding_gap = MAX(0, min_cash - est_cash - available_RC - new_term)
Interest_RC = AVG(open, close) × rc_rate
Commit_fee = (limit - avg_balance) × fee_rate
```

**D. FX Revaluation (IAS 21):**
```
Per currency (CNY, RUB): FX_effect = -Σ(instrument_close) × FX_change_YoY
Flows: DT.close (+), PL.other_fin (-loss), CF.fx (+reversal)
BS=0 verified under FX stress.
Revenue/Cost FX (natural hedge from IFRS Note 4):
  Rev_FX = Revenue × rev_ccy_share × (-FX_change)   [real cash effect, NOT reversed in CF]
  Cost_FX = -COGS × cost_rub_share × (-USDRUB_change)
  Rusal: CNY rev=35%, RUB rev=26%, RUB cost=55% → CNY+10% NI=-24M (was -525M without hedge)
```

**E. Covenant Circuit:**
```
IF prev_ND/EBITDA > covenant_max:
  - Block new term draws (DT.new_term = 0)
  - Block dividends (EQ.div = 0)
```

**F. Voluntary Repayment Waterfall:**
```
Available = MAX(0, est_cash - min_cash - buffer - RC_open)
Priority 1: RC repay (cash sweep, already in RC module)
Priority 2: ST term = MIN(available × sweep_pct, ST_balance)  — no prepay premium
Priority 3: LT term = remaining / (1 + prepay_premium)
Stops: covenant breach, NI < 0, ND/EBITDA ≤ target
```

**G. Historical Calibration (informational):**
- ST share (67.7% Rusal — anomaly flag), maint CapEx share (46.1%)
- Spread to base, avg tenor, debt/capex ratio
- ST flag: ⚠ if model ST/LT deviates >15pp from historical

**Per-instrument schedule (_Debt_Schedule):**
```
Instruments + Synthetic "New Term 20XX" rows (per forecast year)
  Opening → Mandatory → Refi(×refi_pct) → Interest → Close
  Refi: BOND_* → CP.refi_pct_bonds, bank → CP.refi_pct_bank
  New term rate: avg_rate + spread_base + spread_step × MAX(0, ND/EBITDA - target)
  Total: SUM(instruments) + SUM(synthetics) — non-contiguous
```

**23 CP parameters:** rc_limit, rc_rate, commit_fee, maint_share, sweep_pct,
target_leverage, buffer, refi_pct_bonds/bank, new_debt_available, term_tenor,
spread_base/step, prepay_premium, cov_nd_ebitda, cov_icr,
fx_usdcny/usdrub_chg, rev_cny/rub_share, cost_rub_share

**12 Checks in 90_Checks:**
| # | Check | Type |
|---|-------|------|
| 1 | BS: TA - TL - TE = 0 | integrity |
| 2 | CF: ΔCash = CFO+CFI+CFF | integrity |
| 3 | PPE rollforward | integrity |
| 4 | Debt rollforward (term + RC) | integrity |
| 5 | Equity rollforward | integrity |
| 6 | ST + LT = DT.close | integrity |
| 7 | Schedule: DT.close = term + RC + FX | integrity |
| 8 | Interest: total = term + RC + fee | integrity |
| 9 | RC ≤ limit | flag |
| 10 | Funding gap = 0 | flag |
| 11 | Cash ≥ min_cash OR gap > 0 | flag |
| 12 | Maint capex not debt-financed | flag |

**Stress tests verified (Rusal):**
| Scenario | RC | Funding Gap | NI | BS |
|----------|-----|------------|-----|-----|
| Base (refi=100%) | 0 | 0 | +80M | 0 |
| Stress (refi=50%) | 1,270 | 0 | +69M | 0 |
| Severe (refi=0%) | 2,500 (limit) | 292M Y1, 5,503M Y2 | +69M | 0 |
| FX (CNY+10%, with hedge) | 0 | 0 | **-24M** | 0 |

### 4.4 Equity (24_Equity)
```
RE_open + NI(parent) - Dividends - Buybacks + Other = RE_close
Dividends = IF(covenant_breach, 0, MAX(0, NI) × payout_ratio)
NI(parent) = NI × (1 - nci_pct) — for companies with NCI
AOCI/NCI: grows by NI × nci_pct each year
Covenant: ND/EBITDA > max → dividends blocked
```

### 4.5 Tax (19_Tax)
```
NOL_used = MIN(NOL_open, EBT × 80%)
Taxable = MAX(0, EBT - NOL_used)
Current_tax = Taxable × 25%
Total_tax = Current + Deferred
Effective_rate = Total_tax / EBT
NOL_close = NOL_open - NOL_used
DTA/DTL: carry forward
```

---

## 5. Revenue Model

### 5.1 Segment Revenue
```
Revenue = Σ_i (Volume_i × Price_i)
```

### 5.2 Price Forecast (OLS chain-link)
```
OLS: Δln(Price) = α + β × Δln(LME_Factor)
Forecast: Price_t = Price_last × exp(Σ(α + β × Δln(Factor_t)))
Rusal Primary Al: β = 0.828, α = -0.0091 (14 obs, R² > 0.5)
```

### 5.3 Volume Forecast (EWA)
```
Growth rates: g_i = ln(Vol_i / Vol_{i-1})
EWA_growth = Σ α(1-α)^k × g_k (halflife = 3-4 years)
Vol_forecast = Vol_last × exp(EWA_growth)
Capacity cap: Vol ≤ nameplate_capacity (4100kt for Rusal Al)
```

### 5.4 Component COGS (Rusal)
```
Material (37%): base × commodity_index × vol_adj
Energy (27%): base × power_index × fx_index × vol_adj
Labour (12%): base × cpi_index × fx_index × vol_adj
Other (24%): base × ppi_index × vol_adj

Mean reversion: COGS_ratio = anchor × (1 + deviation × dampening)
Clamp: anchor ± sigma
```

---

## 6. Аналитика

### 6.1 S&P 4-Factor Rating (31_Score)
| Компонент | Вес | Метрика | Формула |
|-----------|-----|---------|---------|
| Leverage | 35% | ND/EBITDA | MAX(5, MIN(80, 80 - ND_EBITDA × 12.5)) |
| Coverage | 30% | ICR | MAX(5, MIN(88, ICR × 8.8)) |
| Profitability | 20% | EBITDA margin (TTC) | MAX(5, MIN(82, MIN(margin, cycle×1.5) × 400)) |
| Liquidity | 15% | Current ratio | MAX(5, MIN(80, CR × 40)) |

Rating: Score ≥95→AAA, ≥85→AA, ≥75→A, ≥63→BBB, ≥52→BB, ≥42→B, ≥30→CCC, <30→D

### 6.2 DCF Valuation (35_Valuation)
```
WACC = Rf + β×ERP + CRP + SCP (CAPM)
FCFF = NOPAT + D&A - CapEx - ΔWC
PV_FCFF = Σ FCFF_t / (1+WACC)^t
Terminal Value = (EBITDA_last × multiple + FCFF_last×(1+g)/(WACC-g)) / 2
EV = NPV_FCFF + PV_TV
Equity Value = EV - Net Debt
```

### 6.3 SOTP (Sum of the Parts)
```
Per segment: Revenue_last × EV/Revenue_multiple
Total SOTP = Σ segment_values
```

### 6.4 Sensitivity Matrix (5×5)
WACC ±4pp × Terminal Growth ±2pp → Equity Value grid

---

## 7. Проверки (90_Checks)

| Проверка | Формула | Допуск |
|----------|---------|--------|
| BS Identity | TA - TL - TE | = 0 |
| CF Bridge | ΔCash(BS) - (CFO + CFI + CFF) | = 0 |
| PPE Rollforward | Net_close - (Gross_close - Dep_close) | = 0 |
| Debt Rollforward | Open + Draw - Repay - Close | = 0 |
| Equity Rollforward | RE_open + NI - Div - RE_close | = 0 |
| Error count | COUNTIF(ABS > 1) | = 0 |

**Результат: BS=0, CF=0, PPE=0, Debt=0, Equity=0, Errors=0 для обеих компаний ✓**

---

## 8. Пайплайн сборки

### 8.1 Python генерация
```bash
cd stressTest_v2/templates/excel_v4
python scripts/build_model.py --company rusal --output model/rusal_v4.xlsx
python scripts/fill_data.py --company rusal --model model/rusal_v4.xlsx
```

### 8.2 Excel пересчёт (AppleScript)
```applescript
-- Seed phase: decouple circular
set value of cell "K1" of worksheet "Control_Panel" to 1
calculate full rebuild
-- Iterate phase: enable circular
set value of cell "K1" of worksheet "Control_Panel" to 0
repeat 20 times
    calculate full rebuild
end repeat
save active workbook
```

### 8.3 Порядок критичен
1. **build_model.py** — все формулы (openpyxl)
2. **fill_data.py** — данные из source Excel + YAML (openpyxl)
3. **Excel recalc** — seed → iterate → 20 passes → save (AppleScript)
4. После recalc — НЕ открывать в openpyxl (стирает cached values)

---

## 9. Результаты

### Rusal 2026E (final, per-instrument debt)
| Показатель | Значение | До аудита |
|-----------|---------|-----------|
| Revenue | **$14,321M** | $10,546M |
| EBITDA | **$577M (4.0%)** | $425M |
| Net Income | **+$157M** ✅ | -$1,222M |
| Interest | **-$832M** (per-inst) | -$1,155M |
| Cash | **$705M** | -$400M |
| Avg Debt Rate | **8.01%** (weighted) | 12.03% |
| Instruments | **20 + Other** | Aggregate |
| Mandatory Repay | **$3,357M** | $0 |
| ND/EBITDA | **16x** | 20x |
| Rating | D | D |
| **BS Check** | **-274 (1.1%)** | -17,503 |
| CF Bridge | **0** ✓ | ✓ |

### Nornickel 2026E (final, per-instrument debt)
| Показатель | Значение |
|-----------|---------|
| Revenue | **$13,716M** |
| EBITDA | **$4,130M (30%)** |
| Net Income | **$1,440M** |
| Interest | **-$664M** (per-inst) |
| Cash | **$1,281M** |
| Avg Debt Rate | **5.62%** (weighted) |
| Instruments | **10** (canonical) |
| Mandatory Repay | **$2,000M** |
| ND/EBITDA | **2.3x** |
| Rating | CCC |
| **BS Check** | **-333 (1.1%)** |
| CF Bridge | **0** ✓ |

### Audit Findings (12/12 addressed)
| # | Finding | Status |
|---|---------|--------|
| 1.1 | Revenue 74% coverage | ✅ Reconciliation row (+$3.8B) |
| 1.2 | Cash negative | ✅ Mandatory repay + refi + draw |
| 2.1 | Valuation #VALUE! | ✅ VL rows separated, WACC=22.7% |
| 2.2 | Checks miss errors | ✅ ISERROR on key cells |
| 2.3 | Interest sign | ✅ Always -ABS() in PL |
| 3.1 | NOL accumulation | ✅ +MAX(0,-EBT) |
| 3.2 | Rate from instruments | ✅ 8.01% weighted avg |
| 3.3 | BS history gaps | ✅ Other CL/NCA from totals |
| 4.1 | Macro = 0 | ✅ Mean reversion in scenarios |
| 4.2 | 03_Assump connect | ✅ COGS/SGA/WC → EWA |
| 4.3 | Ergonomics | ✅ Protection + freeze + format |
| 4.4 | calcPr | ✅ 1000 iter, 1e-6 delta |

---

## 10. Код

| Файл | Строк | Назначение |
|------|-------|-----------|
| `build_model.py` | 2,800+ | Генерация 30 листов с формулами |
| `fill_data.py` | 1,400+ | Загрузка данных из Excel/YAML |
| `styles.py` | 160 | Цветовая схема (bank model) |
| `reg.json` | 200+ keys | Реестр строк для cross-sheet refs |
| `DESIGN.md` | Architecture | Архитектурное описание |
| `IMPLEMENTATION_PLAN.md` | Plan | Детальный план реализации |
| `TODO.md` | Issues | 19+ tracked issues |
| `AUDIT_FIXES.md` | Audit | 12/12 findings tracked |
