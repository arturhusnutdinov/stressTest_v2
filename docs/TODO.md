# stressTest_v2 — TODO / Backlog

Status as of 2026-03-31. Items ordered by priority.

---

## ✅ DONE (this session)

| # | Item | Files |
|---|---|---|
| D1 | Debt optimizer `debt.mode: full` alias → `optimizer` | `engine/model/loader.py` |
| D2 | `allow_new_money` double-counting fix (`opening=0.0`) | `engine/model/schedules/debt.py` |
| D3 | Snapshot-restore for iterative convergence loop | `engine/model/core.py` |
| D4 | `_debt_residual` reconciliation instrument (hist BS gap) | `engine/model/core.py` |
| D5 | `approx_cfo` fix: use `_actual_cfo_est` from prior iteration | `engine/model/core.py` |
| D6 | `_cash_estimate = prev.cash` (prevent double-count CFO) | `engine/model/core.py` |
| D7 | ST/LT 4-rule reclassification (maturity/amort/covenant/RC) | `engine/model/schedules/debt.py` |
| D8 | min_cash updated to $596M (preprocessor recommendation) | `companies/us_steel/configs/project.yaml` |
| D9 | Floating rate: environmental bonds 5%→3.5%, `rate_type=floating` | `migrations/fix_environmental_bonds_rate.py`, `engine/stress/runner.py`, `engine/model/core.py` |
| D10 | ASC 842 operating lease BS identity (ΔROU = ΔLL) | `engine/model/core.py`, `engine/model/schedules/leases.py` |
| D11 | NOL carryforward TCJA (80% taxable income limit, indefinite) | `engine/model/schedules/tax.py`, `engine/model/core.py` |
| D12 | Covenant auto-trigger → re-runs `covenant_breach` scenario | `engine/orchestrator.py`, `companies/us_steel/configs/stress_scenarios.yaml` |
| D13 | ModelConfig: `da_in_cogs`, `capitalize_interest` fields | `engine/model/inputs.py`, `engine/model/loader.py` |
| D14 | ModelConfig convenience properties: `nol_enabled`, `nol_limit_pct`, `statutory_rate`, `dividend_pct_ni` | `engine/model/inputs.py` |
| D15 | Excel export v3: `Lease_Schedule` + `NOL_Tax` sheets, 38-instrument `Debt_Instruments` | `companies/us_steel/data/us_steel_data_export_v2.xlsx` |
| D16 | `excel_loader.yaml`: lease maturity schedule + capitalized interest mappings | `companies/us_steel/configs/excel_loader.yaml` |
| D17 | All 6 notebooks updated (NOL §7.4, lease corkscrew §7.5, covenant auto-trigger) | `notebooks/*.ipynb`, `companies/us_steel/notebooks/*.ipynb` |
| D18 | Documentation updated (modeling schema, YAML config, stress/covenants) | `docs/01_MODELING_SCHEMA.md`, `docs/03_YAML_CONFIGURATION.md`, `docs/06_STRESS_RATING_COVENANTS.md` |

**Result**: BS_diff = 0.0 all years, base + all 3 stress scenarios.
IntExp base 2025: $205M (was $216M — ~$11M reduction from correct 3.5% vs 5% fallback).
NOL effective rate 2025: −4.2%. Rating 2025: BBB+. 38 debt instruments, 11 lease_schedule rows.

---

## 🔶 TODO — Priority 1 (affects model accuracy)

### ~~TODO-3: Floating rate instruments (Environmental Revenue Bonds)~~ ✅ DONE
Set `interest_rate=3.5%`, `rate_type=floating`, `base_rate_factor=sofr` via migration.
Stress runner now only applies rate shocks to `rate_type='floating'` instruments.
Model applies `general_rate_delta_pct` to floating instruments (stress config offset).
IntExp 2025: $205M (was $216M).

### ~~TODO-4: Covenant acceleration → LT→ST reclassification~~ ✅ DONE (auto-trigger)
Covenant breach now auto-triggers re-run of `covenant_breach` stress scenario (orchestrator level).
Callable instrument reclassification (instrument-level `_covenant_breach_instruments` hook) is still pending for per-instrument ST/LT split — but orchestrator-level auto-trigger is implemented and tested.

---

## 🔷 TODO — Priority 2 (audit trail / reporting)

### ~~TODO-5: Forecast debt schedule → DB~~ ✅ DONE
`ModelResult.debt_lines` stores `List[DebtYearLine]` per year.
`ModelSaver._save_debt_schedule` persists to `debt_schedule` (30 instruments × 5 years).
Notebooks can now query per-instrument forecast balances and interest expense.

### TODO-6: Base year corkscrew reconciliation plugs
**What**: PPE, WC, and equity corkscrews for base year may have FX effects, reclassifications, or non-cash adjustments not captured in the standard open+capex-dep=close formula.
**Fix**: Store reconciliation residuals in `preprocess_metrics` (e.g., `ppe_plug_2024 = actual_close - (open+capex-dep)`) so the model can use them as year-1 opening adjustments.
**Files**: `engine/model/preprocess.py`, `engine/model/preprocessing/metrics/`

---

## 🔹 TODO — Priority 3 (model quality improvements)

### ~~TODO-7: Deferred tax TaxBlock full implementation~~ ✅ DONE
Full TaxBlock rewrite (`engine/model/schedules/tax.py`): new dataclass with
`accel_dep_excess`, `pension_dta_delta`, `other_dtl_delta`, `other_dta_delta`, `payment_lag`.
IS: `total_tax_expense = current_tax_expense` (statutory × taxable_income only).
CFO: `cfo_deferred_tax = dtl_delta − dta_delta` (+74M/yr when DTL grows).
`_nol_carryforward` initialized in `ThreeStatementModel.__init__`, persisted across years.
DTL: $657M → $731M → $806M → $881M → $955M → $1028M. BS_diff = 0 all years + all scenarios.

### TODO-8: Revenue macro chain — HRC price beta
**What**: Revenue forecast uses EWA/LAST method. No macro linkage to HRC steel price.
**Fix**: Add `beta_hrc` coefficient from preprocessor; revenue = f(HRC_forecast) in macro mode.
**Files**: `engine/model/preprocessing/metrics/beta_coefficients.py`, `companies/us_steel/configs/project.yaml`

### ~~TODO-9: CapEx normalization post-BigRiver acquisition~~ ✅ DONE
Added `capex_pct_by_year` (2025: 8%, 2026: 7%, 2027-2029: 6%) to `capex_policy` in YAML.
Model uses year-specific rate before fallback to `ratio_default`.
Added `capex_pct_by_year` support to `ModelConfig`, loader, and `_solve_ppe`.

---

## ℹ️ ARCHITECTURE NOTES

- **ST/LT split rules** (debt.py Step 6): RC→ST, maturity==year+1→ST, amort_next_yr→split, covenant_breach→ST, else LT
- **callable_flag**: `debt_instruments.callable_flag = 1` → subject to acceleration; `_covenant_breach_instruments` hook for ST reclassification
- **Buyback gate**: `buyback_pct_fcf × FCF_prev` only executes when `ND/EBITDA < buyback_leverage_max` AND prior FCF > 0
- **NULL rates fallback**: `interest_rate IS NULL` → `cfg.avg_rate_pct = 5.0%` (see `core.py:_build_instruments_open_from_raw:1206`)
- **min_cash source**: `preprocess_metrics.debt.min_cash_15day_opex = $595.7M` → YAML `rc.min_cash = 596000000`
