"""
Component-based COGS for commodity producers.

COGS = commodity_cost + energy_cost + labour_cost + other_cost

Where:
  commodity_cost = production_kt × commodity_index × volume_adj
  energy_cost    = base_energy × power_index × fx_index × volume_adj
  labour_cost    = base_labour × inflation_index × fx_index × volume_adj
  other_cost     = base_other × ppi_index × volume_adj

Macro factor names are configurable per company via YAML (defaults match RUSAL).
"""
from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Optional,  Dict, Optional

from engine.constants import COGS_CLAMP_MIN_FACTOR, COGS_CLAMP_MAX_FACTOR

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

    # Macro factor names (configurable per company via YAML)
    # commodity_factor: set to "none" for vertically integrated producers
    # where the primary raw material is self-produced (e.g. Rusal mines bauxite
    # → refines alumina internally). LME spot price does not drive internal cost.
    commodity_factor: str = "lme_alumina"      # Primary commodity index
    energy_factor: str = "russian_power_price"  # Energy cost factor
    fx_factor: str = "usd_rub"                 # FX rate factor
    inflation_factor: str = "cpi_ru"           # Labour cost inflation index
    ppi_factor: str = "ppi_ru"                 # Producer price index for other costs

    # Base year values (computed from base_cogs × shares)
    base_year: int = 2025
    base_cogs: float = 0.0
    base_revenue: float = 0.0
    base_production_kt: float = 0.0
    # Preprocessor-calibrated COGS ratio (EWA, more stable than single-year)
    cogs_ratio_anchor: float = 0.0  # 0 = use base_cogs/base_revenue


class CogsBlock:
    """
    Compute COGS from macro-linked components for any commodity producer.

    Macro factor names are configurable via CogsBlockConfig fields
    (commodity_factor, energy_factor, fx_factor, inflation_factor, ppi_factor).

    Usage:
        cfg = CogsBlockConfig(base_cogs=9.26e9, base_production_kt=3992,
                              commodity_factor='lme_nickel', fx_factor='usd_rub')
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
        # "none" = self-produced commodity, no LME indexation
        self._commodity_disabled = (config.commodity_factor.lower() == "none")
        self._commodity_base = 0.0 if self._commodity_disabled else _base(config.commodity_factor)
        self._power_base = _base(config.energy_factor)
        self._usdrub_base = _base(config.fx_factor) or _base('fx_' + config.fx_factor)
        self._cpi_base = _base(config.inflation_factor)
        self._ppi_base = _base(config.ppi_factor)

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

        # 1. Commodity: indexed to primary commodity factor
        # When commodity_factor="none" (vertically integrated, self-produced),
        # commodity cost grows only with volume and PPI, not LME spot.
        if self._commodity_disabled:
            commodity_index = 1.0
        else:
            commodity_val = self._get_macro(self.cfg.commodity_factor, year)
            if commodity_val > 0 and self._commodity_base > 0:
                commodity_index = commodity_val / self._commodity_base
            else:
                commodity_index = 1.0
        # Volume adjustment
        vol_adj = prod_kt / self.cfg.base_production_kt if self.cfg.base_production_kt > 0 else 1.0
        commodity_cost = self._alumina_base * commodity_index * vol_adj

        # 2. Energy: indexed to energy factor / FX
        power = self._get_macro(self.cfg.energy_factor, year)
        usdrub = self._get_macro(self.cfg.fx_factor, year) or self._get_macro('fx_' + self.cfg.fx_factor, year)
        if power > 0 and self._power_base > 0:
            power_index = power / self._power_base
        else:
            power_index = 1.0
        if usdrub > 0 and self._usdrub_base > 0:
            fx_index = self._usdrub_base / usdrub  # RUB depreciation → cheaper in USD
        else:
            fx_index = 1.0
        energy_cost = self._energy_base * power_index * fx_index * vol_adj

        # 3. Labour: indexed to inflation factor
        cpi = self._get_macro(self.cfg.inflation_factor, year)
        if cpi > 0 and self._cpi_base > 0:
            cpi_index = cpi / self._cpi_base
        else:
            cpi_index = 1.0
        labour_cost = self._labour_base * cpi_index * fx_index * vol_adj

        # 4. Other: indexed to PPI factor
        ppi = self._get_macro(self.cfg.ppi_factor, year)
        if ppi > 0 and self._ppi_base > 0:
            ppi_index = ppi / self._ppi_base
        else:
            ppi_index = 1.0
        other_cost = self._other_base * ppi_index * vol_adj

        total = commodity_cost + energy_cost + labour_cost + other_cost

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
            total = max(self.cfg.base_cogs * COGS_CLAMP_MIN_FACTOR,
                       min(self.cfg.base_cogs * COGS_CLAMP_MAX_FACTOR, total))

        return total
