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
├── engine/                      # Core engine modules
│   ├── orchestrator.py          # Top-level pipeline (406 lines)
│   ├── constants.py             # Named constants (81 lines)
│   ├── model/                   # Three-statement model
│   │   ├── core.py              # ThreeStatementModel (1,696 lines, iterative solver)
│   │   ├── loader.py            # DB + YAML → ModelConfig (824 lines)
│   │   ├── inputs.py            # YearState, ModelConfig dataclasses (515 lines)
│   │   ├── saver.py             # Results → DB (299 lines)
│   │   ├── cogs_block.py        # Component-based COGS (Rusal)
│   │   ├── segment_revenue.py   # Segment Volume × Price revenue
│   │   ├── revenue_models.py    # ElasticNet / EWA revenue
│   │   ├── forecast_dispatcher.py # Method dispatch per metric
│   │   ├── blocks/              # 6 extracted blocks (revenue, sga, cash, bs_totals, ...)
│   │   └── schedules/           # debt, ppe, tax, lease, equity, wc, intangibles
│   ├── macro/                   # VECM / ARIMA / EWA macro (vecm.py 1,666 lines)
│   ├── preprocessor/            # Historical KPI extraction (1,094 lines)
│   ├── database/                # SQLite schema + repository (1,309 lines)
│   ├── loader/                  # ExcelLoader (764 lines)
│   ├── stress/                  # Stress runner (core 282 + runner 427 lines)
│   ├── rating/                  # Credit rating (core 458 + runner 190 lines)
│   └── covenants/               # Covenant monitoring (410 lines)
├── parsers/
│   ├── pdf_parser.py            # Rusal PDF extraction (~1,000 lines)
│   └── adapters/rusal.yaml      # YAML adapter (~600 lines)
├── companies/
│   ├── us_steel/configs/        # project.yaml, stress_scenarios.yaml, macro_ecm.yaml
│   └── rusal/configs/           # project.yaml, stress_scenarios.yaml, macro_ecm.yaml
├── tests/                       # 45 tests (unit + integration)
├── tools/                       # Diagnostic, migration, audit tools
├── docs/                        # Documentation (this folder)
├── pyproject.toml               # Package config, CLI entry point
├── Dockerfile                   # Docker image (python:3.12-slim)
├── .github/workflows/ci.yml     # CI/CD (Python 3.11/3.12, pytest + ruff)
└── data_mart_v2.db              # SQLite database (WAL mode)
```

---

## Engine Architecture

The engine follows a **layered pipeline**:

```
History (Excel / DB)
        │
        ▼
  Preprocessor (1,094 lines) ← computes ratios, betas, EWA, min_cash
        │
        ▼
  Macro Module (VECM 1,666)  ← VECM / ARIMA / EWA forecast of macro factors
        │
        ▼
  Model Loader (824 lines)   ← reads YAML config, assembles ModelConfig + HistoricState
        │
        ▼
  ThreeStatementModel (1,696) ← iterative solver, 6 blocks + 7 schedules
        │
        ├── Stress Runner (427)   ← 8 scenarios (macro + driver shocks)
        ├── Rating Engine (458)   ← S&P scorecard (4 sub-scores)
        └── Covenant Checker (410) ← breach / warning / ok
        │
        ▼
  ModelSaver / Repository    ← writes forecast_is/bs/cf to DB
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
