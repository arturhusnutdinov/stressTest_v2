"""SGA forecast block: Revenue × sga_pct × (1 + CPI uplift).

If sga_split_enabled: splits total SGA into distribution, admin, ECL, other_opex
using share-of-total composition (not independent % of revenue).
This ensures sub-lines always sum to total SGA exactly.
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

    # SGA split: use share-of-total composition (не independent % от revenue)
    # Доля каждой подстатьи в итоговом OpEx — берём из preprocessor *_share_of_opex
    # Это гарантирует что sub-lines ВСЕГДА суммируются в total SGA
    if getattr(config, 'sga_split_enabled', False):
        pp_mr = historic.preprocess.get('margin_ratios', {})

        def _get_share(yaml_pct_rev, pp_share_key, pp_ratio_key):
            """Get share of total. YAML pct_rev → convert to share; else use preprocessor share."""
            # If YAML provides explicit % of revenue, convert to share
            if yaml_pct_rev and sga_pct > 0:
                return yaml_pct_rev / sga_pct
            # Else use preprocessor share-of-opex EWA
            pp = pp_mr.get(pp_share_key)
            if isinstance(pp, dict):
                v = pp.get('_ewa') or pp.get(-1)
                if v:
                    return float(v)
            # Last resort: derive from ratio / opex_ratio
            pp_r = pp_mr.get(pp_ratio_key)
            pp_total = pp_mr.get('opex_ratio')
            if isinstance(pp_r, dict) and isinstance(pp_total, dict):
                r_ewa = pp_r.get('_ewa') or pp_r.get(-1)
                t_ewa = pp_total.get('_ewa') or pp_total.get(-1)
                if r_ewa and t_ewa and t_ewa > 0:
                    return float(r_ewa) / float(t_ewa)
            return 0.0

        dist_share = _get_share(config.sga_distribution_pct_rev,
                                'distribution_share_of_opex', 'distribution_ratio')
        admin_share = _get_share(config.sga_admin_pct_rev,
                                 'admin_share_of_opex', 'admin_ratio')
        ecl_share = _get_share(config.sga_ecl_pct_rev,
                               'ecl_share_of_opex', 'ecl_ratio')
        other_share = _get_share(config.sga_other_opex_pct_rev,
                                 'other_opex_share_of_opex', 'other_opex_ratio')

        # Normalize shares to sum to 1.0
        share_sum = dist_share + admin_share + ecl_share + other_share
        if share_sum > 0:
            dist_share /= share_sum
            admin_share /= share_sum
            ecl_share /= share_sum
            other_share /= share_sum
        else:
            # Fallback: all in admin
            admin_share = 1.0

        # Apply shares to total SGA — guaranteed to sum exactly
        state.distribution_expenses = -total_sga * dist_share
        state.admin_expenses = -total_sga * admin_share
        state.ecl_expenses = -total_sga * ecl_share
        state.other_opex = -total_sga * other_share

    return state
