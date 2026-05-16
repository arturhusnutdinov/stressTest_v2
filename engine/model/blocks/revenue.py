"""
Revenue forecast block.

Priority:
  1. Segment model (if configured in YAML)
  2. Explicit macro_forecasts['revenue']
  3. OLS regression on macro factor (beta from preprocessor)
  4. EWA with historical clamp
  5. Fallback: prev × 1.02
"""
from __future__ import annotations
import math
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..inputs import YearState, HistoricState, ModelConfig

logger = logging.getLogger(__name__)


def solve_revenue(state, prev, historic, config):
    # type: (YearState, YearState, HistoricState, ModelConfig) -> YearState
    year = state.year

    # 1. Segment model
    seg_model = getattr(config, '_segment_model', None)
    if seg_model is not None:
        seg_total = seg_model.get(year)
        if seg_total and seg_total > 0:
            state.revenue = seg_total
            return state

    # 2. Explicit macro forecast
    macro_rev = historic.macro_forecasts.get("revenue", {}).get(year)
    if macro_rev is not None and macro_rev > 0:
        state.revenue = macro_rev
        return state

    # 3. OLS regression on macro factor (read from YAML once)
    revenue_factor = _get_revenue_factor(historic.company_id)
    if revenue_factor:
        factor_series = historic.macro_forecasts.get(revenue_factor, {})
        if factor_series:
            betas = historic.preprocess.get("revenue_betas", {})
            beta = _get_beta(betas, revenue_factor)
            f_curr = factor_series.get(year)
            f_prev = factor_series.get(year - 1)
            if f_curr and f_prev and f_prev > 0:
                alpha_val = betas.get("rev_alpha", {})
                if isinstance(alpha_val, dict):
                    alpha_val = alpha_val.get(-1, 0.0)
                alpha_val = 0.0 if alpha_val is None else float(alpha_val)
                d_rev = alpha_val + beta * math.log(f_curr / f_prev)
                state.revenue = prev.revenue * math.exp(d_rev)
                return state

    # 4. EWA with clamp
    rev_series = {y: historic.is_data.get(y, {}).get("revenue", 0)
                  for y in historic.years
                  if historic.is_data.get(y, {}).get("revenue", 0) > 0}
    if len(rev_series) >= 2:
        from ..revenue_models import ewa_with_clamp
        fc = ewa_with_clamp(rev_series, [year], halflife=5.0)
        if fc.get(year):
            state.revenue = fc[year]
            return state

    # 5. Fallback
    state.revenue = prev.revenue * 1.02
    return state


def _get_revenue_factor(company_id: str):
    """Read revenue macro_factor from project.yaml (one-time per run)."""
    try:
        import yaml
        from engine import ROOT
        cfg_path = ROOT / "companies" / company_id / "configs" / "project.yaml"
        if cfg_path.exists():
            with open(cfg_path) as f:
                raw = yaml.safe_load(f) or {}
            mode = raw.get("model", {}).get("mode", "standard")
            rev_cfg = raw.get("model", {}).get(mode, {}).get("revenue", {})
            return rev_cfg.get("macro_factor") or \
                   (rev_cfg.get("macro_factors") or [None])[0]
    except Exception:
        pass
    return None


def _get_beta(betas: dict, factor_name: str) -> float:
    """Get OLS beta for a macro factor from preprocessor results."""
    beta = betas.get(f"rev_beta_{factor_name}")
    if isinstance(beta, dict):
        beta = beta.get(-1)
    if beta is None:
        best = betas.get("rev_best_beta")
        if isinstance(best, dict):
            best = best.get(-1)
        beta = float(best) if best is not None else 1.0
    return float(beta) if beta else 1.0
