"""PP&E corkscrew block."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass
class PPEBlock:
    # Gross
    gross_open:        float = 0.0
    gross_capex:       float = 0.0
    gross_disposals:   float = 0.0
    gross_other_adj:   float = 0.0
    gross_close:       Optional[float] = None
    # AccDep
    accdep_open:       float = 0.0
    dep_charge:        float = 0.0
    dep_on_disposals:  float = 0.0
    accdep_other_adj:  float = 0.0
    accdep_close:      Optional[float] = None
    # Net
    net_open:          float = 0.0
    net_close:         Optional[float] = None
    # Disposals
    disposal_proceeds: float = 0.0
    nbv_disposed:      Optional[float] = None
    gain_loss:         Optional[float] = None

    def solve(self) -> "PPEBlock":
        self.gross_close  = self.gross_open + self.gross_capex - self.gross_disposals + self.gross_other_adj
        self.accdep_close = self.accdep_open + self.dep_charge - self.dep_on_disposals + self.accdep_other_adj
        self.net_close    = self.gross_close - self.accdep_close
        self.nbv_disposed = self.gross_disposals - self.dep_on_disposals
        self.gain_loss    = self.disposal_proceeds - (self.nbv_disposed or 0)
        return self

    def validate(self, tol: float = 1.0) -> Tuple[bool, list]:
        issues = []
        if self.gross_close is not None:
            expected = self.gross_open + self.gross_capex - self.gross_disposals + self.gross_other_adj
            if abs(self.gross_close - expected) > tol:
                issues.append(f"gross_close: {self.gross_close:.0f} ≠ {expected:.0f}")
        if self.net_close is not None and self.gross_close is not None and self.accdep_close is not None:
            expected_net = self.gross_close - self.accdep_close
            if abs(self.net_close - expected_net) > tol:
                issues.append(f"net_close: {self.net_close:.0f} ≠ {expected_net:.0f}")
        return len(issues) == 0, issues

    @classmethod
    def from_prev_state(cls, prev, dep_rate: float, capex: float,
                        disposal_proceeds: float = 0.0,
                        disposal_pct_of_capex: float = 0.3) -> "PPEBlock":
        gross_open  = prev.ppe_gross  or prev.ppe_net
        accdep_open = prev.ppe_accum_dep
        net_open    = prev.ppe_net
        if gross_open == 0 and net_open > 0:
            gross_open  = net_open * 2
            accdep_open = gross_open - net_open
        gross_disposals   = capex * min(disposal_pct_of_capex, 0.5)
        dep_on_disposals  = gross_disposals * (accdep_open / max(gross_open, 1e-9))
        avg_net = (net_open + max(net_open + capex - (gross_open*dep_rate), 0)) / 2
        dep_charge = dep_rate * avg_net
        block = cls(
            gross_open=gross_open, accdep_open=accdep_open, net_open=net_open,
            gross_capex=capex, gross_disposals=gross_disposals,
            dep_charge=dep_charge, dep_on_disposals=dep_on_disposals,
            disposal_proceeds=disposal_proceeds,
        )
        return block.solve()
