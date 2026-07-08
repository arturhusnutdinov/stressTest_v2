"""
Named constants for the stressTest v2 engine.

All "magic numbers" that were previously hardcoded in core.py,
loader.py, and blocks are centralized here with documentation.
"""

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
WC_ACCRUED_PCT_SGA = 0.10            # Accrued liabilities as % SGA (TODO: calibrate per company)
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
