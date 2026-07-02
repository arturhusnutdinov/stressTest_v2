"""Interest payable corkscrew block."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple

from engine.constants import INTEREST_PAYABLE_TIMING_DEFAULT


@dataclass
class InterestPayableBlock:
    # Inputs
    interest_payable_open:  float = 0.0
    interest_accrued:       float = 0.0   # total interest expense for period
    payment_timing:         str   = INTEREST_PAYABLE_TIMING_DEFAULT   # "current_year" | "next_year"

    # Outputs
    interest_payable_close: Optional[float] = None
    interest_paid_cf:       Optional[float] = None

    def solve(self) -> "InterestPayableBlock":
        if self.payment_timing == "current_year":
            # Pay everything accrued this period; balance sheet goes to zero
            self.interest_payable_close = 0.0
            self.interest_paid_cf       = self.interest_accrued + self.interest_payable_open
        else:
            # next_year: accrue now, pay prior balance this period
            self.interest_payable_close = self.interest_accrued
            self.interest_paid_cf       = self.interest_payable_open
        return self

    def validate(self, tol: float = 1.0) -> Tuple[bool, list]:
        issues = []
        if self.interest_payable_close is not None and self.interest_paid_cf is not None:
            # Reconciliation: open + accrued = paid + close
            lhs = self.interest_payable_open + self.interest_accrued
            rhs = self.interest_paid_cf + self.interest_payable_close
            if abs(lhs - rhs) > tol:
                issues.append(
                    f"interest payable bridge: open+accrued={lhs:.0f} ≠ paid+close={rhs:.0f}"
                )
        return len(issues) == 0, issues
