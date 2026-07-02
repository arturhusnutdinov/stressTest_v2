"""Static BS items: LAST carry-forward for non-corkscrew items.

If provisions_corkscrew_enabled: uses ProvisionsBlock instead of carry.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from engine.constants import PAYROLL_PCT_OF_SGA
if TYPE_CHECKING:
    from ..inputs import YearState, ModelConfig

def solve_bs_other(state, prev, config=None):
    # type: (YearState, YearState, ModelConfig) -> YearState
    state.restricted_cash = prev.restricted_cash
    state.goodwill = prev.goodwill
    state.investments_lt = prev.investments_lt
    state.employee_benefits = prev.employee_benefits
    state.other_nca = prev.other_nca
    fl_adj = getattr(state, '_fl_ncl_adj', 0)
    state.other_ncl = (prev.other_ncl or 0) + fl_adj
    state.accounts_payable_rp = prev.accounts_payable_rp
    state.payroll_payable = abs(state.sga) * PAYROLL_PCT_OF_SGA

    # Provisions corkscrew (optional, enabled via config)
    if config and getattr(config, 'provisions_corkscrew_enabled', False):
        from ..schedules.provisions import ProvisionsBlock
        prov_block = ProvisionsBlock.from_config(
            prev_employee_benefits=prev.employee_benefits or 0.0,
            prev_other_ncl=(prev.other_ncl or 0.0),
        ).solve()
        state.employee_benefits = prov_block.pension_closing
        state.other_ncl = prov_block.other_closing + fl_adj

    return state
