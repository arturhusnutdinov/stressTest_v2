"""Working Capital corkscrew block — 6 параллельных корксрю."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple

from engine.constants import (
    WC_OTHER_CA_PCT_REV, WC_ACCRUED_PCT_SGA, WC_OTHER_CL_PCT_REV,
    WC_CYCLICAL_ADJ_MIN, WC_CYCLICAL_ADJ_MAX,
    WC_DSO_CYCLICAL_ELASTICITY, WC_DIH_CYCLICAL_ELASTICITY,
    WC_DPO_CYCLICAL_ELASTICITY,
)


@dataclass
class WCBlock:
    """
    Working Capital corkscrew — 6 блоков.
    BS:  ar_close, inventory_close, ap_close, other_ca_close,
         accrued_close, other_cl_close
    CF (CFO): get_wc_delta() → cfo_wc_changes
              Знаковое соглашение:
              −ΔAR, −ΔInv, +ΔAP, −ΔOtherCA, +ΔAccrued, +ΔOtherCL
    """
    # AR
    ar_open:        float = 0.0
    ar_additions:   float = 0.0     # продажи в кредит = revenue
    ar_collections: float = 0.0     # поступления
    ar_fx:          float = 0.0
    ar_close:       float = 0.0     # computed

    # Inventory
    inventory_open:  float = 0.0
    inv_purchases:   float = 0.0    # закупки = COGS + ΔINV
    inv_cogs:        float = 0.0    # списание в COGS
    inv_fx:          float = 0.0
    inventory_close: float = 0.0

    # AP
    ap_open:         float = 0.0
    ap_purchases:    float = 0.0    # покупки в кредит
    ap_payments:     float = 0.0    # оплата поставщикам
    ap_fx:           float = 0.0
    ap_close:        float = 0.0

    # Other CA
    other_ca_open:   float = 0.0
    other_ca_add:    float = 0.0
    other_ca_red:    float = 0.0
    other_ca_fx:     float = 0.0
    other_ca_close:  float = 0.0

    # Accrued Liabilities
    accrued_open:    float = 0.0
    accrued_add:     float = 0.0
    accrued_pay:     float = 0.0
    accrued_fx:      float = 0.0
    accrued_close:   float = 0.0

    # Other CL
    other_cl_open:   float = 0.0
    other_cl_add:    float = 0.0
    other_cl_red:    float = 0.0
    other_cl_fx:     float = 0.0
    other_cl_close:  float = 0.0

    def solve(self) -> "WCBlock":
        self.ar_close        = max(0.0, self.ar_open + self.ar_additions - self.ar_collections + self.ar_fx)
        self.inventory_close = max(0.0, self.inventory_open + self.inv_purchases - self.inv_cogs + self.inv_fx)
        self.ap_close        = max(0.0, self.ap_open + self.ap_purchases - self.ap_payments + self.ap_fx)
        self.other_ca_close  = max(0.0, self.other_ca_open + self.other_ca_add - self.other_ca_red + self.other_ca_fx)
        self.accrued_close   = max(0.0, self.accrued_open + self.accrued_add - self.accrued_pay + self.accrued_fx)
        self.other_cl_close  = max(0.0, self.other_cl_open + self.other_cl_add - self.other_cl_red + self.other_cl_fx)
        return self

    def get_wc_delta(self) -> float:
        """
        Изменение кэша от WC — идёт в CFO.
        Рост актива = отток кэша (−), рост пассива = приток (+).
        """
        delta_ar       = self.ar_close       - self.ar_open
        delta_inv      = self.inventory_close - self.inventory_open
        delta_ap       = self.ap_close        - self.ap_open
        delta_other_ca = self.other_ca_close  - self.other_ca_open
        delta_accrued  = self.accrued_close   - self.accrued_open
        delta_other_cl = self.other_cl_close  - self.other_cl_open
        return (
            - delta_ar
            - delta_inv
            + delta_ap
            - delta_other_ca
            + delta_accrued
            + delta_other_cl
        )

    def get_cf_components(self) -> dict:
        """Разбивка WC delta по компонентам для CF Statement."""
        return {
            "wc_accounts_receivable_change": -(self.ar_close - self.ar_open),
            "wc_inventory_change":          -(self.inventory_close - self.inventory_open),
            "wc_accounts_payable_change":    (self.ap_close - self.ap_open),
            "wc_other_change":              (
                -(self.other_ca_close - self.other_ca_open)
                + (self.accrued_close - self.accrued_open)
                + (self.other_cl_close - self.other_cl_open)
            ),
        }

    def validate(self, tol: float = 1.0) -> Tuple[bool, list]:
        issues = []
        checks = [
            ("AR", self.ar_close, self.ar_open + self.ar_additions - self.ar_collections + self.ar_fx),
            ("Inv", self.inventory_close, self.inventory_open + self.inv_purchases - self.inv_cogs + self.inv_fx),
            ("AP", self.ap_close, self.ap_open + self.ap_purchases - self.ap_payments + self.ap_fx),
            ("OtherCA", self.other_ca_close, self.other_ca_open + self.other_ca_add - self.other_ca_red + self.other_ca_fx),
            ("Accrued", self.accrued_close, self.accrued_open + self.accrued_add - self.accrued_pay + self.accrued_fx),
            ("OtherCL", self.other_cl_close, self.other_cl_open + self.other_cl_add - self.other_cl_red + self.other_cl_fx),
        ]
        for name, actual, expected in checks:
            if abs(actual - expected) > tol:
                issues.append(f"{name}: {actual:.0f} ≠ {expected:.0f}")
        return len(issues) == 0, issues

    @classmethod
    def from_days(
        cls,
        prev,
        revenue: float,
        cogs: float,
        sga: float,
        dso: float = 45.0,
        dih: float = 60.0,
        dpo: float = 50.0,
        other_ca_pct_rev: float = WC_OTHER_CA_PCT_REV,
        accrued_pct_sga:  float = WC_ACCRUED_PCT_SGA,
        other_cl_pct_rev: float = WC_OTHER_CL_PCT_REV,
        revenue_growth_rate: float = 0.0,
    ) -> "WCBlock":
        """
        Строит WCBlock через дни оборачиваемости.

        Правила 3-Statement Model:
          AR_close  = Revenue × DSO/365
          Inv_close = |COGS| × DIH/365
          AP_close  = |COGS| × DPO/365

        CF маршрутизация (indirect method):
          ΔAR  → cfo_change_ar  = -(AR_close  - AR_open)   [рост AR = отток]
          ΔInv → cfo_change_inv = -(Inv_close - Inv_open)  [рост Inv = отток]
          ΔAP  → cfo_change_ap  = +(AP_close  - AP_open)   [рост AP = приток]

        Cyclical WC sensitivity (revenue_growth_rate):
          Declining revenue → DSO and DIH increase (counter-cyclical).
          DPO decreases in downturn (suppliers tighten terms).
          Adjustments capped at ±20% of base days.
        """
        # ── Cyclical adjustment of WC days ───────────────────────
        # Calibrated from Rusal 2011-2025 OLS regressions:
        # DSO: rev↑ → DSO↓ (customers pay faster when prices high)
        # DIH: rev↑ → DIH↑ (build inventory when demand strong)
        # DPO: rev↑ → DPO↓ (pay suppliers faster when cash available)
        g = revenue_growth_rate
        adj_factor_dso = max(WC_CYCLICAL_ADJ_MIN, min(WC_CYCLICAL_ADJ_MAX, 1.0 - WC_DSO_CYCLICAL_ELASTICITY * g))
        adj_factor_dih = max(WC_CYCLICAL_ADJ_MIN, min(WC_CYCLICAL_ADJ_MAX, 1.0 + WC_DIH_CYCLICAL_ELASTICITY * g))
        adj_factor_dpo = max(WC_CYCLICAL_ADJ_MIN, min(WC_CYCLICAL_ADJ_MAX, 1.0 - WC_DPO_CYCLICAL_ELASTICITY * g))
        dso = dso * adj_factor_dso
        dih = dih * adj_factor_dih
        dpo = dpo * adj_factor_dpo

        # ── Целевые балансы по дням ──────────────────────────────
        ar_target  = abs(revenue) * dso / 365.0
        inv_target = abs(cogs)    * dih / 365.0
        ap_target  = abs(cogs)    * dpo / 365.0

        # Other CA: % от Revenue (EWA из истории)
        other_ca_target = abs(revenue) * other_ca_pct_rev

        # Accrued liabilities (payroll etc): % от SGA
        accrued_target = abs(sga) * accrued_pct_sga

        # Other CL: % от Revenue
        other_cl_target = abs(revenue) * other_cl_pct_rev

        # ── AR corkscrew ─────────────────────────────────────────
        # Open → +Revenue (продажи) → -Collections → Close
        ar_open        = abs(prev.accounts_receivable or 0)
        ar_collections = ar_open + abs(revenue) - ar_target

        # ── Inventory corkscrew ──────────────────────────────────
        # Open → +Purchases → -COGS → Close
        inv_open      = abs(prev.inventory or 0)
        inv_purchases = inv_target + abs(cogs) - inv_open  # balancing
        inv_purchases = max(0.0, inv_purchases)

        # ── AP corkscrew ─────────────────────────────────────────
        # Open → +Purchases (= inv_purchases) → -Payments → Close
        ap_open     = abs(prev.accounts_payable or 0)
        ap_payments = ap_open + inv_purchases - ap_target
        ap_payments = max(0.0, ap_payments)

        # ── Other CA ─────────────────────────────────────────────
        other_ca_open = abs(prev.other_ca or 0)

        # ── Accrued liabilities ───────────────────────────────────
        accrued_open = abs(getattr(prev, 'accrued_liabilities', 0) or 0)

        # ── Other CL ─────────────────────────────────────────────
        other_cl_open = abs(getattr(prev, 'other_cl', 0) or 0)

        block = cls(
            # AR
            ar_open        = ar_open,
            ar_additions   = abs(revenue),
            ar_collections = max(0.0, ar_collections),
            ar_close       = ar_target,
            # Inventory
            inventory_open  = inv_open,
            inv_purchases   = inv_purchases,
            inv_cogs        = abs(cogs),
            inventory_close = inv_target,
            # AP
            ap_open      = ap_open,
            ap_purchases = inv_purchases,
            ap_payments  = max(0.0, ap_payments),
            ap_close     = ap_target,
            # Other CA
            other_ca_open  = other_ca_open,
            other_ca_add   = other_ca_target,
            other_ca_red   = other_ca_open,   # reset к target
            other_ca_close = other_ca_target,
            # Accrued liabilities
            accrued_open  = accrued_open,
            accrued_add   = accrued_target,
            accrued_pay   = accrued_open,     # reset к target
            accrued_close = accrued_target,
            # Other CL
            other_cl_open  = other_cl_open,
            other_cl_add   = other_cl_target,
            other_cl_red   = other_cl_open,   # reset к target
            other_cl_close = other_cl_target,
        )
        return block
