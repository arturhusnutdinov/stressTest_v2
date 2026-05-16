# Stress Testing, Credit Rating, and Covenants

## Overview

Three downstream modules consume the model's base-case forecast:

```
ThreeStatementModel (base forecast)
        │
        ├── Stress Runner      → stressed IS/BS/CF per scenario
        │       │
        │       └── Rating Engine   → credit grade per scenario
        │
        ├── Rating Engine      → base-case credit rating
        │
        └── Covenant Monitor   → headroom / breach per period
```

All three modules write to the DB (`stress_results`, `ratings`, `covenant_results` tables) and are orchestrated through `engine/orchestrator.py`.

---

## Stress Testing

### Module: `engine/stress/core.py`

```python
from engine.stress.core import StressEngine

stress = StressEngine(
    company_id="us_steel",
    base_forecast=year_states,   # List[YearState] from model
    db_path="data_mart_v2.db"
)
results = stress.run(scenario_name="bear_steel_crash")
```

### How Shocks Are Applied

A stress scenario applies multiplicative or additive shocks to forecast inputs, then re-runs the model:

1. Load shock definition from scenario config
2. Modify `HistoricState` or `Drivers` values (revenue growth, commodity prices, interest rates)
3. Re-run `ThreeStatementModel` with modified inputs
4. Compare stressed result vs base forecast
5. Write to `stress_results` table

### Scenario Types

| Type | Description |
|------|-------------|
| `base` | No shocks — reference case |
| `bull` | Revenue upside + margin expansion |
| `bear` | Revenue decline + margin compression |
| `stress` | Severe: revenue −20%, interest rates +200bps, margin −5pp |
| `custom` | User-defined parameter overrides |

### Shock Parameters (in project.yaml or scenario file)

```yaml
stress_scenarios:
  bear_steel_crash:
    type: bear
    shocks:
      revenue_growth_delta: -0.15    # Additive: reduce growth by 15pp
      steel_price_pct: -0.20         # Multiply steel price by 0.80
      avg_interest_rate_delta: 0.02  # Add 200bps to all rates
      cogs_ratio_delta: 0.03         # Increase COGS/rev ratio by 3pp
```

### Runner (`engine/stress/runner.py`)

Batch stress across multiple scenarios:

```python
from engine.stress.runner import StressRunner

runner = StressRunner(company_id="us_steel", db_path="data_mart_v2.db")
all_results = runner.run_all()   # Runs all defined scenarios
```

---

## Credit Rating Engine

### Module: `engine/rating/core.py`

Implements scorecard methodologies for S&P, Moody's, and Fitch. Each methodology maps financial ratios to scores and grades.

```python
from engine.rating.core import RatingEngine

engine = RatingEngine(methodology="sp")
rating = engine.rate(year_states=forecast, scenario_id=1)
# Returns: RatingResult(grade="BB+", score=6.2, details={...})
```

### Rating (Steel Methodology)

`methodology: steel` activates two additional covenants and uses steel-calibrated score thresholds (`rating steel` in `project.yaml`). NOL carryforward reduces effective tax rate → increases NI and equity → lowers leverage ratios → improves rating score. At $1,014M NOL opening (US Steel), the shield is ~$214M/yr, worth ~0.3–0.5 rating notches.

**Floating rate stress effect on rating:** `avg_rate +200bps` shock in `covenant_breach` scenario raises interest expense on floating rate instruments (`rate_type = floating`) and RC draws → compresses ICR → lowers coverage sub-score by ~5–8 points. Callable flag instruments (`callable_flag = 1`) are reclassified to ST debt on breach.

**TaxBlock DTL / NOL effect on rating:** DTL growth reduces equity book value slightly but is a non-cash timing difference — rating agencies normalize for it. NOL carryforward shield lowers effective tax rate → raises NI → improves coverage and profitability sub-scores.

**Buyback / capital allocation effect:** buybacks reduce equity → increase leverage ratio → may lower leverage sub-score when ND/EBITDA approaches `buyback_leverage_max`.

### S&P Methodology (default)

Four factor groups with configurable weights (YAML `rating.weights`):

| Factor | Default Weight | Key Metrics |
|--------|---------------|-------------|
| `leverage` | 35% | ND/EBITDA, debt/equity |
| `coverage` | 30% | EBITDA/interest (primary), EBIT/interest |
| `profitability` | 20% | TTC-normalized EBITDA margin |
| `liquidity` | 15% | current ratio, FCF/debt |

### Industry Adjustments

Raw sub-scores are combined into a `base_score`, then adjusted for industry and company-size:

```
total_score = base_score + industry_adjustment + size_adjustment
```

| Adjustment | Purpose | Typical Value |
|-----------|---------|---------------|
| `industry_adjustment` | Cyclicality, commodity exposure, earnings volatility | −5 to −10 for steel/metals |
| `size_adjustment` | Scale, market position, diversification | +2 to +5 for large companies |

### Through-the-Cycle Normalization

The profitability sub-score uses normalized EBITDA margin to avoid rating inflation in boom years:

```
normalized_margin = min(actual_margin, cycle_avg_ebitda_margin × 1.5)
```

Set `cycle_avg_ebitda_margin` in YAML to the historical average through a full cycle.
For US Steel: `cycle_avg = 0.10` (2018–2024 avg). In boom years (margin=20%), normalized = 15%, preventing overscoring.

### Grade Scale

| Score | Grade | Category |
|-------|-------|----------|
| ≥ 95 | AAA | Investment Grade |
| 85–94 | AA | Investment Grade |
| 75–84 | A | Investment Grade |
| 63–74 | BBB | Investment Grade |
| 52–62 | BB | Speculative Grade |
| 42–51 | B | Speculative Grade |
| 30–41 | CCC | Distressed |
| < 30 | D | Default |

### Runner (`engine/rating/runner.py`)

```python
from engine.rating.runner import RatingRunner

runner = RatingRunner(company_id="us_steel", db_path="data_mart_v2.db")
runner.run_all_scenarios()   # Rates base + all stress scenarios
```

Results written to `ratings` and `rating_metrics` tables.

---

## Covenant Monitoring

### Module: `engine/covenants/core.py`

Checks financial covenant thresholds across all forecast periods for a given scenario.

```python
from engine.covenants.core import CovenantMonitor

monitor = CovenantMonitor(company_id="us_steel", config_path="...", db_path="data_mart_v2.db")
results = monitor.check(year_states=forecast, scenario_id=1)
```

### Covenant Metrics Computed

| Covenant | Formula | Default Threshold |
|----------|---------|------------------|
| `net_debt_ebitda` | (LT debt + ST debt - cash) / EBITDA | ≤ 4.0 |
| `interest_coverage` | EBIT / interest_expense | ≥ 2.0 |
| `debt_to_equity` | total_debt / total_equity | ≤ 3.0 |
| `current_ratio` | total_CA / total_CL | ≥ 1.0 |
| `ebitda_margin` | EBITDA / revenue | ≥ 0.05 (steel methodology) |
| `fcf_to_debt` | FCF / total_debt | ≥ −0.10 (steel methodology) |

### Headroom Calculation

```
headroom_pct = (threshold - actual) / abs(threshold)   # for max covenants
headroom_pct = (actual - threshold) / abs(threshold)   # for min covenants
```

Warning triggered when `headroom_pct < warning_buffer` (default 10%).

### Output

```python
# CovenantResult per year per covenant:
{
    "period_id": 15,
    "covenant_name": "net_debt_ebitda",
    "value": 3.8,
    "threshold": 4.0,
    "headroom_pct": 0.05,   # 5% headroom → WARNING
    "breached": False
}
```

Written to `covenant_results` table.

---

## Covenant Auto-Trigger

When any covenant in `acceleration_triggers` is breached, the orchestrator automatically re-runs the model under the `covenant_breach` stress scenario (defined in `companies/{company}/configs/stress_scenarios.yaml`).

**How it works:**
```python
# In ModelOrchestrator.run():
cov_result = covenant_monitor.check(year_states=forecast)
breaches = cov_result.breaches()          # List of (year, covenant_name)

if breaches and "covenant_breach" in stress_scenarios:
    triggered_result = stress_engine.run("covenant_breach")
    model_result.stress_results["covenant_breach"] = triggered_result
    model_result.covenant_auto_triggered = True
```

**Covenant breach scenario shocks (US Steel default):**
| Shock | Value | Rationale |
|-------|-------|-----------|
| Steel price (HRC) | −15% | Demand collapse drives breach |
| PPI iron/steel | −10% | Correlated commodity decline |
| Interest rates | +200bps | Credit spread widening on breach |
| DSO days | +10% | Customers slow payments |
| DIH days | +10% | Inventory accumulates |

**`ModelResult` fields:**
- `stress_results["covenant_breach"]` — populated only when covenant breach auto-trigger fires
- `covenant_auto_triggered: bool` — flag indicating auto-trigger fired

The auto-trigger is **one-way**: if the stressed scenario itself would breach covenants, no further recursion occurs.

---

## Combined Stress-Rating Pipeline

`engine/stress_rating/` combines stress + rating into a single callable:

```python
from engine.stress_rating.core import StressRatingPipeline

pipeline = StressRatingPipeline(company_id="us_steel", db_path="data_mart_v2.db")
report = pipeline.run()
# Returns: dict with base + stressed ratings, covenant headrooms, breach flags
```

This is the primary output for the financial analysis report.

---

## Configuration Summary

All stress/rating/covenant settings in `project.yaml`:

```yaml
covenants:
  enabled: true
  methodology: steel          # steel adds EBITDA margin and FCF/debt covenants
  warning_buffer: 0.10
  acceleration_triggers:      # Covenant breach → callable debt reclassified to ST
    - interest_coverage
    - net_debt_ebitda
  thresholds:
    net_debt_ebitda_max:   3.5
    interest_coverage_min: 2.5
    debt_to_equity_max:    3.0
    current_ratio_min:     1.0
    ebitda_margin_min:     0.05

rating:
  methodology: sp
  industry_adjustment: -8.0         # Cyclical steel discount
  size_adjustment: 3.0              # Large integrated producer premium
  cycle_avg_ebitda_margin: 0.10     # TTC normalization baseline
  weights:
    leverage:      0.35
    coverage:      0.30
    profitability: 0.20
    liquidity:     0.15
```
