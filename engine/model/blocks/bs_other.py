"""Static BS items: LAST carry-forward for non-corkscrew items."""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..inputs import YearState

def solve_bs_other(state, prev):
    # type: (YearState, YearState) -> YearState
    state.restricted_cash = prev.restricted_cash
    state.goodwill = prev.goodwill
    state.investments_lt = prev.investments_lt
    state.employee_benefits = prev.employee_benefits
    state.other_nca = prev.other_nca
    fl_adj = getattr(state, '_fl_ncl_adj', 0)
    state.other_ncl = (prev.other_ncl or 0) + fl_adj
    state.accounts_payable_rp = prev.accounts_payable_rp
    state.payroll_payable = abs(state.sga) * 0.10
    return state
