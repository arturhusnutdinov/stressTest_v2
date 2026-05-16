"""Cash from CF Bridge block."""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..inputs import YearState, ModelConfig

logger = logging.getLogger(__name__)

def solve_cash_from_cf(state, prev, config):
    # type: (YearState, YearState, ModelConfig) -> YearState
    state.cf_cash_opening = prev.cash
    state.cf_net_change = state.cfo_total + state.cfi_total + state.cff_total
    state.cf_cash_ending = state.cf_cash_opening + state.cf_net_change
    state.cash = state.cf_cash_ending
    min_cash = getattr(config, 'min_cash', 0.0) or 0.0
    if state.cash < min_cash and min_cash > 0:
        logger.debug(f"  {state.year}: cash={state.cash/1e6:.0f}M < min_cash={min_cash/1e6:.0f}M")
    return state
