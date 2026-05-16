# Data Loading — ExcelLoader and Preprocessor

## Overview

Data flows into the model through two independent stages:

```
Excel file (rusal_unified_complete.xlsx)
      │
      ▼
  ExcelLoader                 ← engine/loader/excel.py
  (parses Excel, applies unit conversion, populates DB)
      │
      ▼
  history_is / history_bs / history_cf  (EAV tables in DB)
      │
      ▼
  Preprocessor                ← engine/preprocessor/core.py
  (compute KPIs and recommended defaults)
      │
      ▼
  preprocess_metrics table
      │
      ▼
  ModelLoader                 ← engine/model/loader.py
  (assemble ModelConfig + HistoricState + Drivers)
      │
      ▼
  ThreeStatementModel         ← engine/model/core.py
```

---

## Stage 1: History Loading

### Loader Scripts

Located in `companies/us_steel/loaders_legacy/`. One script per 2-year period (Excel report cadence):

```
load_master_balance_sheet_2010_2011.py
load_master_balance_sheet_2012_2013.py
...
load_master_balance_sheet_2022_2023.py
load_master_balance_sheet_2024.py
load_master_cash_flow_2010_2012.py
...
load_master_income_statement_2010_2012.py
...
```

Each script:
1. Reads source Excel file (mapped via `excel_loader.yaml`)
2. Normalizes metric names to internal schema
3. Applies unit conversion if needed
4. Upserts into `history_is / history_bs / history_cf`

### Running History Load

```bash
# From refactoring_v2/ directory:
PYTHONPATH=. python companies/us_steel/loaders_legacy/load_master_balance_sheet_2024.py
```

### Metric Naming Convention

Internal metric names follow snake_case IS/BS/CF structure:
- IS: `revenue`, `cogs`, `gross_profit`, `sga`, `ebitda`, `ebit`, `ebt`, `net_income`
- BS: `cash`, `accounts_receivable`, `inventory`, `ppe_net`, `long_term_debt`, `retained_earnings`
- CF: `cfo_total`, `cfi_capex`, `cff_debt_proceeds`, `net_change_cash`

### `accounting_conventions.yaml`

Controls sign conventions per metric. Metrics marked as `positive_in_flow: true` are stored as positive in the CF statement (e.g., `cfi_capex` stored as negative, disposals as positive).

---

## Stage 2: Preprocessor

### `engine/preprocessor/core.py` — `Preprocessor` class

Reads history from DB and computes derived KPIs for each metric group.

```python
from engine.preprocessor.core import Preprocessor

pp = Preprocessor(company_id="us_steel", db_path="data_mart_v2.db")
pp.run()   # computes all groups, saves to preprocess_metrics table
```

### Metric Groups Computed

| Group | Key Outputs |
|-------|------------|
| `revenue` | `revenue_cagr`, `revenue_ewa`, `growth_rate_recommended` |
| `cogs` | `cogs_ratio_recommended`, `cogs_ratio_by_year`, `cogs_ppi_beta` |
| `sga` | `sga_ratio_recommended`, `sga_ratio_by_year` |
| `capex` | `capex_to_rev_recommended`, `dep_to_rev_recommended` |
| `wc` | `dso_recommended`, `dih_recommended`, `dpo_recommended` |
| `debt` | `avg_interest_rate_recommended`, `net_debt_ebitda_by_year`, `min_cash_recommended` |
| `lease` | `lease_dep_rate_recommended`, `rou_to_rev_recommended`, `op_lease_decay_rate`, `op_lease_new_leases`, `op_lease_cash_payment`, `fin_lease_principal_rate`, `fin_lease_amort_rate`, `fin_lease_interest_rate`, `fin_lease_new_leases` |
| `tax` | `effective_tax_rate_by_year`, `effective_tax_rate_recommended` |
| `intangibles` | `intang_amort_rate_recommended` |

### `min_cash` Computation

The preprocessor computes `min_cash_recommended` as:

```
min_cash = max(
    P10 of historical cash balances,
    15-day operating expenses (COGS + SG&A) / 365 × 15,
    2% of last-year revenue
)
```

Stored as `preprocess_metrics(metric_group="debt", metric_name="min_cash_recommended", year=-1)`.

The loader picks this up automatically if `rc.min_cash` is 0 or absent in YAML.

### EWA Helper

```python
from engine.preprocessor.core import ewa

result = ewa(
    {2020: 0.30, 2021: 0.28, 2022: 0.27},   # year → value dict
    halflife_years=3
)
```

Returns a single float: the exponentially weighted average (recent years weighted more).

---

## Stage 3: Model Loader

### `engine/model/loader.py` — `ModelLoader` class

Assembles all inputs into typed dataclasses:

```python
from engine.model.loader import ModelLoader

loader = ModelLoader(
    company_id="us_steel",
    config_path="companies/us_steel/configs/project.yaml",
    db_path="data_mart_v2.db"
)

model_config = loader.load_config()      # ModelConfig dataclass
historic_state = loader.load_history()   # HistoricState (dict by year)
drivers = loader.load_drivers()          # Drivers (macro forecasts)
schedules = loader.load_schedules()      # ScheduleData (debt/lease/tax/equity)
```

### Loader Priority Chain

For each parameter requiring a calibrated value:

1. **YAML explicit** — if value is set and non-zero
2. **Preprocessor `_recommended`** — `repo.get_preprocess(company_id, group)["metric_recommended"]`
3. **History median** — computed from loaded history data at runtime
4. **Last-resort default** — minimal safe value (documented per parameter)

### Debt Schedule Loading

```python
# Reads debt_instruments + debt_schedule tables
# Builds DebtInstrument objects with embedded schedule dicts
instruments = loader.load_debt_instruments()
# Returns: List[DebtInstrument], each with .schedule = {year: {open, draw, repay, interest, close}}
# Key instrument attributes loaded:
#   callable_flag: bool — covenant acceleration instruments
#   rate_type: str — 'fixed' or 'floating' (floating rate instruments get stress rate shocks)
#   amortization_profile, payment_frequency, covenant_package
```

Note: `additional_capex` schedule (YAML `ppe.additional_capex`) is loaded via `loader.load_additional_capex()` → `ModelConfig.additional_capex_schedule`. Strictly additive to modeled CapEx.

### NOL Opening Balance Loading

NOL carryforward pool is loaded from YAML and passed directly to `ModelConfig` — no preprocessor fallback since it's a company-specific known quantity, not a calibrated ratio.

```python
# In loader.py — taxes section:
nol_opening_balance = taxes_raw.get("nol_opening_balance", 0.0)
nol_max_utilization_pct = taxes_raw.get("nol_max_utilization_pct", 0.80)
# US Steel: nol_opening_balance = 1014.0 (millions, = $1,014M)
# TCJA rule: nol_used = min(nol_open, ebt × nol_max_utilization_pct)
# Indefinite carryforward: nol_expiration_years = 999
```

### Accounting Conventions Loading

```python
# In loader.py — from accounting_conventions section of project.yaml:
da_in_cogs = bool(cfg.get("accounting_conventions", {}).get("da_in_cogs", True))
capitalize_interest = bool(cfg.get("accounting_conventions", {}).get("capitalize_interest", False))
# Stored on ModelConfig.da_in_cogs and ModelConfig.capitalize_interest
```

### RC `min_cash` Loading

```python
# In loader.py:
yaml_min_cash = rc_raw.get("min_cash", 0)
if yaml_min_cash and float(yaml_min_cash) > 0:
    min_cash_final = float(yaml_min_cash)       # YAML wins
else:
    pp_debt = self._repo.get_preprocess(self.company_id, "debt")
    pp_min_cash = pp_debt.get("min_cash_recommended")
    if isinstance(pp_min_cash, dict):
        pp_min_cash = pp_min_cash.get(-1)       # year=-1 summary
    min_cash_final = float(pp_min_cash) if pp_min_cash else 0.0
```

### Macro Driver Loading

```python
# Reads macro_forecasts table (populated by macro module)
drivers = loader.load_drivers()
# drivers.macro_forecasts: {factor_name: {year: value}}
# drivers.factor_names: List[str]
```

---

## Data Flow for `HistoricState`

`HistoricState` is a `Dict[int, Dict[str, float]]` — year → metric → value.

Built from `history_is + history_bs + history_cf` tables, with:
1. Period ID → year conversion
2. Unit normalization (all values in `db_unit` of company)
3. Metric name validation against internal schema
4. NaN / None handling (replaced with 0.0 or interpolated)

---

## Loading New Company

1. Copy `templates/project_template.yaml` → `companies/{company}/configs/project.yaml`
2. Fill in company metadata, macro factors, history paths
3. Create loader scripts (or use generic CSV loader)
4. Run: `PYTHONPATH=. python companies/{company}/loaders/load_history.py`
5. Run preprocessor: `PYTHONPATH=. python -m engine.preprocessor.core --company {company}`
6. Verify: `PYTHONPATH=. python -m engine.orchestrator --company {company} --dry-run`


---

## PDF Parser (parsers/)

For companies publishing financial statements as PDFs.

**Implemented for:** Rusal (EN Financial Statements)

See: [08_PDF_PARSER_GUIDE.md](08_PDF_PARSER_GUIDE.md)

### Schedule Sheet Loader

`tools/load_schedule_sheets.py` — loads Notes corkscrew data from Excel:
- Intangibles, Tax DTA/DTL, Provisions, Associates, Operational Drivers

```bash
python3 tools/load_schedule_sheets.py --company rusal
```
