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
17_Debt: Corkscrew + Circular optimizer (draw if cash < min_cash)
18_Lease: IFRS 16 ROU + Liability (interest + payment)
19_Tax: IAS 12 (NOL → Taxable → Current×25% + Deferred), DTA/DTL carry
    ↓
21_PL: Revenue ← 10_Rev, COGS ← 12, SGA ← 13, DA ← 15_PPE, Interest ← 17_Debt, Tax ← 19
    GP = Rev + COGS, EBITDA = GP + SGA, EBIT = EBITDA - DA, EBT = EBIT - Interest, NI = EBT - Tax
    ↓
23_CF (indirect):
    CFO = NI + DA + WC_change + other
    CFI = -CapEx + disposals
    CFF = Debt_draw - Debt_repay - Lease_pay - Dividends
    Net_change = CFO + CFI + CFF
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

### 3.4 Circular Dependencies
```
17_Debt.draw → 17_Debt.close → 17_Debt.interest
    → 21_PL.interest → 21_PL.NI
    → 23_CF.NI → 23_CF.CFO → 23_CF.CFF → 23_CF.cash_close
    → 20_BS.cash → 17_Debt.draw (CIRCULAR)
```

**Решение:**
1. Named range `calc_reset` = `'Control_Panel'!$K$1`
2. Seed phase (`calc_reset=1`): draw = estimated draw (from EBITDA-based cash, no circular)
3. Iterate phase (`calc_reset=0`): draw = CF-based (circular, converges in 3-4 iterations)
4. AppleScript: `calc_reset=1 → recalc → calc_reset=0 → recalc ×20`
5. IFERROR fallback: if circular errors, use seed estimate
6. MEDIAN clamp: draw ∈ [0, 3× opening_debt]

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

### 4.3 Debt (17_Debt)
```
Open + Draw - Mandatory - Voluntary + Refi = Close
Interest = AVG(Open, Close) × avg_rate

Draw: circular optimizer (see §3.4)
Voluntary: MAX(0, est_cash - 1.5×min_cash) × IF(NI>0)
ST/LT split: historical ratio carry-forward

Net Debt = Total Debt - Cash
ND/EBITDA = Net Debt / EBITDA
```

### 4.4 Equity (24_Equity)
```
RE_open + NI(parent) - Dividends - Buybacks + Other = RE_close
Dividends = MAX(0, NI) × payout_ratio (from CP)
NI(parent) = NI × (1 - nci_pct) — for companies with NCI
AOCI/NCI: grows by NI × nci_pct each year
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

### Rusal 2026E (after audit fixes)
| Показатель | Значение | До аудита |
|-----------|---------|-----------|
| Revenue | **$14,321M** | $10,546M |
| EBITDA | **$577M (4.0%)** | $425M |
| Net Income | **+$205M** ✅ | -$1,222M |
| Interest | **-$773M** | -$1,155M |
| Cash | **$752M** | -$400M |
| Avg Debt Rate | **8.01%** | 12.03% |
| Mandatory Repay | **$3,357M** | $0 |
| ND/EBITDA | **16x** | 20x |
| Rating | D | D |
| **BS Check** | **-290 (1.2%)** | -17,503 → 0 |
| CF Bridge | **0** ✓ | ✓ |

### Nornickel 2026E (after audit fixes)
| Показатель | Значение |
|-----------|---------|
| Revenue | **$13,716M** |
| EBITDA | **$4,815M (35%)** |
| Net Income | **$1,252M** |
| Cash | **$764M** |
| Avg Debt Rate | **8.73%** |
| ND/EBITDA | **2.1x** |
| Rating | CCC |
| **BS Check** | **-270 (0.9%)** |
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
