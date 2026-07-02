"""Provisions corkscrew block — pension, site restoration, legal claims.

Each category follows:
    close = open + charge - utilization + accretion

Results map to BS:
    pension → employee_benefits
    site_restoration + legal_claims → other_ncl (non-current provisions)

IS impact: provisions_expense (included in SGA or other_losses_gains)
CF impact: utilization = cash outflow (in cfo_other or WC delta)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass
class ProvisionCategory:
    name: str
    opening: float = 0.0
    charge_rate: float = 0.0        # annual charge as % of opening
    utilization_rate: float = 0.0   # annual utilization as % of opening
    accretion_rate: float = 0.0     # discount unwind (passage of time)

    # Outputs
    charge: float = 0.0
    utilization: float = 0.0
    accretion: float = 0.0
    closing: float = 0.0

    def solve(self) -> "ProvisionCategory":
        self.charge = self.opening * self.charge_rate
        self.utilization = self.opening * self.utilization_rate
        self.accretion = self.opening * self.accretion_rate
        self.closing = max(0.0, self.opening + self.charge - self.utilization + self.accretion)
        return self


@dataclass
class ProvisionsBlock:
    categories: Dict[str, ProvisionCategory] = field(default_factory=dict)

    # Outputs
    total_opening: float = 0.0
    total_closing: float = 0.0
    total_charge: float = 0.0       # IS expense
    total_utilization: float = 0.0  # CF cash outflow
    pension_closing: float = 0.0    # → employee_benefits (BS)
    other_closing: float = 0.0      # → other_ncl component (BS)

    def solve(self) -> "ProvisionsBlock":
        self.total_opening = 0.0
        self.total_closing = 0.0
        self.total_charge = 0.0
        self.total_utilization = 0.0
        self.pension_closing = 0.0
        self.other_closing = 0.0

        for cat in self.categories.values():
            cat.solve()
            self.total_opening += cat.opening
            self.total_closing += cat.closing
            self.total_charge += cat.charge
            self.total_utilization += cat.utilization

            if cat.name == "pension":
                self.pension_closing = cat.closing
            else:
                self.other_closing += cat.closing

        return self

    def validate(self, tol: float = 1.0) -> Tuple[bool, list]:
        issues = []
        for cat in self.categories.values():
            expected = cat.opening + cat.charge - cat.utilization + cat.accretion
            if abs(cat.closing - max(0.0, expected)) > tol:
                issues.append(f"provisions {cat.name}: close={cat.closing:.0f} ≠ expected={expected:.0f}")
        return len(issues) == 0, issues

    @classmethod
    def from_config(
        cls,
        prev_employee_benefits: float,
        prev_other_ncl: float,
        provisions_config: Optional[Dict] = None,
    ) -> "ProvisionsBlock":
        """Create provisions block from YAML config.

        Args:
            prev_employee_benefits: prior year employee_benefits (pension proxy)
            prev_other_ncl: prior year other_ncl (contains site restoration + legal)
            provisions_config: from project.yaml custom.provisions.categories
        """
        if not provisions_config:
            # Fallback: carry forward (backward compatible)
            return cls(categories={
                "pension": ProvisionCategory(name="pension", opening=prev_employee_benefits),
                "other": ProvisionCategory(name="other", opening=prev_other_ncl),
            })

        categories = {}
        cats_cfg = provisions_config.get("categories", {})

        # Pension: from employee_benefits
        pension_cfg = cats_cfg.get("pension", {})
        categories["pension"] = ProvisionCategory(
            name="pension",
            opening=prev_employee_benefits,
            charge_rate=float(pension_cfg.get("annual_charge_pct", 0.0)),
            utilization_rate=float(pension_cfg.get("utilization_pct", 0.0)),
            accretion_rate=0.0,  # pension doesn't accrete
        )

        # Site restoration: from other_ncl (approximate split)
        # Assume site_restoration ≈ 80% of other_ncl, legal ≈ 20%
        site_cfg = cats_cfg.get("site_restoration", {})
        legal_cfg = cats_cfg.get("legal_claims", {})

        site_pct = 0.80  # default split
        legal_pct = 0.20
        site_opening = prev_other_ncl * site_pct
        legal_opening = prev_other_ncl * legal_pct

        categories["site_restoration"] = ProvisionCategory(
            name="site_restoration",
            opening=site_opening,
            charge_rate=float(site_cfg.get("annual_charge_pct", 0.0)),
            utilization_rate=0.0,  # site restoration rarely utilized
            accretion_rate=float(site_cfg.get("accretion_rate", 0.02)),
        )

        categories["legal_claims"] = ProvisionCategory(
            name="legal_claims",
            opening=legal_opening,
            charge_rate=float(legal_cfg.get("annual_charge_pct", 0.30)),
            utilization_rate=float(legal_cfg.get("utilization_pct", 0.20)),
            accretion_rate=0.0,
        )

        return cls(categories=categories)
