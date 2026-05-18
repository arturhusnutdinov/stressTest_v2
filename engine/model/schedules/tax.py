"""Tax corkscrew block — DTA/DTL/NOL/taxes_payable.

Follows IAS 12 / ASC 740 / CFI methodology:
  - Total Tax = Current Tax + Deferred Tax  → IS
  - Current Tax = rate × taxable_income (after NOL)  → taxes_payable → cash paid
  - Deferred Tax = DTL change − DTA change  → non-cash, CFO add-back
  - NOL creates DTA (= NOL × rate), used NOL reduces DTA

Sign conventions (match YearState):
  - dta, dtl, taxes_payable: positive magnitudes
  - tax_expense (IS): negative (expense) or positive (benefit when EBT < 0)
  - cfo_deferred_tax: positive when DTL grows (non-cash add-back to NI)
  - tax_paid_cf: positive magnitude (supplemental disclosure, cash out)

DTL growth mechanics (US GAAP accelerated depreciation / MACRS):
  - Tax dep > book dep  →  taxable income < book income
  - Less cash paid to IRS now  →  DTL liability grows
  - CFO add-back = dtl_delta (positive; the deferred portion of tax expense
    is non-cash this year)
"""
from __future__ import annotations
from dataclasses import dataclass
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
    nol_limit_pct:      float = 0.80  # max % of taxable income offsettable by NOL (TCJA)

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
    deferred_tax_expense:   Optional[float] = None   # negative (expense) or positive (benefit)
    total_tax_expense:      Optional[float] = None   # IS: Current + Deferred
    effective_rate:         Optional[float] = None
    dta_close:              Optional[float] = None
    dtl_close:              Optional[float] = None
    taxes_payable_close:    Optional[float] = None   # positive magnitude
    tax_paid_cf:            Optional[float] = None   # positive magnitude (supplemental)
    cfo_deferred_tax:       Optional[float] = None   # positive when DTL grows

    def solve(self) -> "TaxBlock":
        rate = self.statutory_rate

        # ── 1. NOL utilisation ───────────────────────────────────────────────
        if self.nol_enabled and self.nol_open > 0 and self.ebt > 0:
            # TCJA: NOL offsets up to nol_limit_pct (80%) of taxable income,
            # capped by available NOL balance
            self.nol_used = min(self.nol_open, self.ebt * self.nol_limit_pct)
        else:
            self.nol_used = 0.0
        # New NOL created from current-year loss
        new_nol = max(0.0, -self.ebt) if self.ebt < 0 else 0.0
        self.nol_close = self.nol_open - self.nol_used + new_nol

        # ── 2. Depreciation adjustment (book vs tax) ────────────────────────
        # Tax depreciation > book depreciation → taxable income lower → DTL grows
        # accel_dep_excess = tax_dep − book_dep (positive when tax dep > book dep)
        dep_adjustment = self.accel_dep_excess   # reduces taxable income

        # ── 3. Taxable income (for current tax / cash tax) ───────────────────
        # = EBT − NOL used − depreciation adjustment (tax basis)
        self.taxable_income = max(0.0, self.ebt - self.nol_used - dep_adjustment)
        self.current_tax_expense = -self.taxable_income * rate   # ≤ 0 (cash tax)

        # ── 4. Deferred tax — temporary differences ──────────────────────────
        # DTL growth: accelerated dep + other sources → positive delta = DTL grows
        dtl_delta = self.accel_dep_excess * rate + self.other_dtl_delta
        # DTA growth: pension accruals + other → positive delta = DTA grows
        dta_delta_temp = self.pension_dta_delta + self.other_dta_delta

        # ── 5. DTA from NOL (IAS 12 / ASC 740) ──────────────────────────────
        # New losses (EBT < 0) create NOL → DTA at statutory rate (tax benefit).
        # Pre-existing NOL usage does NOT reverse DTA — the historical DTA opening
        # balance already reflects whatever NOL-related DTA existed. We only create
        # NEW DTA from losses arising in the current period.
        nol_dta_delta = new_nol * rate   # positive when loss → DTA grows (tax benefit)

        # Total DTA/DTL deltas
        dta_delta_total = dta_delta_temp + nol_dta_delta

        # Closing balances (positive magnitudes)
        self.dta_close = max(0.0, self.dta_open + dta_delta_total)
        self.dtl_close = max(0.0, self.dtl_open + dtl_delta)

        # ── 6. Deferred tax expense (IS) ─────────────────────────────────────
        # IAS 12: Deferred tax expense = change in net DTL (DTL − DTA)
        # Positive dtl_delta → expense (negative); positive dta_delta → benefit (positive)
        self.deferred_tax_expense = -(dtl_delta - dta_delta_total)

        # ── 7. Total tax on IS = Current + Deferred ──────────────────────────
        # Per CFI/IAS 12: Total Tax = rate × EBT (when no NOL)
        # Current = rate × (EBT − dep_adj − NOL) = cash tax (lower due to accel dep)
        # Deferred = rate × dep_adj + NOL DTA change = non-cash portion
        # Current + Deferred = rate × EBT ✓
        self.total_tax_expense = self.current_tax_expense + self.deferred_tax_expense

        # ── 7. Effective rate ────────────────────────────────────────────────
        self.effective_rate = (
            abs(self.total_tax_expense) / abs(self.ebt)
            if abs(self.ebt) > 1e-9 else 0.0
        )

        # ── 8. CFO deferred tax add-back ─────────────────────────────────────
        # Deferred tax is non-cash: reverse it in CFO.
        # Positive when DTL grows more than DTA (less cash paid than IS expense)
        self.cfo_deferred_tax = dtl_delta - dta_delta_total

        # ── 9. Taxes payable and cash paid ───────────────────────────────────
        if self.payment_lag == 0:
            # Tax paid same year as accrued
            self.taxes_payable_close = 0.0
            self.tax_paid_cf = max(0.0, abs(self.current_tax_expense))
        else:
            # Tax paid in following year (next_year mode)
            self.taxes_payable_close = max(0.0, abs(self.current_tax_expense))
            self.tax_paid_cf = self.taxes_payable_open

        return self

    def validate(self, tol: float = 1.0) -> Tuple[bool, list]:
        issues = []
        if self.nol_close is not None and self.nol_close < -tol:
            issues.append(f"nol_close negative: {self.nol_close:.0f}")
        if self.dta_close is not None and self.dta_close < -tol:
            issues.append(f"dta_close negative: {self.dta_close:.0f}")
        if self.dtl_close is not None and self.dtl_close < -tol:
            issues.append(f"dtl_close negative: {self.dtl_close:.0f}")
        if self.cfo_deferred_tax is None:
            issues.append("cfo_deferred_tax not computed")
        return len(issues) == 0, issues
