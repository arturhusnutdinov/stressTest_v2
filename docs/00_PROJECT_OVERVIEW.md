# Project Overview — Financial Stress-Test Engine (stressTest_v2)

## Purpose

Three-statement financial model (IS / BS / CF) for corporate financial modeling and stress testing. Designed to forecast P&L, Balance Sheet, and Cash Flow for public companies using a combination of macro-driven regression, rule-based corkscrew schedules, and iterative joint solvers.

**Production companies:**
- **US Steel** (US GAAP, 2010–2024 history, 2025–2029 forecast)
- **UC RUSAL** (IFRS, 2011–2025 history, 2026–2030 forecast)

---

## Directory Structure

```
stressTest_v2/
├── engine/                  # Core engine modules
│   ├── model/               # Three-statement model (core.py, inputs.py, loader.py)
│   │   ├── cogs_block.py    # Component-based COGS (alumina, energy, labour)
│   │   └── segment_revenue.py # Segment Volume × Price revenue model
│   ├── macro/               # Macro module: VECM, ARIMA, EWA, commodity models
│   ├── preprocessor/        # Historical KPI extraction and ratio computation
│   ├── database/            # SQLite schema, repository, connection wrapper
│   ├── loader/              # ExcelLoader: Excel → DB pipeline
│   ├── stress/              # Stress scenario runner
│   ├── rating/              # Credit rating engine (S&P/Moody's/Fitch)
│   ├── covenants/           # Covenant monitoring
│   └── orchestrator.py      # Top-level pipeline orchestrator
├── companies/
│   ├── us_steel/
│   │   ├── configs/         # project.yaml, excel_loader.yaml, stress_scenarios.yaml
│   │   ├── data/excel/      # UNIFIED Excel data file
│   │   └── notebooks/       # 10 Jupyter notebooks
│   └── rusal/
│       ├── configs/         # project.yaml, excel_loader.yaml, stress_scenarios.yaml
│       ├── data/            # rusal_unified_complete.xlsx (32 sheets)
│       └── notebooks/       # 10 Jupyter notebooks
├── templates/
│   └── project_template.yaml   # Canonical YAML config template
├── configs/                 # Global config (db path, logging)
├── tests/                   # pytest suite
├── notebooks/               # Jupyter analysis notebooks
├── scripts/                 # CLI helper scripts
├── tools/                   # Diagnostic and migration tools
├── docs/                    # This documentation
└── data_mart_v2.db          # SQLite database (WAL mode)
```

---

## Engine Architecture

The engine follows a **layered pipeline**:

```
History (CSV / DB)
        │
        ▼
  Preprocessor              ← computes ratios, medians, EWA, min_cash
        │
        ▼
  Macro Module              ← VECM / ARIMA / EWA forecast of macro factors
        │
        ▼
  Model Loader              ← reads YAML config, assembles ModelConfig + HistoricState
        │
        ▼
  ThreeStatementModel       ← joint iterative solver, 10 forecast methods
        │
        ▼
  ModelSaver / Repository   ← writes forecast_is/bs/cf to DB
        │
        ▼
  Stress Runner             ← applies shocks to forecasted values
        │
        ▼
  Rating Engine             ← S&P / Moody's / Fitch methodology scorecards
        │
        ▼
  Covenant Monitor          ← checks thresholds, computes headroom
```

---

## Key Design Principles

1. **Model does not know about DB or YAML** — all data arrives as typed dataclasses (`ModelConfig`, `HistoricState`, `Drivers`). The loader is the only place that touches files and DB.

2. **Preprocessor as single source of calibrated defaults** — ratios, rates, and operating parameters flow from preprocessor → `preprocess_metrics` table → loader → `ModelConfig`. No hardcoded magic numbers in `core.py`.

3. **Joint iterative solver** — `_solve_year()` runs a convergence loop (max 10 iterations, tol=$1K) for the circular dependency chain: RC draw ↔ Interest ↔ Net Income ↔ Cash. Analogous to Excel Iterative Calculation.

4. **Corkscrew schedules built in-memory** — PPE, Debt, Leases, Tax, WC, Equity corkscrews are computed during model run from raw schedules loaded from DB. They are not stored separately.

5. **YAML is the single source of forecast method configuration** — `project.yaml` controls every forecast method override. If not specified, defaults come from preprocessor.

6. **Plug semantics** — `plug < 0` is an error (over-count), never a silent fix. Corrections are always in data or YAML, never in `core.py`.

7. **NOL carryforward (TCJA)** — `_nol_carryforward` persists across forecast years. Each year: `nol_used = min(nol_open, ebt × 0.80)`. Opening balance from YAML `taxes.nol_opening_balance`. US Steel: $1,014M as of end-2024.

8. **ASC 842 lease BS identity** — Operating lease ROU and lease liability move in lockstep (ΔROU = ΔLL enforced). Lease payment flows to CFF; lease expense is embedded in SG&A.

9. **Callable instruments and floating rate** — `debt_instruments.callable_flag` marks bonds subject to covenant acceleration. `rate_type = floating` instruments receive `general_rate_delta_pct` stress shocks; fixed-rate instruments do not.

10. **Covenant breach auto-trigger** — when any `acceleration_triggers` covenant is breached, the orchestrator automatically re-runs `covenant_breach` scenario from `stress_scenarios.yaml`. Result stored in `ModelResult.stress_results["covenant_breach"]`.

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Database | SQLite 3 (WAL mode, data_mart_v2.db) |
| Macro models | statsmodels (VECM, ARIMA), scikit-learn (Elastic Net) |
| Debt optimizer | scipy (linprog / LP) |
| Tests | pytest, hypothesis |
| Notebooks | Jupyter |

---

## Running the Model

```python
from engine.orchestrator import Orchestrator

orch = Orchestrator(company_id="us_steel", config_path="companies/us_steel/configs/project.yaml")
result = orch.run()
```

Or via CLI:
```bash
# From refactoring_v2/ directory:
PYTHONPATH=. python -m engine.orchestrator --company us_steel
PYTHONPATH=. pytest tests/ -v
```

---

## Historical Data Coverage

| Statement | Years Available |
|-----------|---------------|
| Income Statement | 2010–2024 |
| Balance Sheet | 2010–2024 |
| Cash Flow | 2010–2024 |
| Debt Schedule | 2010–2024 |
| Lease Schedule | 2019–2024 (post-ASC 842) |
