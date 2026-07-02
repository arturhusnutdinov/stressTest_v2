"""Equity corkscrew block — retained earnings, share capital, AOCI, NCI."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple

from engine.constants import DIVIDEND_PAYOUT_DEFAULT, BUYBACK_PCT_FCF_DEFAULT, BUYBACK_LEVERAGE_MAX  # noqa: F401


@dataclass
class EquityBlock:
    # Share capital
    share_cap_open:     float = 0.0
    share_cap_change:   float = 0.0
    share_cap_close:    Optional[float] = None

    # APIC
    apic_open:          float = 0.0
    apic_change:        float = 0.0
    apic_close:         Optional[float] = None

    # Treasury stock (stored as negative or positive abs value)
    treasury_open:      float = 0.0    # absolute value (positive)
    buybacks:           float = 0.0    # additional buybacks this period
    treasury_close:     Optional[float] = None

    # Retained earnings
    re_open:            float = 0.0
    net_income:         float = 0.0
    dividends:          float = 0.0    # positive = cash out
    re_other_adj:       float = 0.0
    re_close:           Optional[float] = None

    # AOCI
    aoci_open:          float = 0.0
    aoci_change:        float = 0.0
    aoci_close:         Optional[float] = None

    # NCI
    nci_open:           float = 0.0
    nci_net_income:     float = 0.0
    nci_dividends:      float = 0.0
    nci_other:          float = 0.0
    nci_close:          Optional[float] = None

    # Total
    total_equity_close: Optional[float] = None

    def solve(self) -> "EquityBlock":
        self.share_cap_close = self.share_cap_open + self.share_cap_change
        self.apic_close      = self.apic_open + self.apic_change
        self.treasury_close  = self.treasury_open + self.buybacks
        self.re_close        = self.re_open + self.net_income - self.dividends + self.re_other_adj
        self.aoci_close      = self.aoci_open + self.aoci_change
        self.nci_close       = self.nci_open + self.nci_net_income - self.nci_dividends + self.nci_other

        self.total_equity_close = (
            self.share_cap_close
            + self.apic_close
            - abs(self.treasury_close)
            + self.re_close
            + self.aoci_close
        )
        return self

    def validate(self, tol: float = 1.0) -> Tuple[bool, list]:
        issues = []
        if self.re_close is not None:
            exp = self.re_open + self.net_income - self.dividends + self.re_other_adj
            if abs(self.re_close - exp) > tol:
                issues.append(f"re_close {self.re_close:.0f} ≠ {exp:.0f}")
        if self.total_equity_close is not None and self.re_close is not None:
            exp = (
                (self.share_cap_close or 0)
                + (self.apic_close or 0)
                - abs(self.treasury_close or 0)
                + self.re_close
                + (self.aoci_close or 0)
            )
            if abs(self.total_equity_close - exp) > tol:
                issues.append(f"total_equity_close {self.total_equity_close:.0f} ≠ {exp:.0f}")
        return len(issues) == 0, issues

    @classmethod
    def from_prev_state(
        cls,
        prev,
        net_income:          float = 0.0,
        dividend_pct_ni:     float = 0.0,    # pct of net_income allocated to dividends
        dividend_payout:     float = 0.0,    # legacy alias for dividend_pct_ni
        buyback_pct:         float = 0.0,    # legacy: pct of (share_cap + apic), kept for compat
        buyback_pct_fcf:     float = 0.0,    # pct of prior-year FCF used for buybacks
        buyback_leverage_max: float = 2.0,   # buybacks only when ND/EBITDA < this
        net_debt_ebitda:     float = 0.0,    # current ND/EBITDA for the leverage gate
        fcf_for_buyback:     float = 0.0,    # prior-year FCF as buyback basis
        aoci_change:         float = 0.0,
        nci_net_income:      float = 0.0,
        nci_dividends:       float = 0.0,
        equity_additional_events: Optional[dict] = None,  # {issuance: $, buyback: $, dividends: $}
    ) -> "EquityBlock":
        share_cap = getattr(prev, "share_capital",      0.0) or 0.0
        apic      = getattr(prev, "apic",               0.0) or 0.0
        treasury  = abs(getattr(prev, "treasury_stock", 0.0) or 0.0)
        re        = getattr(prev, "retained_earnings",  0.0) or 0.0
        aoci      = getattr(prev, "aoci",               0.0) or 0.0
        nci       = getattr(prev, "nci",                0.0) or 0.0

        # dividend_pct_ni takes precedence; fall back to legacy dividend_payout
        _div_rate = dividend_pct_ni if dividend_pct_ni > 0 else dividend_payout
        dividends = max(0.0, net_income * _div_rate) if net_income > 0 else 0.0

        # Buybacks: FCF-based with leverage gate (preferred) or legacy pct-of-equity
        if buyback_pct_fcf > 0:
            if net_debt_ebitda < buyback_leverage_max and fcf_for_buyback > 0:
                new_buybacks = fcf_for_buyback * buyback_pct_fcf
            else:
                new_buybacks = 0.0
        else:
            new_buybacks = (share_cap + apic) * buyback_pct

        # Apply additive equity events (one-off issuances, buybacks, special dividends)
        if equity_additional_events:
            dividends  += equity_additional_events.get("dividends", 0.0)
            new_buybacks += equity_additional_events.get("buyback", 0.0)
            # Issuance reduces treasury / increases APIC
            apic += equity_additional_events.get("issuance", 0.0)

        block = cls(
            share_cap_open=share_cap,
            apic_open=apic,
            treasury_open=treasury,
            buybacks=new_buybacks,
            re_open=re,
            net_income=net_income,
            dividends=dividends,
            aoci_open=aoci,
            aoci_change=aoci_change,
            nci_open=nci,
            nci_net_income=nci_net_income,
            nci_dividends=nci_dividends,
        )
        return block.solve()
