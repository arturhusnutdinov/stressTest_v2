"""Tax corkscrew block — DTA/DTL/NOL/taxes_payable.

Sign conventions (match YearState):
  - dta, dtl, taxes_payable: positive magnitudes
  - tax_expense (IS): negative (expense)
  - cfo_deferred_tax: positive when DTL grows (non-cash add-back to NI)
  - tax_paid_cf: positive magnitude (supplemental disclosure, cash out)

DTL growth mechanics (US GAAP accelerated depreciation / MACRS):
  - Tax dep > book dep  →  taxable income < book income
  - Less cash paid to IRS now  →  DTL liability grows
  - CFO add-back = dtl_delta (positive; the deferred portion of tax expense
    is non-cash this year)
  - IS tax = current portion only (statutory × taxable_income, unchanged)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass
class TaxBlock:
    # ── Opening balances ──────────────────────────────────────────────────────
    taxes_payable_open: float = 0.0   # positive magnitude
    dta_open:           float = 0.0   # positive magnitude
    dtl_open:           float = 0.0   # positive magnitude
    nol_open:           float = 0.0   # positive

    # ── Income / rate ─────────────────────────────────────────────────────────
    ebt:                float = 0.0
    statutory_rate:     float = 0.21

    # ── NOL config ────────────────────────────────────────────────────────────
    nol_enabled:        bool  = False
    nol_limit_pct:      float = 0.80  # max % of opening NOL usable in one year

    # ── Temporary differences (all as positive magnitudes / deltas) ───────────
    # accel_dep_excess = dep_ppe × accel_dep_excess_pct  →  DTL grows
    accel_dep_excess:   float = 0.0
    other_dtl_delta:    float = 0.0   # other sources that grow DTL balance
    pension_dta_delta:  float = 0.0   # pension accruals that grow DTA balance
    other_dta_delta:    float = 0.0   # other sources that grow DTA balance

    # ── Payment timing ────────────────────────────────────────────────────────
    payment_lag:        int   = 0     # 0=current_year  1=next_year

    # ── Outputs (populated by solve()) ───────────────────────────────────────
    nol_used:               Optional[float] = None
    nol_close:              Optional[float] = None
    taxable_income:         Optional[float] = None
    current_tax_expense:    Optional[float] = None   # negative (expense on IS)
    deferred_tax_expense:   Optional[float] = None   # negative (expense); routes to CFO only
    total_tax_expense:      Optional[float] = None   # IS: current portion only
    effective_rate:         Optional[float] = None
    dta_close:              Optional[float] = None
    dtl_close:              Optional[float] = None
    taxes_payable_close:    Optional[float] = None   # positive magnitude
    tax_paid_cf:            Optional[float] = None   # positive magnitude (supplemental)
    cfo_deferred_tax:       Optional[float] = None   # positive when DTL grows

    def solve(self) -> "TaxBlock":
        # ── 1. NOL utilisation ───────────────────────────────────────────────
        if self.nol_enabled and self.nol_open > 0 and self.ebt > 0:
            # TCJA: NOL offsets up to nol_limit_pct (80%) of taxable income, capped by available NOL
            self.nol_used = min(self.nol_open, self.ebt * self.nol_limit_pct)
        else:
            self.nol_used = 0.0
        new_nol = max(0.0, -self.ebt) if self.ebt < 0 else 0.0
        self.nol_close = self.nol_open - self.nol_used + new_nol

        # ── 2. Current tax (IS booking) ──────────────────────────────────────
        self.taxable_income = max(0.0, self.ebt - self.nol_used)
        self.current_tax_expense = -self.taxable_income * self.statutory_rate  # ≤ 0

        # ── 3. Deferred tax components ───────────────────────────────────────
        # DTL growth: accelerated dep + other sources → positive delta = DTL grows
        dtl_delta = self.accel_dep_excess * self.statutory_rate + self.other_dtl_delta
        # DTA growth: pension accruals + other → positive delta = DTA grows
        dta_delta = self.pension_dta_delta + self.other_dta_delta

        # DTA/DTL closing balances (positive magnitudes)
        self.dta_close = max(0.0, self.dta_open + dta_delta)
        self.dtl_close = max(0.0, self.dtl_open + dtl_delta)

        # ── 4. IS tax: current portion only ─────────────────────────────────
        # Deferred tax expense stays off IS — routes to CFO as non-cash add-back.
        # This preserves IS at statutory rate × taxable_income.
        self.deferred_tax_expense = -(dtl_delta - dta_delta) * 0  # informational; not routed to IS
        self.total_tax_expense = self.current_tax_expense          # IS line

        # ── 5. Effective rate ────────────────────────────────────────────────
        self.effective_rate = (
            abs(self.total_tax_expense) / self.ebt
            if self.ebt > 1e-9 else 0.0
        )

        # ── 6. CFO deferred tax add-back ─────────────────────────────────────
        # Positive when DTL grows (less cash paid to IRS; deferred to future)
        # Negative when DTA grows (more cash paid than IS expense)
        self.cfo_deferred_tax = dtl_delta - dta_delta

        # ── 7. Taxes payable and cash paid (supplemental disclosure) ─────────
        if self.payment_lag == 0:
            # Tax paid same year as accrued
            self.taxes_payable_close = 0.0
            # Cash paid = current tax reduced by deferred portion
            self.tax_paid_cf = max(0.0, abs(self.current_tax_expense) - self.cfo_deferred_tax)
        else:
            # Tax paid in following year (next_year mode — US Steel)
            self.taxes_payable_close = abs(self.current_tax_expense)
            # Cash paid = prior year's payable (DTL offset doesn't change timing for prior year)
            self.tax_paid_cf = self.taxes_payable_open

        return self

    def validate(self, tol: float = 1.0) -> Tuple[bool, list]:
        issues = []
        if self.nol_close is not None and self.nol_close < -tol:
            issues.append(f"nol_close отрицательный: {self.nol_close:.0f}")
        if self.dta_close is not None and self.dta_close < -tol:
            issues.append(f"dta_close отрицательный: {self.dta_close:.0f}")
        if self.dtl_close is not None and self.dtl_close < -tol:
            issues.append(f"dtl_close отрицательный: {self.dtl_close:.0f}")
        if self.cfo_deferred_tax is None:
            issues.append("cfo_deferred_tax not computed")
        return len(issues) == 0, issues
