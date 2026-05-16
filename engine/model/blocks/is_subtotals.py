"""IS subtotals: EBITDA, EBIT, EBT."""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..inputs import YearState, HistoricState

def solve_is_subtotals(state, historic):
    # type: (YearState, HistoricState) -> YearState
    da_in_cogs = _read_da_in_cogs(historic.company_id)
    if da_in_cogs:
        state.ebit = state.gross_profit + state.sga
        state.ebitda = state.ebit + state.total_da
    else:
        state.ebitda = state.gross_profit + state.sga
        state.ebit = state.ebitda - state.total_da

    state.ebt = (
        state.ebit
        + state.earnings_from_investees
        + state.net_periodic_benefit
        + (state.other_losses_gains or 0.0)
        + (state.ppe_disposal_gain or 0.0)
        + state.interest_income
        - state.interest_expense
        - state.other_financial_costs
        - state.loss_on_debt_extinguishment
    )
    return state


def _read_da_in_cogs(company_id: str) -> bool:
    try:
        import yaml
        from engine import ROOT
        cfg_path = ROOT / "companies" / company_id / "configs" / "project.yaml"
        if cfg_path.exists():
            with open(cfg_path) as fh:
                return (yaml.safe_load(fh) or {}).get(
                    'accounting_conventions', {}).get('da_in_cogs', True)
    except Exception:
        pass
    return True
