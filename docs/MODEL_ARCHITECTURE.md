# Model Architecture — stressTest_v2 (v2.3, July 2026)

## 1. ИСТОЧНИКИ МАКРО-ДАННЫХ

Три уровня, по приоритету:

```
External ECM (modelMacro, 19 факторов)  <- override
    | (если не покрыто)
VECM / Mean Reversion / EWA            <- внутренний forecast
    | (fallback)
Gap-fill (IMF consensus, EWA)           <- safe defaults
```

| Источник | Факторы | Метод |
|----------|---------|-------|
| **External ECM** (modelMacro) | brent, usd_rub, cbr_key_rate, cpi_ru, ppi_ru, gdp_ru + 12 sector drivers | 13 уравнений ECM, quarterly->annual агрегация |
| **Mean Reversion** (OU) | lme_aluminium (+ другие commodity) | kappa=0.12 (HL=5.6yr), медиана как long-run mean |
| **EWA** | lme_alumina, russian_power_price | halflife=5yr, [P10,P90] clamp |
| **IMF consensus** | gdp_world | +2.8% CAGR (исключён из VECM) |
| **Gap-fill** | gdp_deflator_ru | EWA fallback |

### Data Flow

```
modelMacro/verify/scenario_results.csv
    -> external_loader.py (quarterly->annual: mean/q4_level/sum)
    -> macro_forecasts DB (method="external_ecm(...)")

macro_factors DB (история)
    -> vecm_bridge.py (3 потока: VECM/MR/EWA)
    -> macro_forecasts DB

macro_forecasts DB
    -> ModelInputLoader._load_macro_forecasts()
    -> HistoricState.macro_forecasts {factor: {year: value}}
    -> core.py / segment_revenue.py / cogs_block.py
```

### External ECM: Variable Mapping

| modelMacro var | stressTest_v2 factor | Агрегация |
|----------------|---------------------|-----------|
| POIL | brent | mean (4Q) |
| RUBUSD | usd_rub | mean (4Q) |
| R | cbr_key_rate | Q4 level |
| KEY | cbr_key_rate_policy | Q4 level |
| CPI (level) | cpi_ru | Q4 index (base=100) |
| PY (deflator) | ppi_ru | Q4 index |
| Y_real (log) | gdp_ru | sum (4Q) |

### Scenario Mapping

| modelMacro | stressTest_v2 |
|------------|---------------|
| baseline | base |
| low_oil | bear |
| collapse | severe |
| high_oil | bull |
| uae_bearish | sanctions_shock |
| uae_moderate | energy_spike |

### Mean Reversion по сценариям

| Сценарий | kappa | Обоснование |
|----------|-------|-------------|
| base | 0.12 | OU MLE на LME Al 1990-2029, HL=5.6yr |
| bear/stress | 0.5 | Быстрый возврат к медиане (3-4 кв) |
| bull | RW drift | Удержание momentum (P50-P95 clamp) |

### Ключевые файлы макро-модуля

| Файл | Назначение |
|------|-----------|
| `engine/macro/runner.py` | Точка входа `run_macro()` |
| `engine/macro/external_loader.py` | Загрузка из modelMacro (ECM + sector) |
| `engine/macro/vecm_bridge.py` | 3-поточный прогноз (VECM/MR/EWA) |
| `engine/macro/vecm.py` | VECM solver (Johansen, 1600+ строк) |
| `engine/macro/commodity_models.py` | Mean reversion (OU), RW drift, EWA |
| `engine/macro/db_adapter.py` | MacroDBAdapter — DB interface |
| `engine/macro/preprocess.py` | Anomaly detection, cycle detection |

---

## 2. ThreeStatementModel — ITERATIVE SOLVER

**File:** `engine/model/core.py` (1000+ строк)

### Порядок решения `_solve_year()`

```
 NON-ITERATIVE (вычисляется один раз):
  1. Revenue      -> segment model (Vol x Price) или macro OLS
  2. COGS         -> component (alumina+energy+labour+other) или ratio
  3. SGA          -> split (distribution/admin/ECL/other) или % revenue
  4. PPE          -> corkscrew: sustaining 2.0x DA + growth 5%
  5. Other IS     -> ForecastDispatcher (EWA/LAST/ZERO/MACRO)
  6. WC           -> DSO/DIH/DPO с cyclical elasticity
  7. Lease        -> IFRS 16 corkscrew
  8. BS Other     -> provisions, related parties

 ITERATIVE LOOP (max 10, tol=$1K):
  9. Debt         -> optimizer: mandatory->refi->draw->repay
 10. Interest     -> avg(open,close) x rate
 11. IS subtotals -> EBITDA, EBIT, EBT
 12. Tax          -> TaxBlock: current + deferred (IAS 12)
 13. Equity       -> RE = open + NI - dividends
 14. CF           -> CFO/CFI/CFF
 15. Cash         -> from CF bridge (не plug!)
 16. BS Totals    -> Assets = L + E
 17. Covenants    -> breach -> reclassify callable -> ST
     -> if delta_cash < $1K -> converged, exit
```

**Циркулярность:** `RC draw <-> interest <-> EBT <-> tax <-> NI <-> RE <-> equity <-> cash <-> RC draw`

### Входы / Выходы

**Входы:**
- `HistoricState` — IS/BS/CF 2011-2025, debt_instruments (31 шт), macro_forecasts, preprocess (1306 метрик)
- `ModelConfig` — forecast_years, debt_mode, ковенанты, corkscrew флаги, 50+ полей

**Выходы:**
- `ModelResult` — YearState (120+ полей) для каждого года, BS/CF diffs, debt_lines, warnings

---

## 3. REVENUE: Segment Model

**File:** `engine/model/segment_revenue.py`

```
Revenue = Sum(Volume_i x Price_i) по сегментам

primary_al:  Vol = EWA(production_kt), cap=4100kt, demand <= GDP x 0.8
             Price = OLS chain-link от LME Al ($2,652/t base)
alumina:     Vol = EWA, Price = EWA (OLS broken beta=-0.72)
other:       Vol = 1, Price = EWA(foil+other segment revenue)
```

### Приоритет методов (fallback chain)

```
1. SegmentRevenueModel (if configured)
2. Explicit macro_forecasts['revenue']
3. OLS Regression: dln(Revenue) ~ dln(macro_factor) + alpha
4. EWA with [P10, P90] clamp (halflife=5yr)
5. Fallback: prev.revenue x 1.02
```

### Capacity & Demand Constraints

```python
# Capacity cap
if vol_fc[yr] > max_volume_kt:
    vol_fc[yr] = max_volume_kt  # 4100kt nameplate

# Demand elasticity (GDP linkage)
gdp_growth = gdp[yr] / gdp[yr-1] - 1
max_vol_growth = max(0, gdp_growth * 0.8)  # Al demand elasticity
if vol_fc[yr] > prev_vol * (1 + max_vol_growth):
    vol_fc[yr] = prev_vol * (1 + max_vol_growth)
```

---

## 4. COGS: Component Model

**File:** `engine/model/cogs_block.py`

```
COGS = alumina(37%) + energy(27%) + labour(12%) + other(24%)

alumina:  disabled (commodity_factor=none, vertically integrated)
energy:   base x (power_price/base) x (FX_base/FX) x vol_adj
labour:   base x (CPI/CPI_base) x (FX_base/FX) x vol_adj
other:    base x (PPI/PPI_base) x vol_adj
```

### Mean Reversion к anchor

```python
macro_deviation = (total_costs / base_cogs) - 1
cogs_ratio = anchor * (1.0 + macro_deviation * dampening)  # 0.80
cogs_ratio = clamp(anchor - sigma, anchor + sigma, cogs_ratio)  # +/- 0.09
```

| Параметр | Значение | Калибровка |
|----------|----------|------------|
| dampening | 0.80 | OLS dln(COGS/Rev) ~ beta x dln(PPI), R2=0.76 |
| clamp_sigma | 0.09 | 1.5 x sigma(COGS/Rev), sigma=0.059 |
| commodity_factor | none | Rusal vertically integrated |

---

## 5. DEBT OPTIMIZER

**File:** `engine/model/schedules/debt.py` (584 строк)

### 7 шагов DebtOptimizer.solve_year()

```
Step 0: Mandatory payments (amort schedule + bullet maturities)
Step 1: Refinancing (extend 5yr, rate adj, fees 0.1%)
Step 2: Pre-financing cash = opening + CFO + CFI - mandatory
Step 3: Draw (RC first, then LT by priority/rate; NewMoney fallback)
Step 4: Repay surplus (RC first, then lowest-rate LT)
Step 5: Interest = avg(open+refi, close) x effective_rate
Step 6: ST/LT split (maturity, amort, callable+breach)
Step 7: CFF = draws + refi - repays - fees
```

### ST/LT Classification (4 правила)

```
1. RC -> всегда ST
2. Maturity = year+1 -> полный баланс ST
3. Scheduled amortization next year -> partial split
4. Callable + covenant breach -> full ST (acceleration)
Default -> LT
```

---

## 6. CORKSCREWS (8+1)

| Corkscrew | Формула | File |
|-----------|---------|------|
| PPE | gross_open + capex - dep - disposals = gross_close | `schedules/ppe.py` |
| WC | DSO/DIH/DPO days -> AR/Inv/AP (cyclical elasticity) | `schedules/wc.py` |
| Debt | per-instrument optimizer (mandatory->refi->draw->repay) | `schedules/debt.py` |
| Lease | ROU + liability (IFRS 16 / ASC 842) | `schedules/lease.py` |
| Tax | Current + Deferred (IAS 12), NOL->DTA, DT categories | `schedules/tax.py` |
| Equity | RE = open + NI - dividends - buybacks | `schedules/equity.py` |
| Intangibles | open + additions - amort = close | `schedules/intangibles.py` |
| Provisions | open + charge - utilization + accretion = close (3 cat) | `schedules/provisions.py` |
| Interest Payable | tracking schedule (current/next year) | `schedules/interest_payable.py` |

### WC Cyclical Elasticity

```python
DSO_adj = DSO * (1 - 0.87 * rev_growth)  # OLS calibrated
DIH_adj = DIH * (1 + 0.36 * rev_growth)  # inventory sticky
DPO_adj = DPO * (1 - 0.64 * rev_growth)  # payables lag
```

### Tax Block (IAS 12 / ASC 740)

```
Current:  current_tax = rate x max(0, EBT - NOL_used - accel_dep)
Deferred: deferred_tax = -(delta_DTL - delta_DTA)
NI:       NI = EBT + current_tax + deferred_tax

NOL:      NOL_used = min(NOL_open, EBT x 0.80)  # TCJA cap
CF:       cfo_deferred_tax = dtl_delta - dta_delta (non-cash)
          cfo_taxes_paid = -current_tax (current_year) or -prev_taxes_payable (next_year)
```

---

## 7. FORECAST DISPATCHER

**File:** `engine/model/forecast_dispatcher.py`

| Метод | Использование |
|-------|--------------|
| EWA | earnings_from_investees, interest_income, other_financial_costs |
| LAST | carry forward (goodwill, restricted_cash) |
| ZERO | restructuring (обнуление) |
| MACRO | OLS chain-link на macro factor |
| DRIVER | % от базовой статьи (revenue x ratio) |
| CORK | обрабатывается отдельным блоком (WC, Tax) |
| CALC | формула (eval) |
| LINK | связь с другим полем |
| DAYS | WC дни (WCBlock) |
| PLUG | Cash plug |

---

## 8. STRESS TESTING

**File:** `engine/stress/runner.py`

### Алгоритм

```
1. Загрузить base scenario (macro_forecasts + ModelConfig)
2. Применить macro_shocks -> модифицировать macro_forecasts
3. Применить driver_shocks -> модифицировать ModelConfig (cogs%, dso, rate...)
4. Rebuild SegmentRevenueModel (если шоки на price factors)
5. Re-run ThreeStatementModel с stressed inputs
6. Сравнить base vs stress (revenue/ebitda/ni delta)
7. Сохранить в stress_results DB
```

### 9 сценариев (Rusal)

| Сценарий | Шоки | Rev delta | NI delta |
|----------|------|-----------|----------|
| lme_mild | LME Al -15% | -9.3% | -15.8% |
| aluminium_downturn | LME Al -25%, alumina -15%, WC +15/+20% | -15.7% | -23.9% |
| sanctions_shock | USD/RUB +30%, power +20% | 0% | +70.6% |
| energy_spike | Power +40%, brent +30% | 0% | -85.4% |
| rate_spike | avg_rate +200bp | 0% | +0.6% |
| severe | LME -30%, alumina -20%, FX +25%, power +30%, rate +400bp | -19.0% | -24.3% |
| upside | LME +20%, alumina +15% | +11.8% | +22.2% |
| covenant_breach | LME -20%, power +30%, rate +200bp, WC | -12.4% | -99.2% |
| demand_shock | LME -15%, WC +20/+25% | -9.3% | -15.3% |

---

## 9. RATING (S&P Metals/Mining)

**File:** `engine/rating/core.py`

### Скоринг

```
Score = Leverage(35%) + Coverage(30%) + Profitability(20%) + Liquidity(15%)
      + industry_adj(-6) + size_adj(+2)
```

| Sub-score | Метрика | Пороги (BBB- zone) |
|-----------|---------|-------------------|
| Leverage | ND/EBITDA | < 2.0x = 55 |
| Coverage | EBITDA/Interest | > 5x = 62 |
| Profitability | EBITDA% (cycle-norm) | > 10% = 55 |
| Liquidity | Current ratio + cash | > 1.5x = 65 |

### National Scale (RU)

```
Intl -> National: notches below sovereign (BBB+) -> RU scale
BBB+ -> AAA(RU), B+ -> A+(RU), CCC+ -> BBB-(RU)
```

---

## 10. КАЛИБРОВКА (v2.3, July 2026)

Все параметры откалиброваны из исторических данных Rusal 2011-2025:

| Параметр | Значение | Метод | Файл |
|----------|----------|-------|------|
| COGS dampening | 0.80 | OLS dln(COGS/Rev) ~ beta x dln(PPI), R2=0.76 | project.yaml |
| COGS clamp | 0.09 | 1.5 x sigma(COGS/Rev) | project.yaml |
| MR kappa | 0.12 | OU MLE на LME Al 40yr | vecm_bridge.py |
| WC DSO elast | 0.87 | OLS ddays/days ~ beta x drev/rev | constants.py |
| WC DIH elast | 0.36 | OLS, n=14 | constants.py |
| WC DPO elast | 0.64 | OLS, n=12 | constants.py |
| Al capacity | 4100 kt | Nameplate (5 заводов) | project.yaml |
| CapEx sustaining | 2.0x DA | Median 2021-2025 (2.17x) | project.yaml |
| Tax rate | 0.25 | РФ statutory 2025+ | project.yaml |
| GDP World | IMF +2.8% | External consensus | runner.py |

---

## 11. ПОЛНЫЙ PIPELINE

```
build_model()
  |
  +-- 1. Preprocessor (14 групп, 1306 метрик)
  |     margins, WC days, capex, debt, interest, equity, extended,
  |     beta_coefficients, revenue_betas, cf/is_reconciliation,
  |     unmodeled_items, lease, cogs_macro, production_kpi
  |
  +-- 2. Macro (VECM/MR/EWA + external ECM)
  |     22 фактора: 19 external + 3 internal (MR/EWA/gap-fill)
  |
  +-- 3. ModelInputLoader -> HistoricState + ModelConfig
  |     IS/BS/CF history, 31 debt instruments, macro_forecasts,
  |     segment configs, preprocessor drivers
  |
  +-- 4. ThreeStatementModel.run() -> ModelResult
  |     8+1 corkscrews, iterative solver (10x, $1K tol)
  |     BS diff = 0.00, CF diff = 0.00
  |
  +-- 5. ModelSaver -> forecast_is/bs/cf + debt_schedule
  |     IS(32) + BS(45) + CF(33) metrics per year
  |
  +-- 6. StressRunner (9 scenarios)
  |     macro_shocks + driver_shocks -> full 3-statement re-run
  |     585 rows per scenario
  |
  +-- 7. RatingRunner (S&P + national RU)
  |     4 sub-scores -> weighted -> intl rating -> national
  |
  +-- 8. CovenantsChecker
        ND/EBITDA <= 4.5, ICR >= 2.0, D/E <= 4.0, CR >= 1.0
```

**Время выполнения:** ~0.9s (preprocessor 0.0s, macro 0.1s, model 0.1s, stress 0.8s)
