# Database Schema — data_mart_v2.db

## Overview

Single SQLite file: **`refactoring_v2/data_mart_v2.db`** (WAL mode, foreign keys ON).

Schema defined in: `engine/database/schema.py` — `SCHEMA_DDL` constant. This is the single source of truth. All tables are created via `create_schema(conn)`.

---

## Table Groups

### 1. Reference Tables

| Table | Purpose |
|-------|---------|
| `companies` | Company master: name, industry, currency, accounting standard, db_unit |
| `periods` | Year × company × is_annual × is_forecast |
| `scenarios` | Scenario registry: base / bull / bear / stress / custom |
| `model_versions` | Version registry for model outputs |

`db_unit` in `companies` table defines the unit of all numeric values for that company (e.g., `tUSD` = thousands of USD).

---

### 2. History Layer (Raw EAV)

Three EAV tables, one per statement type:

| Table | Key | Columns |
|-------|-----|---------|
| `history_is` | (company_id, period_id, metric) | value, source, updated_at |
| `history_bs` | (company_id, period_id, metric) | value, source, updated_at |
| `history_cf` | (company_id, period_id, metric) | value, source, updated_at |

`metric` = internal metric name (e.g., `revenue`, `cash`, `cfo_total`).
`source` = loader identifier (e.g., `excel_2010_2011`, `edgar_2024`).

---

### 3. Schedule Tables (Raw Detail)

| Table | Purpose |
|-------|---------|
| `debt_instruments` | Master record per instrument: type, rate, maturity, amortization profile |
| `debt_schedule` | Annual corkscrew per instrument: open/draw/repay/interest/close |
| `ppe_components` | PPE detail: gross, accumulated, net by component |
| `lease_schedule` | Lease corkscrew: ROU open/dep/close, liab open/interest/payment/close |
| `tax_schedule` | Tax block: EBT, current/deferred tax, DTA/DTL/NOL corkscrews |
| `equity_schedule` | RE corkscrew: open/NI/dividends/buybacks/issuance/close |
| `segment_data` | Segment breakdown of revenue/volume/price |

`debt_instruments` key columns:

| Column | Description |
|--------|-------------|
| `db_type` | `revolving`, `term_amort`, `term_bullet`, `bond_fixed`, `bond_float`, `finance_lease`, `other` |
| `rate_type` | `fixed` or `floating` — floating instruments receive stress rate shocks |
| `callable_flag` | `1` if covenant acceleration clause exists — breach triggers ST reclassification |
| `amortization_profile` | `bullet`, `level_payment`, `custom` |
| `payment_frequency` | `annual`, `semiannual`, `quarterly` |
| `covenant_package` | JSON with ICR/leverage thresholds specific to this instrument |

`lease_schedule` key columns: `rou_open`, `rou_dep`, `rou_additions`, `rou_close`, `liab_open`, `interest_exp`, `payment`, `liab_close`, `discount_rate`, `lease_type` (`operating` / `finance`).

`tax_schedule` key columns: `ebt`, `current_tax`, `deferred_tax`, `dta_open`, `dta_close`, `dtl_open`, `dtl_close`, `nol_open`, `nol_used`, `nol_additions`, `nol_close`. NOL carryforward pool tracked year-by-year; `nol_close` from year N = `nol_open` in year N+1.

**Floating rate tracking:** `debt_instruments.rate_type = floating` marks instruments that receive base rate shocks in stress scenarios (Environmental Revenue Bonds, RC, SOFR-linked term loans).

---

### 4. Detailed Corkscrew Schedules

| Table | Purpose |
|-------|---------|
| `sched_lease_finance` | Finance lease full corkscrew with ROU/liability split |
| `sched_lease_operating` | Operating lease full corkscrew |
| `sched_tax_corkscrew` | DTA/DTL by temp diff type (depreciation, inventory, leases, other) |
| `sched_wc_corkscrew` | WC components: AR/Inv/AP/other_ca/other_cl open/close/delta |
| `interest_paid_split` | Interest paid split: debt vs leases, payable open/close |
| `lease_maturity_ladder` | Maturity schedule by lease and year |
| `balancing_adjustments` | BS identity adjustments with lineage and reason |
| `intangible_assets` | Intangibles by category with amortization |
| `debt_cashflows` | Instrument-level cashflows: interest/principal/drawdown/fee |

---

### 5. Macro Tables

| Table | Purpose |
|-------|---------|
| `macro_factors` | Historical macro factor values (global / industry / company scope) |
| `macro_forecasts` | Forecasted macro values by method and scenario |
| `macro_anomalies` | Z-score anomaly flags for structural break detection |

---

### 6. Preprocessor Table

| Table | Key | Purpose |
|-------|-----|---------|
| `preprocess_metrics` | (company_id, metric_group, metric_name, year) | Computed KPIs |

`year = -1` means a summary metric (EWA/median/recommended scalar).
`metric_group` examples: `revenue`, `cogs`, `sga`, `capex`, `wc`, `debt`, `lease`, `tax`.
`metric_name` examples: `cogs_ratio_recommended`, `capex_to_rev_recommended`, `avg_interest_rate_recommended`, `min_cash_recommended`.

---

### 7. Model Results (Forecast Layer)

| Table | Key | Purpose |
|-------|-----|---------|
| `forecast_is` | (company_id, period_id, scenario_id, metric) | IS forecast values |
| `forecast_bs` | (company_id, period_id, scenario_id, metric) | BS forecast values |
| `forecast_cf` | (company_id, period_id, scenario_id, metric) | CF forecast values |

Same EAV structure as history tables. Version-linked via `version_id`.

---

### 8. Downstream Results

| Table | Purpose |
|-------|---------|
| `stress_results` | Stressed forecast values per scenario, period, statement |
| `covenant_results` | Covenant metrics: value, threshold, headroom, breached flag |
| `ratings` | Credit rating scores and grades per scenario and period |
| `rating_metrics` | Detailed factor-level rating breakdown |

---

### 9. Audit Table

| Table | Purpose |
|-------|---------|
| `audit_log` | All DB operations: INSERT/UPDATE/DELETE/LOAD/RUN with JSON details |

---

## Indexes

Performance indexes on all heavy-query paths:

```sql
idx_history_is_company_year  ON history_is(company_id, period_id)
idx_forecast_is_scenario     ON forecast_is(company_id, scenario_id)
idx_preprocess_company       ON preprocess_metrics(company_id, metric_group)
idx_debt_schedule_company    ON debt_schedule(company_id, period_id)
idx_macro_factors_name       ON macro_factors(factor_name, year)
-- + 10 more indexes for other tables
```

---

## Repository Pattern

Database access through `engine/database/repository.py`:

```python
from engine.database.repository import Repository

repo = Repository(db_path="data_mart_v2.db")
history = repo.get_history(company_id="us_steel", statement="IS", years=[2020, 2021])
repo.save_forecast(company_id="us_steel", scenario_id=1, results=year_states)
```

Key repository methods:
- `get_history(company_id, statement, years)` → `Dict[int, Dict[str, float]]`
- `get_schedules(company_id, years)` → `ScheduleData` dataclass
- `get_preprocess(company_id, metric_group)` → `Dict[str, Any]`
- `get_macro_forecasts(company_id, factor_name, years)` → `Dict[int, float]`
- `save_forecast(company_id, scenario_id, year_states)` → inserts to forecast_is/bs/cf
- `save_preprocess(company_id, metrics_dict)` → upserts to preprocess_metrics

---

## Conventions

- All monetary values stored in **`db_unit`** of the company (e.g., `tUSD` for US Steel = thousands of USD).
- Rates stored as **decimals** (0.21 = 21%, not percent).
- `period_id` is always resolved via `periods` table (never stored as raw year in data tables).
- `is_forecast = 0` for history, `1` for forecast periods.
