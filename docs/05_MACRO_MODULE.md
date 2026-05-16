# Macro Module

## Overview

`engine/macro/` — forecasts macro-economic factors (GDP, steel price, PPI, etc.) that drive revenue and COGS in the financial model.

```
engine/macro/
├── runner.py           # Main entry: run_macro_forecast()
├── vecm_bridge.py      # VECM pipeline: fit, forecast, chain-link
├── vecm_engine.py      # Raw VECM estimation (statsmodels wrapper)
├── vecm.py             # VECM data prep and cointegration tests
├── cointegration_test.py  # Engle-Granger / Johansen tests
├── svar.py             # Structural VAR (optional)
├── commodity_models.py # Univariate models: EWA, ARIMA, random walk, select_best
├── db_adapter.py       # Reads macro_factors from DB
├── io.py               # Reads CSV factor files, writes macro_forecasts table
└── preprocess.py       # Log-diff transforms, outlier detection
```

---

## Pipeline

```
CSV factor files
      │
      ▼
  io.py (read_factor_csv)      → raw history {year: value}
      │
      ▼
  preprocess.py (transforms)   → dln (log-diff) or level
      │
      ▼
  vecm_bridge.py (fit_vecm)    → cointegration rank, VECM params
      │
      ▼
  vecm_bridge.py (forecast)    → {factor: {year: value}}
      │
      ▼
  runner.py (gap-fill)         → _fill_missing_with_fallback() for uncovered factors
      │
      ▼
  macro_forecasts table        → written via io.py save_forecasts()
```

---

## `runner.py` — `run_macro_forecast()`

Main entry point:

```python
from engine.macro.runner import run_macro_forecast

forecasts = run_macro_forecast(
    company_id="us_steel",
    config_path="companies/us_steel/configs/project.yaml",
    db_path="data_mart_v2.db",
    forecast_years=[2025, 2026, 2027, 2028, 2029]
)
# Returns: {factor_name: {year: value}}
```

### Commodity Keyword Detection

Factors are classified as "commodity" vs "macro" using `_COMMODITY_KW`:

```python
_COMMODITY_KW = [
    "steel", "iron", "coal", "aluminum", "copper", "nickel",
    "zinc", "hrc", "crc", "scrap", "ore", "brent", "wti",
    "gas", "lng", "lme"
]
```

Commodity factors use commodity-specific models (EWA + mean reversion). Macro factors use VECM.

### Gap-Fill Fallback

After the VECM loop, any factors not covered by VECM are gap-filled:

```python
missing = all_factors - set(forecasts.keys())
_fill_missing_with_fallback(missing, adapter, result, forecast_years)
```

`_fill_missing_with_fallback` uses EWA with halflife=3 years as the fallback forecast.

---

## VECM Module (`vecm_bridge.py`)

### Stream 1: Joint VECM on cointegrated factors

```python
from engine.macro.vecm_bridge import VecmBridge

bridge = VecmBridge(config=macro_config)
bridge.fit(history_data)
forecasts = bridge.forecast(horizon=5)
```

1. Loads factor histories aligned to common years
2. Tests for cointegration rank (Johansen trace test)
3. Fits VECM with `rank` cointegrating relations
4. Forecasts `horizon` steps ahead in log-diff space
5. Chain-links to last historical level

### Stream 2: ARIMA fallback

For non-cointegrated factors or insufficient history (< 10 years):
```python
from statsmodels.tsa.arima.model import ARIMA
```
Auto-selects (p,d,q) via AIC.

### Stream 3: EWA fallback

For factors with very short history (< 5 years):
```python
from engine.macro.commodity_models import select_best_forecast
fc = select_best_forecast(history, method="ewa", forecast_years=forecast_years, halflife=5.0)
```

Note: `vecm_bridge.py` uses `commodity_models.select_best_forecast`, not `runner._ewa_forecast` (which was removed to break the circular import).

---

## `commodity_models.py`

Univariate models for commodity price forecasting:

```python
from engine.macro.commodity_models import select_best_forecast

forecast = select_best_forecast(
    history={2015: 650, 2016: 680, ..., 2024: 750},
    method="ewa",           # ewa | mean_reversion | random_walk | arima | auto
    forecast_years=[2025, 2026, 2027, 2028, 2029],
    halflife=5.0
)
# Returns: {year: value}
```

**Methods:**
- `ewa` — Exponentially Weighted Average growth rate, projected forward
- `mean_reversion` — Ornstein-Uhlenbeck mean reversion to long-run level
- `random_walk` — drift-adjusted random walk (last value + mean growth)
- `arima` — ARIMA(p,d,q) auto-selected
- `auto` — selects best in-sample fit (RMSE on holdout)

**`_ewa_forecast_local`** (internal to `commodity_models.py`):
```python
def _ewa_forecast_local(history: dict, forecast_years: list, halflife: float = 5.0) -> dict:
    # Computes EWA growth rate from history
    # Projects: last_value × (1 + ewa_growth)^t
```

---

## Macro Anomaly Detection (`preprocess.py`)

Before fitting, the preprocessor flags structural breaks:

1. Compute z-score for each year: `(value - rolling_mean) / rolling_std`
2. Flag years with `|z| > threshold` (default 3.0) as anomalies
3. Suggest adding dummy variables for flagged years in VECM
4. Store in `macro_anomalies` table

---

## DB Adapter (`db_adapter.py`)

Reads historical macro data from DB instead of CSV files (alternative to `io.py`):

```python
from engine.macro.db_adapter import MacroDbAdapter

adapter = MacroDbAdapter(db_path="data_mart_v2.db")
history = adapter.get_factor_history(factor_name="steel_price_hrc", company_id="us_steel")
# Returns: {year: value}
```

Used in `_fill_missing_with_fallback` to avoid re-reading CSV files for gap-fill pass.

---

## Configuration in project.yaml

```yaml
macro_forecast:
  profile: vecm_default
  factors:
    - gdp_us
    - steel_price_hrc
    - ppi_us
    # ...
  policy:
    factors:                  # Subset used for revenue regression
      - steel_price_hrc
      - gdp_world
  transforms:
    revenue_target: dln       # Log-diff transform for target variable
    revenue_features: dln
```

---

## Adding a New Macro Factor

1. Add CSV file: `companies/us_steel/drivers/{factor_name}.csv`
   - Format: `year,value` (annual)
2. Register in `project.yaml`:
   ```yaml
   macro_forecast:
     factors:
       - {factor_name}
     file_map:
       {factor_name}: {factor_name}.csv
   ```
3. Run: `PYTHONPATH=. python -m engine.macro.runner --company us_steel`
4. Verify in DB: `SELECT * FROM macro_forecasts WHERE factor_name = '{factor_name}'`
