"""Intangibles corkscrew block."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple

from engine.constants import INTANG_AMORT_RATE_FALLBACK


@dataclass
class IntangiblesBlock:
    """
    Intangibles corkscrew.
    IS:  amort_is → amortization_intangibles (в total_da)
         impairments_is → asset_impairment (one-time, обычно ZERO в прогнозе)
    BS:  intangibles = intang_close
    CF:  cfi_intang_additions = -additions
    """
    intang_open:    float = 0.0
    additions:      float = 0.0     # приобретения → -CFI
    amort_is:       float = 0.0     # амортизация → IS + total_da
    impairments_is: float = 0.0     # обесценение → IS (ZERO в прогнозе)
    disposals:      float = 0.0     # выбытия
    other_adj:      float = 0.0     # FX, переоценка
    intang_close:   Optional[float] = None

    def solve(self) -> "IntangiblesBlock":
        self.intang_close = max(0.0,
            self.intang_open
            + self.additions
            - self.amort_is
            - self.impairments_is
            - self.disposals
            + self.other_adj
        )
        return self

    def validate(self, tol: float = 1.0) -> Tuple[bool, list]:
        issues = []
        if self.intang_close is not None:
            expected = (self.intang_open + self.additions
                       - self.amort_is - self.impairments_is
                       - self.disposals + self.other_adj)
            if abs(self.intang_close - expected) > tol:
                issues.append(f"intang_close {self.intang_close:.0f} ≠ {expected:.0f}")
            if self.intang_close < -tol:
                issues.append(f"intang_close < 0: {self.intang_close:.0f}")
            max_disposals = (self.intang_open + self.additions) * 1.1
            if self.disposals > max_disposals + tol:
                issues.append(f"disposals {self.disposals:.0f} > max {max_disposals:.0f}")
        return len(issues) == 0, issues

    @classmethod
    def from_prev_state(
        cls,
        prev,
        amort_rate: float = INTANG_AMORT_RATE_FALLBACK,
        additions_pct_revenue: float = 0.0,
        revenue: float = 0.0,
    ) -> "IntangiblesBlock":
        intang_open = prev.intangibles or 0.0
        amort = intang_open * amort_rate
        additions = revenue * additions_pct_revenue
        block = cls(
            intang_open=intang_open,
            additions=additions,
            amort_is=min(amort, intang_open + additions),
            impairments_is=0.0,   # ZERO в базовом прогнозе
        )
        return block.solve()
