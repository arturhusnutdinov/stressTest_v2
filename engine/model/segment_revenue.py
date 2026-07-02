"""
Сегментное моделирование Revenue.

Revenue = Σ_i (Volume_i × Price_i)

Где:
- Volume_i — объём продаж сегмента i (тонны, единицы и т.д.)
- Price_i  — средняя цена реализации сегмента i

Методы прогноза:
- Volume: ewa | macro (регрессия на macro-факторы типа industrial_production)
- Price:  ewa | macro (регрессия на HRC, commodity prices)

Конфигурация в project.yaml:
    model:
      custom:
        revenue:
          segment_modeling: true
          segments:
            flat_rolled:
              volume_history: {2022: 14.5, 2023: 12.8, 2024: 13.1}  # млн тонн
              price_history:  {2022: 1100, 2023: 900, 2024: 950}    # $/тонна
              volume_method: ewa
              price_method: macro
              price_factors: [steel_price_hrc]
            mini_mill:
              volume_history: {2022: 3.0, 2023: 3.5, 2024: 4.0}
              price_history:  {2022: 1050, 2023: 850, 2024: 900}
              volume_method: ewa
              price_method: macro
              price_factors: [steel_price_hrc]
"""
from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Optional,  Dict, List, Optional

from engine.constants import REVENUE_CLAMP_PERCENTILE_LOW, REVENUE_CLAMP_PERCENTILE_HIGH

logger = logging.getLogger(__name__)


@dataclass
class SegmentConfig:
    """Конфигурация одного сегмента."""
    name: str
    volume_history: Dict[int, float]  # {year: volume}
    price_history:  Dict[int, float]  # {year: price}
    volume_method:  str = "ewa"       # ewa | macro | fixed_growth
    price_method:   str = "macro"     # ewa | macro | fixed_growth
    price_factors:  List[str] = field(default_factory=list)
    volume_factors: List[str] = field(default_factory=list)
    volume_growth:  Optional[float] = None  # фиксированный рост объёма (%/год)
    price_growth:   Optional[float] = None  # фиксированный рост цены (%/год)
    ewa_halflife:   float = 3.0

    @classmethod
    def from_dict(cls, name: str, cfg: dict) -> "SegmentConfig":
        return cls(
            name=name,
            volume_history={int(k): float(v) for k, v in cfg.get("volume_history", {}).items()},
            price_history ={int(k): float(v) for k, v in cfg.get("price_history",  {}).items()},
            volume_method =cfg.get("volume_method", "ewa"),
            price_method  =cfg.get("price_method",  "macro"),
            price_factors =cfg.get("price_factors", []),
            volume_factors=cfg.get("volume_factors", []),
            volume_growth =cfg.get("volume_growth"),
            price_growth  =cfg.get("price_growth"),
            ewa_halflife  =float(cfg.get("ewa_halflife", 3.0)),
        )


@dataclass
class SegmentForecast:
    """Результат прогноза одного сегмента."""
    name: str
    volume: Dict[int, float]   # {year: volume}
    price:  Dict[int, float]   # {year: price}
    revenue: Dict[int, float]  # {year: volume × price}


class SegmentRevenueModel:
    """
    Сегментная модель Revenue.

    Использование:
        model = SegmentRevenueModel(segments_config, macro_forecasts)
        forecasts = model.forecast(forecast_years=[2025, 2026, 2027, 2028, 2029])
        total_revenue = model.total_revenue(forecasts)
    """

    def __init__(
        self,
        segments: List[SegmentConfig],
        macro_forecasts: Dict[str, Dict[int, float]],
        macro_history: Dict[str, Dict[int, float]] = None,
    ):
        self.segments = segments
        self.macro_forecasts = macro_forecasts
        self.macro_history = macro_history or {}

    @classmethod
    def from_yaml_config(
        cls,
        revenue_cfg: dict,
        macro_forecasts: Dict[str, Dict[int, float]],
    ) -> Optional["SegmentRevenueModel"]:
        """Создаёт модель из секции model.{mode}.revenue YAML."""
        if not revenue_cfg.get("segment_modeling", False):
            return None

        segments_cfg = revenue_cfg.get("segments", {})
        if not segments_cfg:
            logger.warning("segment_modeling=true но segments не заданы")
            return None

        segments = []
        for seg_name, seg_cfg in segments_cfg.items():
            seg = SegmentConfig.from_dict(seg_name, seg_cfg)
            segments.append(seg)
            logger.info(f"  Сегмент: {seg_name} ({len(seg.volume_history)} лет истории)")

        return cls(segments, macro_forecasts)

    def forecast(self, forecast_years: List[int]) -> List[SegmentForecast]:
        """Прогнозирует каждый сегмент."""
        results = []
        for seg in self.segments:
            vol_fc = self._forecast_series(
                seg.volume_history, forecast_years,
                method=seg.volume_method,
                factors=seg.volume_factors,
                fixed_growth=seg.volume_growth,
                halflife=seg.ewa_halflife,
            )
            price_fc = self._forecast_series(
                seg.price_history, forecast_years,
                method=seg.price_method,
                factors=seg.price_factors,
                fixed_growth=seg.price_growth,
                halflife=seg.ewa_halflife,
            )
            rev_fc = {yr: vol_fc.get(yr, 0) * price_fc.get(yr, 0)
                      for yr in forecast_years}

            sf = SegmentForecast(
                name=seg.name,
                volume=vol_fc,
                price=price_fc,
                revenue=rev_fc,
            )
            results.append(sf)
            logger.info(
                f"  {seg.name}: vol={[round(v, 2) for v in list(vol_fc.values())[:2]]} "
                f"price={[round(v, 0) for v in list(price_fc.values())[:2]]} "
                f"rev={[round(v/1e9, 2) for v in list(rev_fc.values())[:2]]}B"
            )

        return results

    def total_revenue(self, forecasts: List[SegmentForecast]) -> Dict[int, float]:
        """Суммирует Revenue по всем сегментам."""
        total: Dict[int, float] = {}
        for sf in forecasts:
            for yr, rev in sf.revenue.items():
                total[yr] = total.get(yr, 0.0) + rev
        return total

    # ── Внутренние методы прогнозирования ────────────────────────────────────

    def _forecast_series(
        self,
        history: Dict[int, float],
        forecast_years: List[int],
        method: str,
        factors: List[str],
        fixed_growth: Optional[float],
        halflife: float,
    ) -> Dict[int, float]:
        """Прогнозирует один ряд (volume или price)."""
        if not history:
            return {}

        if method == "fixed_growth" and fixed_growth is not None:
            last_year  = max(history.keys())
            last_value = history[last_year]
            return {
                yr: last_value * ((1 + fixed_growth / 100) ** (yr - last_year))
                for yr in forecast_years
            }

        if method == "macro" and factors:
            factor_name = factors[0]
            macro_series = self.macro_forecasts.get(factor_name, {})
            if len(macro_series) >= 3 and len(history) >= 3:
                return self._ols_chainlink(history, macro_series, forecast_years)
            logger.debug(f"  macro fallback → ewa: {factor_name} недостаточно данных")

        # EWA (дефолт)
        return self._ewa_forecast(history, forecast_years, halflife)

    def _ewa_forecast(
        self,
        history: Dict[int, float],
        forecast_years: List[int],
        halflife: float,
    ) -> Dict[int, float]:
        """EWA темп роста + chain-link."""
        sorted_years = sorted(history.keys())
        values = [history[y] for y in sorted_years]
        last_value = values[-1]

        if len(values) < 2:
            return {yr: last_value for yr in forecast_years}

        alpha = 1.0 - math.exp(-math.log(2) / halflife)
        growth_rates = []
        for i in range(1, len(values)):
            if values[i-1] > 0:
                growth_rates.append(math.log(values[i] / values[i-1]))

        if not growth_rates:
            return {yr: last_value for yr in forecast_years}

        ewa_growth = growth_rates[0]
        for g in growth_rates[1:]:
            ewa_growth = alpha * g + (1 - alpha) * ewa_growth

        # Clamp growth to historical percentile range
        forecast_growth = ewa_growth
        if len(growth_rates) >= 3:
            import numpy as np
            g_lo = float(np.percentile(growth_rates, REVENUE_CLAMP_PERCENTILE_LOW * 100))
            g_hi = float(np.percentile(growth_rates, REVENUE_CLAMP_PERCENTILE_HIGH * 100))
            forecast_growth = max(g_lo, min(g_hi, forecast_growth))

        result = {}
        val = last_value
        for yr in sorted(forecast_years):
            val = val * math.exp(forecast_growth)
            result[yr] = val
        return result

    def _ols_chainlink(
        self,
        history: Dict[int, float],
        macro_series: Dict[int, float],
        forecast_years: List[int],
    ) -> Dict[int, float]:
        """OLS: dln(series) ~ dln(macro) + chain-link от последней истории."""
        common = sorted(set(history) & set(macro_series))
        if len(common) < 4:
            return self._ewa_forecast(history, forecast_years, 3.0)

        dy, dx = [], []
        for i in range(1, len(common)):
            y0, y1 = common[i-1], common[i]
            h0, h1 = history.get(y0, 0), history.get(y1, 0)
            m0, m1 = macro_series.get(y0, 0), macro_series.get(y1, 0)
            if h0 > 0 and h1 > 0 and m0 > 0 and m1 > 0:
                dy.append(math.log(h1 / h0))
                dx.append(math.log(m1 / m0))

        if not dx:
            return self._ewa_forecast(history, forecast_years, 3.0)

        n  = len(dx)
        mx = sum(dx) / n
        my = sum(dy) / n
        cov = sum((dx[i] - mx) * (dy[i] - my) for i in range(n))
        var = sum((dx[i] - mx) ** 2 for i in range(n))
        beta  = cov / var if var > 1e-12 else 0.0
        alpha = my - beta * mx

        last_hist_yr  = max(history.keys())
        last_hist_val = history[last_hist_yr]
        last_macro = macro_series.get(last_hist_yr) or macro_series[max(macro_series.keys())]

        result = {}
        cum_ln = 0.0
        prev_macro = last_macro
        for yr in sorted(forecast_years):
            curr_macro = macro_series.get(yr)
            if curr_macro and prev_macro and prev_macro > 0:
                d_macro = math.log(curr_macro / prev_macro)
                cum_ln += alpha + beta * d_macro
                prev_macro = curr_macro
            result[yr] = last_hist_val * math.exp(cum_ln)
        return result
