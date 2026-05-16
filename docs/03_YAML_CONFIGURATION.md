# YAML Configuration Reference

## Config Files

| File | Purpose |
|------|---------|
| `companies/{company}/configs/project.yaml` | Main model config (all settings) |
| `templates/project_template.yaml` | Canonical template — copy for new companies |
| `companies/{company}/configs/accounting_conventions.yaml` | Sign conventions, metric aliases |

---

## Top-Level Sections

### `company`
```yaml
company:
  name: "United States Steel Corporation"
  industry: "metals"         # metals | energy | chemicals | retail | ...
  currency: "USD"
  cik: "0000101830"          # SEC CIK (optional)
  accounting_standard: "US_GAAP"  # US_GAAP | IFRS
```

---

### `accounting_conventions`
```yaml
accounting_conventions:
  da_in_cogs: true          # D&A is embedded in COGS (not shown separately on IS)
                             # Affects: EBITDA bridge, SG&A ratio calibration
  capitalize_interest: true  # Capitalized interest added to CapEx, excluded from IS interest expense
                             # Affects: PPE corkscrew, interest expense modeling
  interest_in_cff: true      # Interest paid in CFF (not CFO) — IFRS common; US GAAP usually CFO
  da_presentation: separate_line  # separate_line | embedded_in_cogs
```

Loaded by `engine/model/loader.py` into `ModelConfig.da_in_cogs` and `ModelConfig.capitalize_interest`.

---

### `macro_forecast`
```yaml
macro_forecast:
  profile: vecm_default
  factors:
    - gdp_us
    - industrial_production_us
    - dxy
    - steel_price_hrc
    - iron_ore_price
    - cpi_us
    - ppi_us
    - gdp_world
  policy:
    factors:                  # Factors used for revenue regression
      - steel_price_hrc
      - gdp_world
      - gdp_us
  file_map:
    gdp_us: gdp_us.csv
    steel_price_hrc: steel_price_hrc_usd.csv
    # ...
  search_paths:               # Searched in order for CSV files
    - companies/{company}/drivers
    - macro/industry/metallurgy/drivers
    - macro/global/drivers
```

---

### `history`
```yaml
history:
  is: companies/{company}/history/is_history_{company}.csv
  bs: companies/{company}/history/bs_history_{company}.csv
  cf: companies/{company}/history/cf_history_{company}.csv
```

CSV format: metric names as rows, years as columns (or transposed — loader auto-detects).

---

### `model`

```yaml
model:
  engine_version: v2
  mode: custom           # standard | custom
```

**`standard`** mode: simplified estimation (% revenue ratios, effective tax rate). Lower data requirements.
**`custom`** mode: full corkscrew blocks (PPE, WC, Tax, Debt). Requires schedule tables populated.

#### `model.standard.periods`
```yaml
periods:
  history_start_year: 2010
  history_end_year: 2024
  forecast_start_year: 2025
  forecast_end_year: 2029
  forecast_years: 5
```

#### `model.standard.debt`
```yaml
debt:
  mode: full                     # full | simple
  target_pct_revenue: 0.267      # Target net debt / revenue
  avg_rate_pct: 5.0              # Average interest rate (percent, not decimal)
  version: v2_solver
  interest_treatment: separate_line
  general_rate_delta_pct: 0.0
  absorb_nonmodeled_st_debt: true

  rc:
    enable: true
    limit: 2000.0                # RC facility limit (in db_unit)
    min_cash: 500000000.0        # Minimum cash floor (in db_unit)
                                 # Set 0 to use preprocessor auto-computed value
    rate_spread: 0.03
    rate_delta_pct: 0.0

  iter_max: 50                   # Internal debt solver iterations
  tol: 1.0e-6

  refinancing:
    enable: true
    mode: simple                 # simple | detailed
    simple:
      extend_years: 5
      rate_adjustment: 0.0
      fees_pct: 0.1

  covenants:
    icr_min: 2.0
    lev_max: 3.25

  lp_weights:                    # Used only when mode = optimizer
    w_cash_def: 1000000.0
    w_icr: 600000.0
    w_lev: 600000.0
    w_draw: 0.1
    w_end_debt: 0.02
```

**Debt modes:**
- `schedule_based` — reads `debt_schedule` table, builds corkscrews from actual instruments
- `parametric` — maintains target_pct_revenue; RC fills gap; no instrument detail
- `optimizer` — LP minimizes objective (cash deficit + covenant violations); RC is decision variable

**Floating rate instruments:** `rate_type = floating` in `debt_instruments` table → receives `general_rate_delta_pct` shock in stress scenarios. Fixed-rate bonds (`rate_type = fixed`) are immune to rate shocks. Environmental Revenue Bonds (US Steel) use `floating` despite low coupon.

**Callable instruments:** `callable_flag = 1` in `debt_instruments` → on covenant breach, instrument reclassified to short-term debt. Triggers `covenant_breach` auto-scenario (see `stress_scenarios.yaml`).

#### `model.standard.taxes`
```yaml
taxes:
  mode: full                        # full | simple
  policy: statutory_with_floor      # statutory_with_floor | effective_rate
  nol_opening_balance: 1014.0       # NOL carryforward pool at forecast start (in db_unit)
                                    # US Steel: $1,014M as of end-2024
  nol_max_utilization_pct: 0.80     # TCJA cap: max 80% of taxable income used per year
                                    # NOT 80% of the NOL pool — limits usage per period
  nol_expiration_years: 999         # 999 = indefinite (TCJA: no expiry for post-2017 NOLs)
  tax_paid_timing: next_year        # current_year | next_year
  accel_dep_excess_pct: 0.4         # Pct of CapEx that generates excess tax depreciation → DTL
```

**TaxBlock DTL logic:** `accel_dep_excess_pct × capex` adds to DTL each year (`_solve_tax_block`). DTL unwinds when accelerated depreciation benefit expires.

**NOL logic (TCJA):**
- Each year: `nol_used = min(nol_open, ebt × nol_max_utilization_pct)`
- Tax shield: `nol_shield = nol_used × statutory_rate`
- Corkscrew: `nol_open + nol_additions - nol_used = nol_close`
- Opening balance initialized from YAML at model start; carried across years via `_nol_carryforward`
- `nol_enabled` property: `True` when `nol_opening_balance > 0`

#### `model.standard.wc`
```yaml
wc:
  method: days
  dso_days: 35     # Days Sales Outstanding — set to historical avg (2018-2024: 37d)
  dio_days: 55     # Days Inventory on Hand — historical avg (2018-2024: 54d)
  dpo_days: 70     # Days Payable Outstanding — historical avg (2018-2024: 70d)
                   # IMPORTANT: calibrate to history; wrong DPO causes large AP jump in year 1
  transform_days: dln
  floors:
    ar_days: 5
    inv_days: 10
    ap_days: 5
```

**Dynamic WC days (macro-cycle sensitivity):** When revenue declines, the model automatically extends DSO/DIO (customers slow down, inventory accumulates) and compresses DPO (suppliers tighten). The adjustment is bounded at ±20%:
- `adj_dso = clamp(1.0 - 0.3 × rev_growth, 0.80, 1.20)`
- `adj_dih = clamp(1.0 - 0.4 × rev_growth, 0.80, 1.20)`
- `adj_dpo = clamp(1.0 + 0.2 × rev_growth, 0.80, 1.20)`

This is automatic — no additional configuration required.

---

#### `model.standard.ppe`
```yaml
ppe:
  mode: full
  net_pct_revenue: 0.75
  useful_life_years: 12
  min_capex_da_ratio: 0.90  # CapEx/DA floor: maintenance capex >= 90% of DA
                             # Prevents structural underspend when revenue declines
                             # and fixed % CapEx method would produce CapEx/DA < 1.0×
```

**CapEx floor logic:** Each year `capex = max(raw_capex, prev_DA × min_capex_da_ratio)`. The floor is binding when `revenue × capex_pct < prev_DA × ratio`. Set to `0.0` to disable.

**Additional project CapEx (additive):**
```yaml
ppe:
  additional_capex:   # One-time project additions ON TOP of modeled CapEx (in millions)
    2026: 200         # $200M project in 2026 (additive, not override)
    2027: 150
```

---

#### `model.standard.equity`
```yaml
equity:
  mode: full
  dividend_payout_ratio: 0.03     # 3% of Net Income as dividends
  buyback_pct_fcf: 0.15           # 15% of prior-year FCF as share buybacks
  buyback_leverage_max: 2.0       # Buyback gate: only if ND/EBITDA < 2.0×
```

**Capital allocation logic:**
- Dividends: `dividends = NI × dividend_payout_ratio` (unconditional)
- Buybacks: `buybacks = FCF_prev × buyback_pct_fcf` but only when `ND/EBITDA < buyback_leverage_max` AND prior-year FCF > 0
- Uses prior-year FCF (not current) to avoid circular dependency in the solver

**Capital allocation** policy: the model applies dividends first (unconditional), then leverage-gated buybacks, then any scheduled `equity_additional_events`. All are strictly additive.

**Additional equity events (`equity_additional_events`, additive, one-time):**
```yaml
equity:
  additional_events:           # Scheduled events ON TOP of modeled buybacks/dividends
    2026:
      buyback: 500             # $500M special buyback in 2026 (millions)
      issuance: 0
      special_dividend: 0
    2027:
      buyback: 0
      issuance: 200            # $200M equity issuance
```

All additional events are strictly additive (`total = modeled + scheduled`). Financing of extra CapEx is handled automatically by the debt optimizer.

---

#### `model.standard.leases`
```yaml
leases:
  enabled: false
  default_discount_rate: 0.05
  rate_delta_pct: 0.0
  default_payment_frequency: annual
```

**Lease preprocessor metrics** (auto-populated from `lease_schedule` / history; stored in `model_preprocess_metrics`):

| Metric | Description |
|--------|-------------|
| `op_lease_decay_rate` | Annual ROU amortization rate (dep/open_rou) |
| `op_lease_new_leases` | New lease additions as % of prior ROU balance |
| `op_lease_cash_payment` | Cash lease payment as % of lease liability |
| `fin_lease_principal_rate` | Finance lease principal repayment rate |
| `fin_lease_amort_rate` | Finance lease ROU amortization rate |
| `fin_lease_interest_rate` | Effective interest rate on finance leases |
| `fin_lease_new_leases` | New finance lease additions as % of prior balance |

**ASC 842 operating lease accounting:**
- Lease expense → embedded in SG&A (no separate IS line)
- Lease payment → CFF (not CFO)
- BS: `rou_operating` and `lease_liab_cur/ncur_operating`
- Enforced identity: ΔROU = ΔLL each period

**Stress scenarios** can apply shocks to `avg_rate` (applies to both debt and lease discount rates when `rate_delta_pct > 0`). See `stress_scenarios.yaml`.

#### `model.standard.intangibles`
```yaml
intangibles:
  mode: full
  additions_method: pct_of_revenue
  additions_pct_of_revenue: 0.0
  amortization_method: pct_of_balance
  amortization_pct_of_balance: 10.0
  amortization_useful_life_years: 10
  track_gross_and_accum: true
```

---

### `solver`
```yaml
solver:
  max_iter: 10      # Joint iterative solver max iterations (Excel Iterative Calc analog)
  tol: 1000.0       # Convergence tolerance in reporting currency ($1K for USD)
```

The joint solver handles the circular dependency: RC draw ↔ Interest ↔ NI ↔ Cash.
- Schedule-based mode: converges in 2 iterations.
- RC/optimizer mode: converges in 2–3 iterations.
- Set `max_iter: 1` to disable iteration (legacy behavior, not recommended).

---

### `covenants`
```yaml
covenants:
  enabled: true
  methodology: default    # default | steel | energy | custom
  warning_buffer: 0.10    # Warn when within 10% of threshold
  acceleration_triggers:  # Breach of these covenants → callable debt reclassified to ST
    - interest_coverage
    - net_debt_ebitda
  thresholds:
    net_debt_ebitda_max:   4.0
    interest_coverage_min: 2.0
    debt_to_equity_max:    3.0
    current_ratio_min:     1.0
```

**Covenant breach auto-trigger:** When `covenants.acceleration_triggers` is configured AND a breach is detected, the orchestrator automatically re-runs the `covenant_breach` scenario from `stress_scenarios.yaml` (if present). The covenant breach auto-trigger is equivalent to calling:
```python
orchestrator.run_stress(scenario="covenant_breach")
```
The triggered result is included in `ModelResult.stress_results["covenant_breach"]`.

---

### `stress_scenarios.yaml` (separate file)

Stored at `companies/{company}/configs/stress_scenarios.yaml`. Defines named scenarios referenced by the orchestrator and covenants auto-trigger:

```yaml
scenarios:
  covenant_breach:
    description: "Auto-triggered on covenant breach — severe combined shock"
    macro_shocks:
      steel_price_hrc:
        type: percentage        # percentage | absolute | pp
        value: -15.0            # -15% steel price
      steel_ppi_iron_steel:
        type: percentage
        value: -10.0
    driver_shocks:
      avg_rate:
        type: pp                # Additive percentage-point shock to all rates
        value: 2.0              # +200bps interest rates
      dso_days:
        type: percentage
        value: 10.0             # +10% receivables days (credit tightening)
      dih_days:
        type: percentage
        value: 10.0             # +10% inventory days (demand slowdown)
```

---

### `rating`
```yaml
rating:
  methodology: sp                   # sp | moodys | fitch
  industry_adjustment: -8.0         # Score adjustment (points) for industry risk
                                    # Cyclical/commodity industries: negative (-5 to -10)
                                    # Defensive industries: 0 to +3
  size_adjustment: 3.0              # Score adjustment for company size
                                    # Large integrated producer: +2 to +5
  cycle_avg_ebitda_margin: 0.10     # Through-the-cycle average EBITDA margin
                                    # Used to normalize profitability score:
                                    # norm_margin = min(actual, cycle_avg × 1.5)
                                    # Prevents rating inflation in boom years
  weights:
    leverage:      0.35             # ND/EBITDA — most important for cyclical cos
    coverage:      0.30             # EBITDA/interest
    profitability: 0.20             # TTC-normalized EBITDA margin
    liquidity:     0.15             # Current ratio + FCF/debt
```

**Rating steel methodology** (`methodology: steel`) adds two extra covenants beyond default: `ebitda_margin_min` and `fcf_to_debt_min`. Calibrated for steel sector cyclicality.

**Steel industry calibration (US Steel example):**
- `industry_adjustment: -8.0` — accounts for earnings volatility, commodity price exposure
- `size_adjustment: +3.0` — large integrated producer, diversified end-markets
- `cycle_avg_ebitda_margin: 0.10` — through-the-cycle avg 2018–2024
- Result: 2024 historical = BB+ (exact match vs S&P actual)

**Score→Rating mapping (steel-calibrated thresholds):**

| Score Range | Grade | Category |
|-------------|-------|----------|
| ≥ 95 | AAA | Investment Grade |
| 85–94 | AA | Investment Grade |
| 75–84 | A | Investment Grade |
| 63–74 | BBB | Investment Grade |
| 52–62 | BB | Speculative Grade |
| 42–51 | B | Speculative Grade |
| 30–41 | CCC | Distressed |
| < 30 | D | Default |

---

### `features`
```yaml
features:
  min_cash: 500000000.0   # Override minimum cash (in db_unit)
                          # Set 0 or omit to use preprocessor auto-computed
  # These are auto-detected from data; explicit flags override auto-detection:
  # use_ppe_corkscrew:         true
  # use_wc_days:               true
  # use_tax_corkscrew:         true
  # use_debt_rc:               true
  # use_intangibles_corkscrew: true
  # use_interest_payable_cork: true
```

---

### `forecast_methods`

Override the default forecast method for any specific line item:

```yaml
forecast_methods:
  is:
    asset_impairment:
      method: zero              # One-time item → zero in forecast

    restructuring:
      method: zero

    earnings_from_investees:
      method: ewa
      ewa_halflife_years: 3
      sign: -1                  # Stored negative in DB (income convention)

    interest_income:
      method: ewa
      ewa_halflife_years: 2
      sign: -1

    sga:
      method: driver
      driver_base: revenue
      driver_ratio: history     # Auto-computed from history; or explicit float: 0.08

  bs:
    goodwill:
      method: last              # Carry forward (static asset)

    employee_benefits:
      method: ewa
      ewa_halflife_years: 5

  cf:
    # CF fields typically auto-populated from YearState
    # Override only for non-standard positions
```

**`sign` parameter:** Use `sign: -1` for metrics stored with inverted sign in the DB (income line items often stored as negative in IS per accounting convention). The model will multiply by -1 when reading history.

---

## Preprocessor Default Chain

When a parameter is not set in YAML, the loader follows this chain:

```
1. YAML explicit value
2. preprocessor `*_recommended` metric (year=-1 summary)
3. History median (computed at load time)
4. Last-resort neutral default (documented per parameter)
```

**Parameters with preprocessor fallback:**

| Parameter | Preprocessor Metric | Last Resort |
|-----------|--------------------|-----------  |
| `cogs_ratio` | `cogs_ratio_recommended` | 0.75 (history median) |
| `sga_ratio` | `sga_ratio_recommended` | history median |
| `capex_to_rev` | `capex_to_rev_recommended` | 0.05 |
| `intang_amort_rate` | `intang_amort_rate_recommended` | 0.10 |
| `avg_interest_rate` | `avg_interest_rate_recommended` | 0.05 |
| `lease_dep_rate` | `lease_dep_rate_recommended` | 0.15 |
| `min_cash` (RC) | `min_cash_recommended` | 0 |
| `tax_rate` | history median `effective_tax_rate` | 0.21 (statutory) |
| `dso/dih/dpo` | `dso/dih/dpo_recommended` | WCBlock defaults |
