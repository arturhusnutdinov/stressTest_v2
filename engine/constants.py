"""
Named constants for the stressTest v2 engine.

All "magic numbers" that were previously hardcoded in core.py,
loader.py, and blocks are centralized here with documentation.
"""

# ── Revenue fallback ─────────────────────────────────────────────────
REVENUE_FALLBACK_GROWTH = 1.02       # 2% nominal growth when no forecast method works

# ── SGA / Payroll ────────────────────────────────────────────────────
PAYROLL_PCT_OF_SGA = 0.10            # Payroll payable ≈ 10% of SGA

# ── EWA / Decay defaults ─────────────────────────────────────────────
EWA_HALFLIFE_YEARS = 3.0             # Default EWA half-life
EWA_DECAY_FALLBACK = 0.97            # When no history, decay at 3%/yr
OTHER_IS_DECAY = 0.95                # Decay for other IS items without data

# ── Lease defaults ───────────────────────────────────────────────────
LEASE_OP_DECAY_RATE_DEFAULT = 0.33   # Operating lease ROU amortisation rate
LEASE_FIN_PRINCIPAL_RATE = 0.25      # Finance lease principal repayment rate
LEASE_FIN_AMORT_RATE = 0.28          # Finance lease ROU depreciation rate
LEASE_FIN_INTEREST_RATE = 0.06       # Finance lease interest rate
LEASE_DEFAULT_DISCOUNT_RATE = 0.05   # Default lease discount rate

# ── Debt defaults ────────────────────────────────────────────────────
DEBT_AVG_RATE_DEFAULT = 0.05         # 5% when no historical rate available
DEBT_ST_RATIO_MIN = 0.05             # Min ST/Total debt ratio
DEBT_ST_RATIO_MAX = 0.40             # Max ST/Total debt ratio
DEBT_ST_RATIO_DEFAULT = 0.15         # Default ST/Total ratio
DEBT_TARGET_PCT_REVENUE = 0.35       # Target debt / revenue
DEBT_MAX_ANNUAL_CHANGE = 0.20        # Max ±20% debt change per year

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

# ── Margin defaults ──────────────────────────────────────────────────
COGS_PCT_DEFAULT = 0.85              # COGS / Revenue fallback
SGA_PCT_DEFAULT = 0.05               # SGA / Revenue fallback
SGA_PCT_MAX = 0.30                   # Max SGA ratio
SGA_PCT_MIN = 0.01                   # Min SGA ratio
COGS_PCT_MIN = 0.40                  # Min COGS ratio (ex-DA)
COGS_PCT_MAX = 1.05                  # Max COGS ratio

# ── CapEx defaults ───────────────────────────────────────────────────
CAPEX_PCT_DEFAULT = 0.05             # CapEx / Revenue fallback
MIN_CAPEX_DA_RATIO = 0.90            # Maintenance capex ≥ 90% of D&A

# ── Solver defaults ──────────────────────────────────────────────────
SOLVER_MAX_ITER = 10                 # Max joint solver iterations
SOLVER_TOL = 1000.0                  # Convergence tolerance ($1K)
BS_TOLERANCE = 1.0                   # BS identity check tolerance ($1)
CF_TOLERANCE = 1.0                   # CF bridge check tolerance ($1)

# ── Cash / Interest ──────────────────────────────────────────────────
CASH_RATE_DEFAULT = 0.02             # Interest earned on cash (2%)
CASH_RATE_MAX = 0.10                 # Max cash interest rate
MIN_CASH_REVENUE_PCT = 0.02          # Min cash as % of revenue
MIN_CASH_DAYS_OPEX = 15              # Min cash as days of opex

# ── Dividend / Buyback ───────────────────────────────────────────────
DIVIDEND_PAYOUT_DEFAULT = 0.0        # No dividends by default
BUYBACK_PCT_FCF_DEFAULT = 0.0        # No buybacks by default
BUYBACK_LEVERAGE_MAX = 2.0           # ND/EBITDA threshold for buybacks

# ── Depreciation ─────────────────────────────────────────────────────
ACCEL_DEP_EXCESS_PCT_DEFAULT = 0.0   # Tax depreciation exceeding book

# ── Intangibles ──────────────────────────────────────────────────────
INTANG_AMORT_RATE_FALLBACK = 0.10    # 10% amortisation when no data
