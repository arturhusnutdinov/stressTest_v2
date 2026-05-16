"""
Component-based COGS for commodity producers.

COGS = alumina_cost + energy_cost + labour_cost + other_cost

Where:
  alumina_cost = production_kt × 1000 × alumina_intensity × lme_alumina_price
  energy_cost  = production_kt × 1000 × energy_kwh_per_t × power_price_rub / usd_rub
  labour_cost  = prev_labour × (1 + cpi_growth)
  other_cost   = prev_other × (1 + ppi_growth)
"""
from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CogsBlockConfig:
    """Component cost parameters from YAML / preprocessor."""
    # Cost component shares of total COGS (for base year breakdown)
    alumina_share: float = 0.37
    energy_share: float = 0.27
    labour_share: float = 0.12
    other_share: float = 0.24

    # Alumina: tonnes alumina per tonne Al (industry: ~1.93) — from YAML
    alumina_intensity: float = 1.93
    # Energy: kWh per tonne Al (Rusal: ~15,500) — from YAML
    energy_kwh_per_t: float = 15500.0
    # Mean-reversion dampening: fraction of macro deviation that passes through
    mean_reversion_dampening: float = 0.30
    # Clamp: max deviation from anchor (±sigma)
    clamp_sigma: float = 0.06

    # Base year values (computed from base_cogs × shares)
    base_year: int = 2025
    base_cogs: float = 0.0
    base_revenue: float = 0.0
    base_production_kt: float = 0.0
    # Preprocessor-calibrated COGS ratio (EWA, more stable than single-year)
    cogs_ratio_anchor: float = 0.0  # 0 = use base_cogs/base_revenue


class CogsBlock:
    """
    Compute COGS from macro-linked components.

    Usage:
        cfg = CogsBlockConfig(base_cogs=9.26e9, base_production_kt=3992)
        block = CogsBlock(cfg, macro_forecasts)
        cogs_2026 = block.compute(2026, production_kt=4000)
    """

    def __init__(
        self,
        config: CogsBlockConfig,
        macro_forecasts: Dict[str, Dict[int, float]],
        macro_history: Dict[str, Dict[int, float]] = None,
    ):
        self.cfg = config
        self.macro = macro_forecasts
        self.hist = macro_history or {}

        # Base year revenue (for ratio computation)
        self._base_revenue = config.base_revenue

        # Base year component costs
        base = config.base_cogs
        self._alumina_base = base * config.alumina_share
        self._energy_base = base * config.energy_share
        self._labour_base = base * config.labour_share
        self._other_base = base * config.other_share

        # Base year macro values (for indexing) — always from HISTORY, not forecasts
        # This ensures stress shocks to forecasts produce non-zero deltas
        by = config.base_year
        def _base(factor):
            return (self.hist.get(factor) or {}).get(by) or self._get_macro(factor, by)
        self._lme_alumina_base = _base('lme_alumina')
        self._power_base = _base('russian_power_price')
        self._usdrub_base = _base('usd_rub') or _base('fx_usdrub')
        self._cpi_ru_base = _base('cpi_ru')
        self._ppi_ru_base = _base('ppi_ru')

    def _get_macro(self, factor: str, year: int) -> float:
        """Get macro value from forecasts or history."""
        v = (self.macro.get(factor) or {}).get(year)
        if v: return v
        v = (self.hist.get(factor) or {}).get(year)
        return v or 0.0

    def compute(self, year: int, production_kt: float = 0.0,
                revenue: float = 0.0) -> float:
        """
        Compute total COGS for given year.

        Returns COGS as a positive number (caller applies negative sign).
        If revenue is provided, scales result to maintain reasonable COGS/Revenue ratio.
        """
        if self.cfg.base_cogs <= 0:
            return 0.0

        # Production volume: use forecast or EWA from base
        prod_kt = production_kt or self.cfg.base_production_kt

        # 1. Alumina: indexed to LME Alumina
        lme_alm = self._get_macro('lme_alumina', year)
        if lme_alm > 0 and self._lme_alumina_base > 0:
            alumina_index = lme_alm / self._lme_alumina_base
        else:
            alumina_index = 1.0
        # Volume adjustment
        vol_adj = prod_kt / self.cfg.base_production_kt if self.cfg.base_production_kt > 0 else 1.0
        alumina_cost = self._alumina_base * alumina_index * vol_adj

        # 2. Energy: indexed to power_price / usd_rub
        power = self._get_macro('russian_power_price', year)
        usdrub = self._get_macro('usd_rub', year) or self._get_macro('fx_usdrub', year)
        if power > 0 and self._power_base > 0:
            power_index = power / self._power_base
        else:
            power_index = 1.0
        if usdrub > 0 and self._usdrub_base > 0:
            fx_index = self._usdrub_base / usdrub  # RUB depreciation → cheaper in USD
        else:
            fx_index = 1.0
        energy_cost = self._energy_base * power_index * fx_index * vol_adj

        # 3. Labour: indexed to CPI Russia
        cpi = self._get_macro('cpi_ru', year)
        if cpi > 0 and self._cpi_ru_base > 0:
            cpi_index = cpi / self._cpi_ru_base
        else:
            cpi_index = 1.0
        labour_cost = self._labour_base * cpi_index * fx_index * vol_adj

        # 4. Other: indexed to PPI Russia
        ppi = self._get_macro('ppi_ru', year)
        if ppi > 0 and self._ppi_ru_base > 0:
            ppi_index = ppi / self._ppi_ru_base
        else:
            ppi_index = 1.0
        other_cost = self._other_base * ppi_index * vol_adj

        total = alumina_cost + energy_cost + labour_cost + other_cost

        # Revenue-relative scaling with MEAN-REVERSION.
        # For commodity producers: COGS% is historically stable (beta ≈ 0 to LME).
        # Macro factors cause short-term deviations that revert to EWA anchor.
        if revenue > 0 and self.cfg.base_cogs > 0:
            anchor = self.cfg.cogs_ratio_anchor if self.cfg.cogs_ratio_anchor > 0 else \
                     (self.cfg.base_cogs / self._base_revenue if self._base_revenue > 0 else 0.75)

            # Macro effect: how much components deviated from base (as ratio)
            macro_deviation = (total / self.cfg.base_cogs) - 1.0  # e.g. +0.04 = costs up 4%

            # Mean-reversion: only a fraction of macro deviation passes through
            dampening = self.cfg.mean_reversion_dampening
            cogs_ratio = anchor * (1.0 + macro_deviation * dampening)

            # Clamp to historical ±σ range (configurable via YAML)
            sigma = self.cfg.clamp_sigma
            cogs_ratio = max(anchor - sigma, min(anchor + sigma, cogs_ratio))
            total = revenue * cogs_ratio
        else:
            total = max(self.cfg.base_cogs * 0.5, min(self.cfg.base_cogs * 1.5, total))

        return total
