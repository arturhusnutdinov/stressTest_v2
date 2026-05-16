# Modeling Schema — Three-Statement Model

## Overview

`engine/model/core.py` — `ThreeStatementModel` class. Processes one company × one scenario × N forecast years. Returns a list of `YearState` objects (one per year).

---

## YearState — Full State Object

`YearState` (in `engine/model/inputs.py`) is a flat dataclass holding every modeled line item for one year. It is populated incrementally by `_solve_year()`.

**Income Statement fields:**
- `revenue`, `cogs`, `gross_profit`
- `sga`, `dep_ppe`, `dep_rou`, `amort_intangibles`, `total_da`
- `ebitda`, `ebit`
- `asset_impairment`, `restructuring`, `other_losses_gains`
- `earnings_from_investees`, `net_periodic_benefit`
- `interest_expense_debt`, `interest_expense_leases`, `interest_expense`
- `interest_income`, `loss_on_debt_extinguishment`, `other_financial_costs`
- `ebt`, `tax_expense`, `net_income`, `eps_basic`, `eps_diluted`

**Balance Sheet fields:**
- Current assets: `cash`, `restricted_cash`, `accounts_receivable`, `inventory`, `other_ca`, `total_ca`
- Non-current assets: `ppe_gross/accum/net`, `rou_asset`, `intangibles`, `goodwill`, `investments_lt`, `dta`, `other_nca`, `total_nca`, `total_assets`
- Current liabilities: `short_term_debt`, `accounts_payable`, `taxes_payable`, `interest_payable`, `lease_liab_current`, `other_cl`, `total_cl`
- Non-current liabilities: `long_term_debt`, `lease_liab_noncurrent`, `employee_benefits`, `dtl`, `other_ncl`, `total_ncl`, `total_liabilities`
- Equity: `share_capital`, `apic`, `treasury_stock`, `retained_earnings`, `aoci`, `nci`, `total_equity`, `total_liab_equity`

**Cash Flow fields:**
- CFO: `cfo_net_income`, `cfo_total_da`, `cfo_deferred_tax`, WC changes, interest paid, taxes paid, `cfo_total`
- CFI: `cfi_capex`, `cfi_disposal_proceeds`, `cfi_acquisitions`, `cfi_total`
- CFF: `cff_debt_proceeds`, `cff_debt_repayments`, `cff_rc_draw`, `cff_rc_repay`, `cff_dividends`, `cff_buybacks`, lease payments, `cff_total`
- `net_change_cash`, `cash_beginning`, `cash_ending`

---

## Forecast Methods (ForecastMethod enum)

| Method | Description | Key Parameters |
|--------|-------------|----------------|
| `MACRO` | Elastic Net regression on macro factors | `macro_factors`, `macro_model` |
| `DRIVER` | % of base line item (revenue, cogs, etc.) | `driver_base`, `driver_ratio` |
| `DAYS` | Working capital turnover (DSO/DIH/DPO) | `days_metric`, `days_base`, `days_floor` |
| `CORK` | Corkscrew roll-forward schedule | `corkscrew_type`, `corkscrew_field` |
| `EWA` | Exponentially Weighted Average | `ewa_halflife_years` (default 3.0) |
| `LAST` | Carry forward last historical value | — |
| `ZERO` | Zero in forecast (one-time items) | — |
| `CALC` | Formula of other line items | `calc_formula` |
| `PLUG` | Balancing item (absorbs residual) | `plug_min_value`, `plug_absorbs_gap` |
| `LINK` | Link to another statement | `link_source`, `link_field` |

Configured in `project.yaml` under `forecast_methods.is / bs / cf`.

---

## `_solve_year()` — Joint Iterative Solver

The core solver handles the circularity: **RC draw → Interest → Net Income → Cash → RC draw**.

```
Non-iterative (computed once):
  _solve_revenue → _solve_cogs → _solve_sga → _solve_ppe
  _solve_other_is → _solve_wc → _solve_lease → _solve_bs_other

Iterative loop (max_iter=10, tol=$1K):
  iteration 0: cash_estimate = _estimate_cash_before_debt(state, prev)
  iteration 1+: cash_estimate = prev_cash (already accurate)

  Each iteration:
    _solve_debt          ← RC draw/repay uses cash_estimate
    _solve_interest_payable
    _solve_is_subtotals  ← EBIT, EBT, EBITDA
    _solve_tax_block
    _solve_equity
    _solve_bs_totals
    _solve_cash_plug
    _solve_cf

  Convergence: |cash_delta| < tol AND |ni_delta| < tol
```

Converges in **2 iterations** for schedule-based debt mode, **2–3 iterations** for RC/optimizer mode.

Solver parameters in `project.yaml`:
```yaml
solver:
  max_iter: 10      # Excel Iterative Calculation analog
  tol: 1000.0       # $1K tolerance in reporting currency
```

---

## Block-by-Block Logic

### Revenue (`_solve_revenue`)
- Default method: macro regression (Elastic Net on steel_price_hrc, gdp_us, etc.)
- Fallback chain: VECM → EWA from history
- Segment modeling supported (volume × price decomposition)

### COGS (`_solve_cogs`)
- Method: `DRIVER` (% of revenue) or `MACRO` (PPI-linked)
- Ratio source: preprocessor `cogs_ratio_recommended` → history median → 0.75 last resort
- PPI uplift: optional, driven by `ppi_us` factor with configurable beta

### SG&A (`_solve_sga`)
- Method: `EWA` ratio from history or `DRIVER`
- Ratio source: preprocessor `sga_ratio_recommended` → history median
- CPI indexation: optional (`index_by_cpi: true`)

### PPE (`_solve_ppe`)
- Two modes: `simple` (dep_to_rev ratio) and `full` (gross → accum corkscrew)
- CapEx: preprocessor `capex_to_rev_recommended` → last resort 5% revenue
- **CapEx floor:** `capex = max(raw_capex, prev_DA × min_capex_da_ratio)`. Prevents structural underspend when revenue declines and fixed `%` capex would fall below maintenance level. Configured via `ppe.min_capex_da_ratio` (default 0.90).
- **Additional project CapEx (`additional_capex`):** `additional_capex_schedule[year]` adds on top of modeled CapEx. Strictly additive.
- Depreciation: straight-line, useful life from schedule or config
- Intangibles: `intang_amort_rate_recommended` from preprocessor

### Working Capital (`_solve_wc`)
- Method: `DAYS` (DSO/DIH/DPO) or `DRIVER`
- DSO/DIH/DPO: preprocessor recommended → config defaults → `WCBlock.from_days` built-in defaults
- **Dynamic WC days (macro-cycle adjustment):** automatically extends DSO/DIO and compresses DPO when revenue declines (±20% bounds). No additional config required.
- WC delta flows to CFO

### Leases (`_solve_lease`)
- Finance leases: ROU asset dep + interest to IS; principal to CFF
- Operating leases (ASC 842): lease expense embedded in SG&A; lease payment flows to CFF; **no separate CF adjustment**
- **BS Identity (ΔROU = ΔLL):** Operating lease ROU asset and lease liability move in lockstep each period — `rou_operating_close = rou_operating_open - rou_dep + rou_additions`; `lease_liab_close = lease_liab_open - principal_paid + new_leases`; and `ΔROU = ΔLL` is enforced by the model
- Dep rate: preprocessor `lease_dep_rate_recommended` → 15% default
- 7 preprocessor lease metrics populated: `op_lease_decay_rate`, `op_lease_new_leases`, `op_lease_cash_payment`, `fin_lease_principal_rate`, `fin_lease_amort_rate`, `fin_lease_interest_rate`, `fin_lease_new_leases`

### Tax (`_solve_tax_block`)
- Effective rate: history median from preprocessor → 21% statutory last resort
- **NOL carryforward (TCJA):** `nol_used = min(nol_open, ebt × nol_max_utilization_pct)` — limited to `nol_max_utilization_pct` (default 80%) of taxable income, NOT 80% of pool; indefinite carryforward
- NOL corkscrew: `nol_open + nol_losses_added - nol_used = nol_close` — carried across years in `_nol_carryforward`; opening balance set in YAML `taxes.nol_opening_balance`
- **NOL safety:** `_nol_year_open` is frozen before the convergence loop so iterative solver changes to NI don't double-count NOL consumption
- DTA/DTL corkscrew driven by deferred tax; accelerated depreciation excess (`accel_dep_excess_pct`) generates DTL

### Debt (`_solve_debt`)
Three modes:
- `schedule_based` — reads pre-computed corkscrew from DB, sums instruments
- `parametric` — target debt = `target_pct_revenue × revenue`; RC fills gap
- `optimizer` — LP minimizing cash deficit + ICR/leverage covenant violations

**Instrument attributes affecting model behavior:**
- `callable_flag = 1` → subject to covenant acceleration; on breach, reclassified to ST debt
- `rate_type = floating` → floating rate instruments receive `general_rate_delta_pct` stress shocks; fixed-rate bonds do not
- **TaxBlock DTL:** accelerated depreciation (`accel_dep_excess_pct`) generates deferred tax liability (DTL) in `_solve_tax_block`; interest deductibility feeds into the NOL carryforward pool

**Covenant breach auto-trigger** (orchestrator level): when any `acceleration_triggers` covenant is breached in `_solve_covenants`, the orchestrator re-runs `covenant_breach` scenario automatically. See `06_STRESS_RATING_COVENANTS.md`.

**Rating steel methodology:** `industry_adjustment: -8.0` applied to raw score for cyclical commodity exposure. Four-factor: leverage (35%), coverage (30%), profitability (20%), liquidity (15%). Through-the-cycle EBITDA normalization prevents rating inflation in boom years.

### Interest Payable (`_solve_interest_payable`)
- `interest_payable_open + interest_accrued - interest_paid = interest_payable_close`
- Payment timing: current year or next year (config: `interest_payable.payment_timing`)

### Equity (`_solve_equity`)

**Capital allocation** policy governs how free cash flow is distributed:
- RE corkscrew: `re_open + net_income - dividends - buybacks + issuance = re_close`
- **Dividends:** `net_income × dividend_payout_ratio` (configured in YAML, default 0)
- **Buybacks (leverage-gated):** `buybacks = FCF_prev × buyback_pct_fcf` but only when `ND/EBITDA < buyback_leverage_max` AND prior-year FCF > 0. Uses prior-year FCF to avoid circular dependency.
- **Additional equity events (`equity_additional_events`):** `equity_additional_events[year]` adds scheduled buybacks/issuances/special dividends on top of modeled amounts. Strictly additive.

### Cash Plug (`_solve_cash_plug`)
- `cash = prev.cash + cfo_total + cfi_total + cff_total`
- Balancing item: `bs_cash_plug` corrects for any BS rounding

---

## BS Identity Check

At every year-end:
```
total_assets = total_liabilities + total_equity
```

Mismatch → `logger.error` + stored in `balancing_adjustments` table. Target: diff = 0.

---

## ModelConfig — Top-Level Config Dataclass

Key fields (in `engine/model/inputs.py`):

| Field | Type | Source |
|-------|------|--------|
| `mode` | str | YAML `model.mode` |
| `history_start_year` | int | YAML |
| `forecast_start_year` | int | YAML |
| `forecast_end_year` | int | YAML |
| `tax_rate` | float | preprocessor / YAML |
| `debt` | `DebtSettings` | YAML `model.standard.debt` |
| `lease` | `LeaseDrivers` | YAML `model.standard.leases` |
| `max_iter` | int | YAML `solver.max_iter` (default 10) |
| `tol` | float | YAML `solver.tol` (default 1000.0) |
| `forecast_methods` | dict | YAML `forecast_methods` |
| `min_capex_da_ratio` | float | YAML `ppe.min_capex_da_ratio` (default 0.90) |
| `additional_capex_schedule` | Dict[int, float] | YAML `ppe.additional_capex` (millions → internal) |
| `dividend_payout_ratio` | float | YAML `equity.dividend_payout_ratio` |
| `buyback_pct_fcf` | float | YAML `equity.buyback_pct_fcf` (default 0.0) |
| `buyback_leverage_max` | float | YAML `equity.buyback_leverage_max` (default 2.0) |
| `equity_additional_events` | Dict[int, Dict] | YAML `equity.additional_events` (millions → internal) |
| `da_in_cogs` | bool | YAML `accounting_conventions.da_in_cogs` (default `true`) |
| `capitalize_interest` | bool | YAML `accounting_conventions.capitalize_interest` (default `false`) |

**Convenience properties** (read-only aliases — no YAML key):

| Property | Returns | Purpose |
|----------|---------|---------|
| `nol_enabled` | bool | `True` when `nol_opening_balance > 0` |
| `nol_limit_pct` | float | Alias for `nol_max_utilization_pct` (TCJA 80% cap) |
| `statutory_rate` | float | Alias for `tax_rate` or `0.21` fallback |
| `dividend_pct_ni` | float | Alias for `dividend_payout` |
