"""BS static/non-modeled items: configurable via forecast_methods.bs in project.yaml.

Methods:
  - last:  carry forward from previous year (default)
  - ewa:   exponentially weighted average of historical values
  - zero:  set to zero
  - model: handled by dedicated block (TaxBlock, ProvisionsBlock, etc.)

If provisions_corkscrew_enabled: uses ProvisionsBlock for employee_benefits/other_ncl.
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from engine.constants import PAYROLL_PCT_OF_SGA  # default fallback

if TYPE_CHECKING:
    from ..inputs import YearState, ModelConfig

logger = logging.getLogger(__name__)

# Default method for each BS static item (if not specified in YAML)
_DEFAULTS = {
    "restricted_cash":     "last",
    "goodwill":            "last",
    "investments_lt":      "last",
    "employee_benefits":   "last",
    "other_nca":           "last",
    "other_ncl":           "last",
    "accounts_payable_rp": "last",
    "dta":                 "last",
    "dtl":                 "last",
    "aoci":                "last",
    "nci":                 "last",
    "share_capital":       "last",
    "apic":                "last",
    "treasury_stock":      "last",
}


def _get_method(config, metric: str) -> str:
    """Get forecast method for a BS metric from config (forecast_methods.BS)."""
    if config is None:
        return _DEFAULTS.get(metric, "last")
    fc_cfg = config.get_forecast_method("BS", metric) if hasattr(config, 'get_forecast_method') else None
    if fc_cfg is not None:
        return getattr(fc_cfg, 'method', 'last') or 'last'
    return _DEFAULTS.get(metric, "last")


def solve_bs_other(state, prev, config=None):
    # type: (YearState, YearState, ModelConfig) -> YearState
    """Set non-modeled BS items based on forecast_methods.bs config.

    Items handled here are NOT computed by corkscrews (WC, Debt, PPE, etc.)
    They are either carried forward, set to EWA, or zeroed.
    """

    # ── Static carry-forward items ──
    for attr in ("restricted_cash", "goodwill", "investments_lt",
                 "other_nca", "aoci", "nci", "share_capital", "apic",
                 "treasury_stock", "dta", "dtl"):
        method = _get_method(config, attr)
        if method == "last":
            setattr(state, attr, getattr(prev, attr, 0) or 0)
        elif method == "zero":
            setattr(state, attr, 0)
        # "ewa" and "model" handled elsewhere (EWA in preprocessor, model in blocks)

    # ── Employee benefits ──
    method = _get_method(config, "employee_benefits")
    if method == "last":
        state.employee_benefits = prev.employee_benefits or 0
    # If provisions_corkscrew_enabled → override below

    # ── Other NCL ──
    fl_adj = getattr(state, '_fl_ncl_adj', 0)
    method = _get_method(config, "other_ncl")
    if method == "last":
        state.other_ncl = (prev.other_ncl or 0) + fl_adj
    elif method == "zero":
        state.other_ncl = fl_adj

    # ── Related party payables ──
    state.accounts_payable_rp = prev.accounts_payable_rp or 0

    # ── Payroll: % of SGA ──
    _payroll_pct = config.get_constraint("sga", "payroll_pct_of_sga", PAYROLL_PCT_OF_SGA) \
        if config and hasattr(config, 'get_constraint') else PAYROLL_PCT_OF_SGA
    state.payroll_payable = abs(state.sga or 0) * _payroll_pct

    # ── Provisions corkscrew (optional, enabled via config) ──
    if config and getattr(config, 'provisions_corkscrew_enabled', False):
        from ..schedules.provisions import ProvisionsBlock
        prov_block = ProvisionsBlock.from_config(
            prev_employee_benefits=prev.employee_benefits or 0.0,
            prev_other_ncl=(prev.other_ncl or 0.0),
        ).solve()
        state.employee_benefits = prov_block.pension_closing
        state.other_ncl = prov_block.other_closing + fl_adj

    return state
