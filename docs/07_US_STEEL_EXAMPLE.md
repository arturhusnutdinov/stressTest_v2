# US Steel — Working Example

## Company Profile

| Field | Value |
|-------|-------|
| Company ID | `us_steel` |
| Full Name | United States Steel Corporation |
| Industry | Integrated steel producer |
| Currency | USD |
| DB Unit | tUSD (thousands of USD) |
| Accounting Standard | US GAAP |
| History Coverage | 2010–2024 |
| Forecast Horizon | 2025–2029 |
| Config | `companies/us_steel/configs/project.yaml` |

---

## Key Financial Characteristics

| Metric | Typical Value (2022–2024) |
|--------|--------------------------|
| Revenue | ~$17–21B |
| EBITDA Margin | 10–20% (highly cyclical) |
| CapEx / Revenue | 5–8% |
| Net Debt / EBITDA | 0.5–2.0× |
| Avg Interest Rate | 5–6% |
| Operating Lease ROU | ~$500M |
| Min Cash (auto) | ~$596M (15-day opex floor) |

---

## Macro Factors Used

| Factor | File | Description |
|--------|------|-------------|
| `steel_price_hrc` | `steel_price_hrc_usd.csv` | Hot-rolled coil price (USD/ton) |
| `iron_ore_price` | `iron_ore_price_usd.csv` | Iron ore fines (USD/ton) |
| `gdp_us` | `gdp_us.csv` | US real GDP growth |
| `gdp_world` | `world_gdp.csv` | World real GDP growth |
| `industrial_production_us` | `industrial_production_us.csv` | US IP index |
| `ppi_us` | `ppi_us.csv` | US Producer Price Index |
| `cpi_us` | `cpi_us.csv` | US Consumer Price Index |
| `dxy` | `dxy.csv` | US Dollar Index |

Revenue is the primary macro-driven variable: VECM cointegration between revenue and `steel_price_hrc`.

---

## Running the Full Pipeline

```bash
# From refactoring_v2/ directory:

# 1. Load / refresh history (if needed)
PYTHONPATH=. python companies/us_steel/loaders_legacy/load_master_balance_sheet_2024.py
PYTHONPATH=. python companies/us_steel/loaders_legacy/load_master_income_statement_2011_2013.py
# ... (run all relevant loaders)

# 2. Run preprocessor
PYTHONPATH=. python -m engine.preprocessor.core --company us_steel

# 3. Run macro forecast
PYTHONPATH=. python -m engine.macro.runner --company us_steel

# 4. Run three-statement model
PYTHONPATH=. python -m engine.orchestrator --company us_steel

# 5. Run stress + rating
PYTHONPATH=. python -m engine.stress_rating.core --company us_steel

# 6. Run tests
PYTHONPATH=. pytest tests/ -v
```

---

## Preprocessor Output (US Steel)

Sample `preprocess_metrics` values for US Steel (approximates):

| group | metric_name | year | value |
|-------|-------------|------|-------|
| revenue | growth_rate_recommended | -1 | 0.032 |
| cogs | cogs_ratio_recommended | -1 | 0.812 |
| sga | sga_ratio_recommended | -1 | 0.044 |
| capex | capex_to_rev_recommended | -1 | 0.063 |
| wc | dso_recommended | -1 | 28.5 |
| wc | dih_recommended | -1 | 42.1 |
| wc | dpo_recommended | -1 | 38.6 |
| debt | avg_interest_rate_recommended | -1 | 0.057 |
| debt | min_cash_recommended | -1 | 596000.0 |
| tax | effective_tax_rate_recommended | -1 | 0.183 |
| lease | lease_dep_rate_recommended | -1 | 0.142 |

---

## Debt Structure (2024 baseline)

US Steel maintains a mixed debt portfolio (38 instruments in `debt_instruments`):

| Instrument Type | Example | db_type | callable_flag | rate_type |
|----------------|---------|---------|---------------|-----------|
| Senior Notes | 6.875% due 2029 | `bond_fixed` | 1 | fixed |
| Term Loan | SOFR + 250bps | `term_bullet` | 0 | floating |
| Revolving Credit | $1.5B facility | `revolving` | 0 | floating |
| Environmental Revenue Bonds | 3.5%, state-issued | `bond_fixed` | 0 | floating |
| Finance Leases | Blast furnace equipment | `finance_lease` | 0 | fixed |

`callable_flag = 1` → covenant acceleration: breach of ICR/leverage → instrument reclassified to ST.
`rate_type = floating` → receives `general_rate_delta_pct` stress shock; fixed instruments do not.

In `schedule_based` mode, the model reads actual corkscrews from `debt_schedule` table.
In `parametric` mode, target leverage = 26.7% of revenue; RC draws/repays automatically.

**Additional CapEx schedule (BigRiver integration):**
```yaml
ppe:
  additional_capex:     # Project CapEx on top of modeled ratio (millions)
    2025: 0
    2026: 200           # $200M BigRiver expansion (additive)
```

---

## Solver Convergence (Observed)

With the joint iterative solver:

| Mode | Iterations to Convergence |
|------|--------------------------|
| `schedule_based` | 2 (always) |
| `parametric` (with RC) | 2–3 |
| `optimizer` (LP) | 2–3 |

Cash delta at convergence: < $100 (well within $1K tolerance).

---

## BS Identity Verification

At every modeled year: `total_assets == total_liabilities + total_equity`.

Expected result for US Steel: **max diff = 0.0** across all forecast years.

If non-zero diff is found, check:
1. Equity corkscrew (RE roll-forward)
2. DTA/DTL movements vs deferred tax in IS/CF
3. Lease liability corkscrew vs ROU asset

---

## Forecast Model Features Active (2025 run)

| Feature | Setting | Effect |
|---------|---------|--------|
| **CapEx floor** | `min_capex_da_ratio: 0.90` | Maintenance floor = 90% of DA (~$420M floor) |
| **Dynamic WC days** | Auto (no config) | DSO/DIO extend +10–20% when revenue declines |
| **Additional CapEx** | `additional_capex: {2026: 200}` | $200M BigRiver project additive in 2026 |
| **Capital allocation** | `dividend_payout_ratio: 0.03`, `buyback_pct_fcf: 0.15` | Dividends + leverage-gated buybacks |
| **equity_additional_events** | None (base case) | Special buybacks/issuances via `equity.additional_events` |
| **TaxBlock DTL** | `accel_dep_excess_pct: 0.40` | DTL grows ~$74M/yr from accelerated depreciation |
| **NOL carryforward** | `nol_opening_balance: 1014.0` | ~$214M annual shield, depletes 2027 |

## Covenant Profile (Typical)

| Covenant | Threshold | Typical Headroom |
|----------|-----------|-----------------|
| Net Debt / EBITDA | ≤ 3.5× (steel) | 100–200% in good years, tight in downturns |
| Interest Coverage | ≥ 2.5× (steel) | 3–8× in normal conditions |
| Current Ratio | ≥ 1.0 | ~1.2–1.5 |

**Covenant breach auto-trigger:** If any `acceleration_triggers` covenant breaches, the orchestrator automatically re-runs the `covenant_breach` scenario (steel_price −15%, avg_rate +200bps, DSO/DIO +10%). The rating steel methodology (`methodology: steel`) adds EBITDA margin and FCF/debt covenants above the default set.

The stress scenario `bear_steel_crash` (steel price −20%, GDP −2%) is the primary risk scenario for covenant breach testing. Callable instruments (`callable_flag = 1`) and floating rate bonds receive additional sensitivity to this scenario.

---

## NOL Tax Shield

US Steel generated large NOL pools during the 2015–2020 losses period. TCJA (2017) made these indefinite.

| Item | Value |
|------|-------|
| NOL opening balance (end-2024) | $1,014M |
| TCJA annual utilization cap | 80% of taxable income |
| Effective shield (2025 base) | ~$214M (80% × $267M EBT × 21%) |
| Effective tax rate impact | −4.2pp vs statutory 21% |

NOL is set in `project.yaml`: `taxes.nol_opening_balance: 1014.0`. Pool depletes by 2027 in base case.

---

## Credit Rating (Base Case Estimate)

Using S&P methodology (`industry_adjustment: −8.0`, `size_adjustment: +3.0`, `cycle_avg: 10%`):

| Scenario | Estimated Grade | Key Driver |
|----------|----------------|------------|
| Bull | A− / BBB+ | High EBITDA margin, low leverage |
| **Base** | **BBB+** | Moderate leverage (ND/EBITDA ~1.5×), strong coverage |
| Bear | BB+ | Compressed margins, higher leverage |
| Stress | BB / BB− | Possible covenant approach on ICR |

**Model calibration (2025):** Rating BBB+, score ~71, ND/EBITDA 1.5×, ICR 8.2×.
US Steel's actual rating (as of 2024): BB+ (S&P) — model rates slightly higher due to positive macro outlook embedded in 2025 forecast.

---

## Testing

```bash
# Run full test suite
PYTHONPATH=. pytest tests/ -v

# Run specific integration test
PYTHONPATH=. pytest tests/integration/ -v

# Quick smoke test
PYTHONPATH=. python -c "
from engine.model.loader import ModelLoader
from engine.model.core import ThreeStatementModel
loader = ModelLoader('us_steel', 'companies/us_steel/configs/project.yaml', 'data_mart_v2.db')
mc = loader.load_config()
print('Config loaded OK:', mc.forecast_start_year, '-', mc.forecast_end_year)
"
```

---

## Known Data Notes

- **2010–2013**: Some CF metrics missing in legacy Excel; plugged via CF identity
- **2014–2015**: US Steel had negative net income; model handles NOL carryforward
- **2019**: ASC 842 lease adoption — operating leases first appear on BS; loader handles step-up
- **2020**: COVID impact — stress year; used as 2020-specific dummy in VECM
- **2023–2024**: BigRiver Steel integration impact on BS consolidation


---

## See Also

- [09_RUSAL_MODEL_GUIDE.md](09_RUSAL_MODEL_GUIDE.md) — Rusal (IFRS, aluminium, PDF parser)
