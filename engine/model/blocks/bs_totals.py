"""BS totals computation block."""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from engine.constants import BS_DIFF_LOG_THRESHOLD

if TYPE_CHECKING:
    from ..inputs import YearState

logger = logging.getLogger(__name__)

def solve_bs_totals(state):
    # type: (YearState) -> YearState
    state.total_ca = (
        (state.cash or 0) + (state.restricted_cash or 0) +
        (state.accounts_receivable or 0) + (state.inventory or 0) +
        (state.other_ca or 0)
    )
    state.total_nca = (
        (state.ppe_net or 0) + (state.rou_asset or 0) +
        (state.intangibles or 0) + (state.goodwill or 0) +
        (state.dta or 0) + (state.investments_lt or 0) +
        (state.other_nca or 0)
    )
    state.total_assets = state.total_ca + state.total_nca

    state.total_cl = (
        (state.short_term_debt or 0) + abs(state.accounts_payable or 0) +
        abs(state.taxes_payable or 0) + abs(state.interest_payable or 0) +
        abs(state.payroll_payable or 0) + abs(state.lease_liab_current or 0) +
        abs(state.other_cl or 0)
    )
    state.total_ncl = (
        (state.long_term_debt or 0) + abs(state.dtl or 0) +
        abs(state.employee_benefits or 0) + abs(state.lease_liab_noncurrent or 0) +
        abs(state.other_ncl or 0)
    )
    state.total_liabilities = state.total_cl + state.total_ncl

    state.total_equity = (
        (state.share_capital or 0) + (state.apic or 0) +
        (state.retained_earnings or 0) - abs(state.treasury_stock or 0) +
        (state.aoci or 0) + (state.nci or 0)
    )
    state.total_liab_equity = state.total_liabilities + state.total_equity

    bs_diff = state.total_assets - state.total_liab_equity
    if abs(bs_diff) > BS_DIFF_LOG_THRESHOLD:
        logger.debug(
            f"  {state.year}: BS diff={bs_diff/1e6:.2f}M "
            f"(assets={state.total_assets/1e6:.0f} L+E={state.total_liab_equity/1e6:.0f})"
        )
    return state
