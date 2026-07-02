# Полная карта моделирования: от макро-факторов до статей отчётности

Версия: v2.2 (2026-07-02)

---

## 1. МАКРО-ПРОГНОЗИРОВАНИЕ (`engine/macro/`)

Три потока прогнозирования, автоматически распределённые по типу фактора через `auto_group_factors()`:

```
┌─────────────────────────────────────────────────────────────┐
│  auto_group_factors() — классификация по ключевым словам    │
├───────────────┬──────────────────┬──────────────────────────┤
│  VECM (макро) │  Mean Reversion  │  EWA (прочие)            │
│  GDP, CPI,    │  LME Al, Alumina │  russian_power_price,    │
│  PPI, Ind.Prod│  Brent, HRC,     │  прочие не-классиф.      │
│               │  Iron Ore, Coal  │                          │
├───────────────┼──────────────────┼──────────────────────────┤
│  Коинтеграция │  Ornstein-       │  Сглаженный тренд        │
│  Johansen,    │  Uhlenbeck,      │  α = 1-exp(-ln2/HL)      │
│  p=1..3,      │  P(t+1)=P(t)+    │  halflife=5 лет          │
│  det="ci"     │  κ×(μ-P(t))      │                          │
├───────────────┼──────────────────┼──────────────────────────┤
│  Fallback:    │  κ зависит от    │                          │
│  ARIMA(0,1,1) │  сценария:       │                          │
│  → ETS → RW   │  base=0.15       │                          │
│               │  bear/stress=0.5 │                          │
│               │  bull=rw_drift   │                          │
└───────────────┴──────────────────┴──────────────────────────┘
```

**Rusal факторы:** `lme_aluminium`, `lme_alumina`, `usd_rub`, `brent`, `gdp_world`, `cpi_ru`, `ppi_ru`, `russian_power_price`

**Preprocessing:** Z-score аномалии (≥2.5σ), dummy-переменные для шоков (2020 COVID, 2022 санкции), winsorize ±20%

**Структурные шоки:** dummy-переменные для 2020 и 2022 автоматически включаются в VECM если |z| ≥ 3.0σ

**Результат:** таблица `macro_forecasts` → `{factor: {year: value}}` → загружается в `HistoricState.macro_forecasts`

---

## 2. ПРЕПРОЦЕССОР (`engine/preprocessor/core.py`)

14 групп метрик из исторических IS/BS/CF → EWA-сглаженные рекомендации для прогноза:

| # | Группа | Ключевые метрики | Формула |
|---|--------|-----------------|---------|
| 1 | `margin_ratios` | gross_margin, cogs_ratio, sga_ratio, opex_ratio, distribution/admin/ecl/other_opex_ratio, `*_share_of_opex`, tax_rate, current/deferred_tax_ratio, dta/dtl_pct_assets, provisions_pct_revenue | `metric / revenue` + доля в total opex |
| 2 | `wc_days` | DSO, DIH, DPO, CCC, NWC/Revenue | `(BS_item / IS_driver) × 365` |
| 3 | `capex` | capex_to_rev, dep_to_rev, dep_rate, disposal_ratio | `CF_item / Revenue` или `DA / PPE_net` |
| 4 | `debt` | avg_interest_rate, debt_to_ebitda, net_debt_to_ebitda, ICR, min_cash | `interest / debt`, `debt / ebitda` |
| 5 | `interest` | interest_income_rate, interest_accrual_ratio | `income / avg_cash` |
| 6 | `equity` | dividend_payout, buyback_to_ni, ROE | `dividends / NI` |
| 7 | `extended` | earnings_from_investees, other_fin_costs, AOCI | EWA абсолютных значений |
| 8 | `beta_coefficients` | ppi_beta, cpi_beta, demand_decline_beta | OLS: `Δln(COGS/Rev) ~ Δln(PPI)` |
| 9 | `revenue_betas` | rev_beta_*, rev_r2_*, best_factor | OLS: `Δln(Rev) ~ Δln(Factor)` |
| 10 | `cf_reconciliation` | cfo_adjustment, cfi_adjustment | gap между subtotal и компонентами |
| 11 | `is_reconciliation` | ebit_adjustment | gap в IS |
| 12 | `unmodeled_items` | unmodeled_assets | `total_assets - Σ(смоделированные)` |
| 13 | `lease` | op_decay_rate, fin_principal_rate, fin_interest_rate | `(open+new-close) / open` |
| 14 | `cogs_macro` | cogs_beta_*, cogs_best_factor | OLS: `COGS% ~ ln(commodity)` |

**EWA формула:**
```
result = α × current + (1-α) × prior
α = 1 - exp(-ln2 / halflife)
halflife = 3 года (margin/capex/debt), 3 года (wc_days)
```

**Выход:** каждая метрика → `{year: value, _ewa, _mean, _last, _ewa_winsorized, _recommended}` → DB `preprocess_metrics`

---

## 3. МОДЕЛЬ: КТО ЧЕМ УПРАВЛЯЕТСЯ

### IS — Отчёт о прибылях и убытках

```
Revenue ─── Macro (LME Al × Vol) или OLS β или EWA growth
  │
  ├─ COGS ─── Component: commodity×energy×labour×other (каждый × макро-индекс)
  │           ИЛИ Revenue × cogs_pct (EWA из препроцессора) × macro uplift
  │           Clamp: исторические P10–P90
  │
  ├─ SGA ──── Revenue × sga_pct (EWA) × (1 + CPI_growth × β)
  │   │       Clamp: hist_min×0.7 .. hist_max×1.3
  │   │
  │   └─ Split (если включён):
  │      distribution = SGA × norm_share (EWA *_share_of_opex)
  │      admin        = SGA × norm_share
  │      ecl          = SGA × norm_share
  │      other_opex   = SGA × norm_share
  │      Σ shares = 1.0 → гарантированная сумма = total SGA
  │
  ├─ D&A ─── PPE:    avg_net_ppe × dep_rate (препроцессор)
  │           ROU:    rou_open × op_decay_rate
  │           Intang: intang_open × amort_rate
  │
  ├─ Other IS ── ForecastDispatcher:
  │   earnings_from_investees  → EWA (halflife=3)
  │   interest_income          → EWA (halflife=2)
  │   other_financial_costs    → EWA (halflife=3)
  │   asset_impairment         → ZERO (one-time, не прогнозируем)
  │   restructuring            → ZERO
  │
  ├─ Interest ── DebtOptimizer: avg(open, close) × rate по каждому инструменту
  │              + Lease: liab_open × discount_rate
  │
  └─ Tax ─── TaxBlock (IAS 12):
             taxable = EBT - NOL_used - accel_dep
             current = taxable × rate
             deferred = -(ΔDTL - ΔDTA)
             NI = EBT + total_tax
```

### BS — Баланс

| Статья | Драйвер | Метод |
|--------|---------|-------|
| **Cash** | CF Bridge plug | `open + CFO + CFI + CFF` |
| **AR** | DSO × Revenue / 365 | Days + cyclical elasticity (0.15 × rev_growth) |
| **Inventory** | DIH × COGS / 365 | Days + cyclical elasticity (0.30 × rev_growth) |
| **PPE** | Corkscrew | `open + capex - dep - disposals` |
| **Intangibles** | Corkscrew | `open + additions - amort` |
| **Goodwill** | Carry forward | `prev.goodwill` |
| **DTA** | Tax corkscrew | `NOL×rate + pension DTA + temp diffs` |
| **AP** | DPO × COGS / 365 | Days + cyclical elasticity |
| **ST/LT Debt** | Debt Optimizer | 69 инструментов: amort + refi + draw/repay |
| **Lease liab** | Lease corkscrew | `open + additions - principal` |
| **DTL** | Tax corkscrew | `accel_dep×rate + temp diffs (PPE/Inv/AR/AP)` |
| **Employee benefits** | Provisions corkscrew | `open + charge(12%) - utilization(8%)` |
| **Other NCL** | Provisions corkscrew | `site_restoration + legal_claims` |
| **Retained earnings** | Equity corkscrew | `open + NI - dividends` |
| **Taxes payable** | Payment timing | `current_year=0`, `next_year=\|current_tax\|` |

### CF — Денежный поток (indirect method)

```
CFO = NI + D&A + ΔDeferred_Tax + ΔWC + Δtaxes_payable + Δinterest_payable + other
CFI = -CapEx + disposal_proceeds - intang_additions + other
CFF = debt_draws - debt_repays - lease_principal - dividends - buybacks + refi_fees
Cash_close = Cash_open + CFO + CFI + CFF + FX
```

---

## 4. SOLVER: ИТЕРАЦИОННЫЙ ЦИКЛ

```
Порядок решения внутри года:

ОДНОКРАТНО (нет циклических зависимостей):
  Revenue → COGS → SGA → PPE → WC → Lease → BS Other → Other IS

ИТЕРАЦИОННО (max_iter=10, tol=$1K на cash и NI):
  ┌─→ Debt Optimizer  (interest зависит от cash, cash от interest)
  │   Interest Payable
  │   IS Subtotals    (EBITDA → EBIT → EBT)
  │   TaxBlock        (current + deferred)
  │   Equity          (RE = open + NI - div)
  │   CF Statement    (CFO / CFI / CFF)
  │   Cash            = open + CFO + CFI + CFF
  │   BS Totals       (assets = liab+equity check)
  └── Covenant check  → если breach → reclassify callable → repeat
```

Convergence: `|cash_t - cash_{t-1}| < $1K` и `|NI_t - NI_{t-1}| < $1K`

---

## 5. ПРИОРИТЕТ ИСТОЧНИКОВ ДАННЫХ

Для каждого драйвера модели:

```
1. YAML explicit (project.yaml)          → если задан явно, используем
2. Preprocessor _recommended (EWA)       → автоматический из истории
3. Hardcoded default (constants.py)      → fallback
```

Пример для COGS:
```
cfg.cogs_pct = YAML(0.82) → preprocess(cogs_ratio_recommended=0.827) → DEFAULT(0.85)
```

---

## 6. СЦЕНАРНАЯ ЗАВИСИМОСТЬ

| Сценарий | Макро-κ | Влияние на модель |
|----------|---------|-------------------|
| `base` | 0.15 | Медленная нормализация цен (3-4 года) |
| `bear` / `stress` / `severe` | 0.50 | Быстрый откат к медиане (1-2 года) |
| `bull` / `upside` | `rw_drift` | Сохранение момента + clamp P50-P95 |

Стресс-шоки применяются к макро-факторам → Revenue × elasticity → COGS × component indices → Interest × rate shocks → каскадирует по всей модели.

---

## 7. ПОЛНЫЙ ПОТОК ДАННЫХ

```
modelMacro (опционально, external.enabled=true)
  ├── verify/scenario_results.csv → 7 macro (brent, usd_rub, cpi_ru, ppi_ru, cbr_key_rate, gdp_ru)
  └── data/processed/sector/     → 10 sector (gva_growth, ipi, wages, npl, leverage × mining/manuf)
  ↓ quarterly→annual aggregation (mean/sum/q4/q4_yoy)
  ↓ scenario mapping (baseline→base, low_oil→bear, collapse→severe...)

Macro DB (LME, GDP, CPI...)
  → VECM / MR / EWA прогноз (только факторы, не покрытые external)
    → macro_forecasts таблица

History DB (IS/BS/CF × 15 лет)
  → Preprocessor (14 групп, EWA)
    → preprocess_metrics таблица

YAML Config (project.yaml)
  → ModelConfig (50+ параметров)

         ↓ всё загружается в HistoricState + ModelConfig ↓

ThreeStatementModel.solve()
  → Revenue  (macro × elasticity × segment Vol×Price)
  → COGS     (component: commodity+energy+labour+other × macro indices)
  → SGA      (EWA × CPI uplift, split по share-of-opex)
  → 8 corkscrews: PPE, WC, Debt, Lease, Tax, Equity, Intangibles, Provisions
  → 10-iteration solver (cash ↔ interest convergence)
  → BS_diff = 0.00,  CF_diff = 0.00
```

---

## 11. EXTERNAL MACRO INTEGRATION (`engine/macro/external_loader.py`)

Опциональная интеграция с проектом **modelMacro** — квартальная ECM (13 уравнений, макро РФ).

### Режим: override

External перезаписывает VECM/MR для покрытых факторов, остальные прогнозируются как раньше.

### Покрытие

| modelMacro var | stressTest_v2 factor | Агрегация Q→Y |
|---------------|---------------------|---------------|
| `POIL` | `brent` | mean |
| `RUBUSD` | `usd_rub` | mean |
| `CPI` (level) | `cpi_ru` | Q4 level |
| `PY` (deflator) | `ppi_ru` | Q4 level |
| `R` (RUONIA) | `cbr_key_rate` | Q4 |
| `KEY` | `cbr_key_rate_policy` | Q4 |
| `Y_real` | `gdp_ru` | sum |

### Отраслевые драйверы (sector module)

| Драйвер | Формат | Для чего |
|---------|--------|----------|
| `gva_growth_{sector}` | YoY % | Revenue elasticity |
| `ipi_{sector}` | Index | Production volume |
| `sector_wage_{sector}` | руб./мес. | Labour COGS |
| `sector_npl_{sector}` | ratio | ECL calibration |
| `sector_leverage_{sector}` | ratio | Refinancing risk |

### Непокрытые (остаются на VECM/MR/EWA)

`lme_aluminium`, `lme_alumina`, `gdp_world`, `russian_power_price`

### YAML конфиг

```yaml
macro_forecast:
  external:
    enabled: true
    source_path: /path/to/modelMacro
    mode: override
    macro:
      scenario_map: {baseline: base, low_oil: bear, collapse: severe}
      variable_map: {POIL: brent, RUBUSD: usd_rub, R: cbr_key_rate}
    sector:
      company_sector_map:
        rusal: [mining, manuf]
        nornickel: [mining]
```

---

## 8. СПРАВОЧНИК: CORKSCREWS

| Corkscrew | Формула | Файл |
|-----------|---------|------|
| **PPE** | `gross_open + capex - disposals = gross_close` | `schedules/ppe.py` |
| **WC** | `DSO/DIH/DPO days → AR/Inv/AP (cyclical elasticity)` | `schedules/wc.py` |
| **Debt** | `per-instrument schedule / optimizer / parametric` | `schedules/debt.py` |
| **Lease** | `ROU + liability (IFRS 16 / US GAAP ASC 842)` | `schedules/lease.py` |
| **Tax** | `Current + Deferred (IAS 12), NOL→DTA, DT categories` | `schedules/tax.py` |
| **Equity** | `RE = open + NI - dividends - buybacks` | `schedules/equity.py` |
| **Intangibles** | `open + additions - amortization = close` | `schedules/intangibles.py` |
| **Provisions** | `open + charge - utilization + accretion = close (3 категории)` | `schedules/provisions.py` |

---

## 9. COMPONENT COGS (Rusal)

```
COGS = Revenue × cogs_ratio

cogs_ratio = anchor × (1 + macro_dev × dampening)   # clamp ±σ от anchor

Компоненты (Rusal):
  alumina  37%: base × (lme_alumina_index) × vol_adj
  energy   27%: base × (power_price_index) × (usd_rub_index) × vol_adj
  labour   12%: base × (cpi_ru_index)      × (usd_rub_index) × vol_adj
  other    24%: base × (ppi_ru_index)      × vol_adj

mean_reversion_dampening = 0.30  # только 30% отклонения проходит в прогноз
clamp_sigma = 0.06               # max ±6pp от anchor
```

---

## 10. SGA SPLIT (Rusal, опционально)

Принцип: **share-of-total composition**, не independent % от revenue.

```python
# Препроцессор вычисляет:
distribution_share_of_opex = |distribution| / total_opex   # EWA
admin_share_of_opex        = |admin| / total_opex
ecl_share_of_opex          = |ecl| / total_opex
other_opex_share_of_opex   = |other| / total_opex

# Модель (sga.py):
share_sum = Σ shares
shares = [s / share_sum for s in shares]   # normalize → Σ = 1.0

state.distribution_expenses = -total_sga × dist_share   # гарантированно
state.admin_expenses         = -total_sga × admin_share  # суммируются
state.ecl_expenses           = -total_sga × ecl_share    # в total SGA
state.other_opex             = -total_sga × other_share
```
