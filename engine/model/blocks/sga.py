"""SGA forecast block: Revenue × sga_pct × (1 + CPI uplift).

If sga_split_enabled: breaks SGA into distribution, admin, ECL, other_opex.
Total SGA is unchanged — split is IS detail only, zero BS impact.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from engine.constants import SGA_PCT_MIN, SGA_PCT_MAX, SGA_CPI_UPLIFT_MAX, SGA_HIST_CLAMP_LOW, SGA_HIST_CLAMP_HIGH

if TYPE_CHECKING:
    from ..inputs import YearState, HistoricState, ModelConfig

def solve_sga(state, prev, historic, config):
    # type: (YearState, YearState, HistoricState, ModelConfig) -> YearState
    sga_pct = config.sga_pct
    if not sga_pct:
        pp_mr = historic.preprocess.get('margin_ratios', {})
        rec = pp_mr.get('opex_ratio_recommended')
        if isinstance(rec, dict): rec = rec.get(-1)
        if not rec:
            rec = pp_mr.get('sga_ratio_recommended')
            if isinstance(rec, dict): rec = rec.get(-1)
        if not rec:
            rec = pp_mr.get('sga_ratio_last')
            if isinstance(rec, dict): rec = rec.get(-1)
        if rec: sga_pct = float(rec)
        else:
            hist_sga_raw = pp_mr.get('sga_ratio', {})
            hist_vals_raw = [v for k, v in (hist_sga_raw.items() if isinstance(hist_sga_raw, dict) else [])
                             if isinstance(k, int) and k > 0 and v is not None]
            sga_pct = sorted(hist_vals_raw)[len(hist_vals_raw)//2] if hist_vals_raw else 0.05

    cpi_beta = historic.preprocess.get("beta_coefficients", {}).get("cpi_beta")
    if cpi_beta is not None and cpi_beta > 0:
        cpi_series = historic.macro_forecasts.get("cpi_us", {})
        cpi_curr = cpi_series.get(state.year)
        cpi_prev = cpi_series.get(state.year - 1)
        if cpi_curr and cpi_prev and cpi_prev > 0:
            cpi_growth = (cpi_curr / cpi_prev) - 1.0
            beta_clamped = min(cpi_beta, 1.0)
            uplift = cpi_growth * beta_clamped
            uplift = max(-SGA_CPI_UPLIFT_MAX, min(SGA_CPI_UPLIFT_MAX, uplift))
            sga_pct = sga_pct * (1.0 + uplift)

    hist_sga = historic.preprocess.get("margin_ratios", {}).get("opex_ratio") or \
               historic.preprocess.get("margin_ratios", {}).get("sga_ratio", {})
    if isinstance(hist_sga, dict):
        hist_vals = [v for k, v in hist_sga.items() if isinstance(k, int) and k > 0 and v is not None]
        if hist_vals:
            sga_pct = max(min(hist_vals)*SGA_HIST_CLAMP_LOW, min(max(hist_vals)*SGA_HIST_CLAMP_HIGH, sga_pct))
    else:
        sga_pct = max(SGA_PCT_MIN, min(SGA_PCT_MAX, sga_pct))

    total_sga = abs(state.revenue * sga_pct)
    state.sga = -total_sga

    # SGA split: populate sub-lines (IS detail, zero BS impact)
    if getattr(config, 'sga_split_enabled', False):
        # Priority: YAML config → preprocessor EWA → 0
        pp_mr = historic.preprocess.get('margin_ratios', {})
        def _get_ratio(yaml_val, pp_key):
            if yaml_val:
                return yaml_val
            pp = pp_mr.get(pp_key)
            if isinstance(pp, dict):
                return pp.get('_ewa') or pp.get(-1) or 0.0
            return float(pp) if pp else 0.0

        dist_pct = _get_ratio(config.sga_distribution_pct_rev, 'distribution_ratio')
        admin_pct = _get_ratio(config.sga_admin_pct_rev, 'admin_ratio')
        ecl_pct = _get_ratio(config.sga_ecl_pct_rev, 'ecl_ratio')
        other_pct = _get_ratio(config.sga_other_opex_pct_rev, 'other_opex_ratio')

        # Calculate sub-lines as % of revenue
        rev = abs(state.revenue)
        state.distribution_expenses = -rev * dist_pct
        state.admin_expenses = -rev * admin_pct
        state.ecl_expenses = -rev * ecl_pct
        state.other_opex = -rev * other_pct

        # Reconcile: ensure sub-lines sum to total SGA
        sub_total = abs(state.distribution_expenses) + abs(state.admin_expenses) + \
                    abs(state.ecl_expenses) + abs(state.other_opex)
        if sub_total > 0 and abs(sub_total - total_sga) > 1.0:
            # Scale proportionally to match total SGA
            scale = total_sga / sub_total
            state.distribution_expenses *= scale
            state.admin_expenses *= scale
            state.ecl_expenses *= scale
            state.other_opex *= scale

    return state
