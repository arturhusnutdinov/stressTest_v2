"""
Named constants for the stressTest v2 engine.

All "magic numbers" that were previously hardcoded in core.py,
loader.py, and blocks are centralized here with documentation.
"""

# ── Engine version ───────────────────────────────────────────────────
MODEL_VERSION = "v2.3"               # written to model_versions table on save

# ── Revenue fallback ─────────────────────────────────────────────────
REVENUE_FALLBACK_GROWTH = 1.02       # 2% nominal growth when no forecast method works

# ── SGA / Payroll ────────────────────────────────────────────────────
PAYROLL_PCT_OF_SGA = 0.10            # Payroll payable ≈ 10% of SGA
SGA_PCT_DEFAULT = 0.05               # SGA / Revenue fallback
SGA_PCT_MAX = 0.30                   # Max SGA ratio
SGA_PCT_MIN = 0.01                   # Min SGA ratio
SGA_CPI_UPLIFT_MAX = 0.03            # Max CPI uplift on SGA
SGA_HIST_CLAMP_LOW = 0.80            # Historical SGA lower bound multiplier
SGA_HIST_CLAMP_HIGH = 1.20           # Historical SGA upper bound multiplier

# ── EWA / Decay defaults ─────────────────────────────────────────────
EWA_HALFLIFE_YEARS = 3.0             # Default EWA half-life
EWA_DECAY_FALLBACK = 0.97            # When no history, decay at 3%/yr
OTHER_IS_DECAY = 0.95                # Decay for other IS items without data

# ── Lease defaults ───────────────────────────────────────────────────
LEASE_OP_DECAY_RATE_DEFAULT = 0.33   # Operating lease ROU amortisation rate
LEASE_FIN_PRINCIPAL_RATE = 0.25      # Finance lease principal repayment rate
LEASE_FIN_AMORT_RATE = 0.28          # Finance lease ROU depreciation rate
LEASE_FIN_INTEREST_RATE = 0.06       # Finance lease interest rate
LEASE_FIN_DEP_RATE_DEFAULT = 0.15    # Finance lease depreciation rate
LEASE_DEFAULT_DISCOUNT_RATE = 0.05   # Default lease discount rate

# ── Debt defaults ────────────────────────────────────────────────────
DEBT_AVG_RATE_DEFAULT = 0.05         # 5% when no historical rate available
DEBT_ST_RATIO_MIN = 0.05             # Min ST/Total debt ratio
DEBT_ST_RATIO_MAX = 0.40             # Max ST/Total debt ratio
DEBT_ST_RATIO_DEFAULT = 0.15         # Default ST/Total ratio
DEBT_TARGET_PCT_REVENUE = 0.35       # Target debt / revenue
DEBT_MAX_ANNUAL_CHANGE = 0.20        # Max ±20% debt change per year
DEBT_MANDATORY_ST_MULTIPLIER = 0.5   # Mandatory amort = ST ratio × multiplier
DEBT_MIN_RATE = 0.001                # Minimum interest rate (clamp)
REFI_FEES_BPS_DIVISOR = 10_000       # Basis points → decimal

# ── Tax defaults ─────────────────────────────────────────────────────
TAX_STATUTORY_RATE_DEFAULT = 0.21    # US federal corporate rate
TAX_EFFECTIVE_RATE_MIN = 0.05
TAX_EFFECTIVE_RATE_MAX = 0.45
NOL_MAX_UTILIZATION_PCT = 0.80       # TCJA: 80% of taxable income

# ── WC defaults ──────────────────────────────────────────────────────
WC_DSO_DEFAULT = 45.0                # Days Sales Outstanding
WC_DIH_DEFAULT = 60.0                # Days Inventory Held
WC_DPO_DEFAULT = 50.0                # Days Payable Outstanding
WC_NWC_RATIO_DEFAULT = 0.08          # Net Working Capital / Revenue
WC_NWC_RATIO_MIN = 0.02
WC_NWC_RATIO_MAX = 0.25
WC_OTHER_CA_PCT_REV = 0.07           # calibrated: Rusal avg 2021-2025 = 6.5-9.3%, median ~7%
WC_ACCRUED_PCT_SGA = 0.10            # Accrued liabilities as % SGA (Rusal median 2021-2025)
WC_OTHER_CL_PCT_REV = 0.04           # calibrated: Rusal avg 2021-2025 = 0.9-7.4%, median ~4%
WC_CYCLICAL_ADJ_MIN = 0.80           # Min cyclical adjustment factor
WC_CYCLICAL_ADJ_MAX = 1.20           # Max cyclical adjustment factor
WC_DSO_CYCLICAL_ELASTICITY = 0.87    # calibrated: OLS Δ(DSO)/DSO ~ β×Δ(Rev)/Rev, β=-0.87 (n=14)
WC_DIH_CYCLICAL_ELASTICITY = 0.36   # calibrated: β=+0.36 (n=14); revenue↑ → inventory days↑
WC_DPO_CYCLICAL_ELASTICITY = 0.64   # calibrated: β=-0.64 (n=12); revenue↑ → pay suppliers faster

# ── Margin defaults ──────────────────────────────────────────────────
COGS_PCT_DEFAULT = 0.85              # COGS / Revenue fallback
COGS_PCT_MIN = 0.40                  # Min COGS ratio (ex-DA)
COGS_PCT_MAX = 1.05                  # Max COGS ratio
COGS_CLAMP_MIN_FACTOR = 0.5          # COGS floor relative to base_cogs
COGS_CLAMP_MAX_FACTOR = 1.5          # COGS ceiling relative to base_cogs

# ── CapEx defaults ───────────────────────────────────────────────────
CAPEX_PCT_DEFAULT = 0.05             # CapEx / Revenue fallback
MIN_CAPEX_DA_RATIO = 0.90            # Maintenance capex ≥ 90% of D&A
CAPEX_INTEREST_DECAY_RATE = 0.15     # Capitalized interest decay per year

# ── Solver defaults ──────────────────────────────────────────────────
SOLVER_MAX_ITER = 10                 # Max joint solver iterations
SOLVER_TOL = 1000.0                  # Convergence tolerance ($1K)
SOLVER_EPSILON = 1e-9                # Float comparison epsilon
BS_TOLERANCE = 1.0                   # BS identity check tolerance ($1)
CF_TOLERANCE = 1.0                   # CF bridge check tolerance ($1)
BS_DIFF_LOG_THRESHOLD = 100.0        # Log warning if BS diff exceeds this

# ── Cash / Interest ──────────────────────────────────────────────────
CASH_RATE_DEFAULT = 0.02             # Interest earned on cash (2%)
CASH_RATE_MAX = 0.10                 # Max cash interest rate
MIN_CASH_REVENUE_PCT = 0.02          # Min cash as % of revenue
MIN_CASH_DAYS_OPEX = 15              # Min cash as days of opex

# ── Interest payable ─────────────────────────────────────────────────
INTEREST_PAYABLE_TIMING_DEFAULT = "next_year"  # "current_year" | "next_year"

# ── Dividend / Buyback ───────────────────────────────────────────────
DIVIDEND_PAYOUT_DEFAULT = 0.0        # No dividends by default
BUYBACK_PCT_FCF_DEFAULT = 0.0        # No buybacks by default
BUYBACK_LEVERAGE_MAX = 2.0           # ND/EBITDA threshold for buybacks

# ── Depreciation ─────────────────────────────────────────────────────
ACCEL_DEP_EXCESS_PCT_DEFAULT = 0.0   # Tax depreciation exceeding book

# ── Intangibles ──────────────────────────────────────────────────────
INTANG_AMORT_RATE_FALLBACK = 0.10    # 10% amortisation when no data

# ── Revenue percentile clamp ────────────────────────────────────────
REVENUE_CLAMP_PERCENTILE_LOW = 0.05  # 5th percentile
REVENUE_CLAMP_PERCENTILE_HIGH = 0.95 # 95th percentile

# ── Rating ───────────────────────────────────────────────────────────
RATING_CYCLE_AVG_MARGIN_DEFAULT = 0.10  # Through-the-cycle EBITDA margin
RATING_MARGIN_NORM_CAP = 1.5            # Cap margin at cycle_avg × this factor
RATING_INDUSTRY_ADJ_DEFAULT = -12.0     # Cyclicality discount (metals/mining)
RATING_SIZE_ADJ_DEFAULT = 2.0           # Large integrated producer bonus
RATING_SOVEREIGN_DEFAULT = "BBB+"       # Sovereign rating for national scale mapping
RATING_DEFAULT_SCORE = 50.0             # Default score when no data available
RATING_FCF_WEIGHT_DISCOUNT = 0.8        # FCF-to-debt weight relative to BS metrics

# ── Stress sector packs ─────────────────────────────────────────────
STRESS_METALS_HRC_SHOCK = -25.0         # Steel/metals HRC shock %
STRESS_METALS_PPI_SHOCK = -15.0         # Metals PPI shock %
STRESS_METALS_BRENT_SHOCK = -20.0       # Brent shock %
STRESS_METALS_CAPEX_SHOCK = -30.0       # CapEx reduction %
STRESS_RECESSION_GDP_SHOCK = -3.0       # GDP shock %
STRESS_RECESSION_CPI_SHOCK = -1.0       # CPI shock %
STRESS_RECESSION_BRENT_SHOCK = -30.0    # Brent shock %
STRESS_LIQUIDITY_DSO_SHOCK = 30.0       # DSO increase %
STRESS_LIQUIDITY_DIH_SHOCK = 20.0       # DIH increase %
STRESS_LIQUIDITY_DPO_SHOCK = -15.0      # DPO decrease %
STRESS_LIQUIDITY_RATE_SHOCK = 2.0       # Rate spike pp

# ── Macro / VECM defaults ─────────────────────────────────────────
VECM_MIN_COMMON_YEARS = 8              # Min overlapping years for VECM estimation
VECM_COMMODITY_KAPPA_BASE = 0.12       # OU MLE on LME Al 1990-2029: phi=0.88, HL=5.6yr
VECM_COMMODITY_KAPPA_BEAR = 0.50       # Fast mean reversion for bear/stress scenarios
MACRO_FALLBACK_KAPPA_BASE = 0.15       # Slow normalization for base scenario gap-fill
MACRO_FALLBACK_HALFLIFE = 5.0          # EWA halflife for macro/EWA fallback (years)
MACRO_COMMODITY_HALFLIFE = 8.0         # EWA halflife for commodity RW-drift (years)
VECM_FC_MAX_GROWTH = 1.5              # Max growth ceiling factor per forecast step
VECM_FC_MIN_DECLINE = 0.3             # Min decline floor factor per forecast step
VECM_SANITY_MIN_RATIO = 0.01          # Min forecast/last_hist ratio (generic)
VECM_SANITY_MAX_RATIO = 100.0         # Max forecast/last_hist ratio (generic)
MACRO_GAPFILL_SANITY_MIN = 0.1        # Min ratio for gap-fill sanity check
MACRO_GAPFILL_SANITY_MAX = 10.0       # Max ratio for gap-fill sanity check
UNIVARIATE_FC_MIN_RATIO = 0.05        # Univariate forecast min/last bound
UNIVARIATE_FC_MAX_RATIO = 20.0        # Univariate forecast max/last bound
UNIVARIATE_EWA_ALPHA = 0.3            # EWA alpha for pure-Python fallback
UNIVARIATE_DRIFT_MAX = 0.15           # Max abs drift in EWA fallback
PRICE_INDEX_MIN_INFLATION = 0.005     # Min 0.5% inflation for price indices
VECM_TREND_THRESHOLD = 0.03           # Strong aggregate trend threshold
VECM_SLOPE_CONSISTENCY = 0.02         # Per-factor slope consistency threshold

# ── COGS clamp ─────────────────────────────────────────────────────
COGS_P10_BUFFER = 0.95                # P10 boundary multiplier
COGS_P90_BUFFER = 1.05                # P90 boundary multiplier
COGS_MIN_HIST_BUFFER = 0.90           # Min historical boundary multiplier
COGS_MAX_HIST_BUFFER = 1.10           # Max historical boundary multiplier

# ── WC composition (standard mode) ────────────────────────────────
WC_AR_PCT_OF_NWC = 0.45              # AR share in NWC
WC_INV_PCT_OF_NWC = 0.40             # Inventory share in NWC
WC_OTHER_CA_PCT_OF_NWC = 0.15        # Other CA share in NWC
WC_AP_PCT_OF_NWC = 0.35              # AP share in NWC
WC_OTHER_CL_PCT_OF_NWC = 0.10        # Other CL share in NWC

# ── Commodity / Macro keyword sets ─────────────────────────────────
COMMODITY_KEYWORDS = frozenset([
    "steel", "brent", "coal", "iron", "aluminum",
    "copper", "gas", "hrc", "ppi_iron", "lme",
])
MACRO_KEYWORDS = frozenset([
    "gdp", "cpi", "ppi", "production", "pmi", "dxy",
])
BEAR_SCENARIO_KEYWORDS = frozenset(["bear", "stress", "severe", "down"])
BULL_SCENARIO_KEYWORDS = frozenset(["bull", "up", "optimistic"])
SKIP_FALLBACK_FACTORS = frozenset(["gdp_world", "gdp_us", "gdp_china"])
