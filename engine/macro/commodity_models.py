"""
Модели прогнозирования цен на commodities.
Практика: Mean Reversion лучше EWA для цикличных рядов.
"""
from __future__ import annotations

import math
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def mean_reversion_forecast(
    history: Dict[int, float],
    forecast_years: int = 5,
    long_run_mean: Optional[float] = None,
    kappa: float = 0.3,
    use_log: bool = True,
) -> Dict[int, float]:
    """
    Ornstein-Uhlenbeck Mean Reversion.

    Формула (дискретная):
    P(t+1) = P(t) + kappa × (mu - P(t))

    В log-пространстве:
    ln P(t+1) = ln P(t) + kappa × (ln mu - ln P(t))

    Args:
        history:        {year: value} исторический ряд
        forecast_years: горизонт прогноза
        long_run_mean:  долгосрочное равновесие (если None → медиана истории)
        kappa:          скорость возврата (0.1=медленно, 0.5=быстро)
                        для стали ~0.3 (возврат ~3-4 года)
        use_log:        работать в log-пространстве (стабильнее)

    Returns:
        {year: value} прогноз
    """
    if not history or len(history) < 2:
        return {}

    sorted_years = sorted(history.keys())
    last_year  = sorted_years[-1]
    last_value = history[last_year]
    values     = [history[y] for y in sorted_years]

    # Долгосрочное равновесие = медиана истории (устойчива к outlier)
    if long_run_mean is None:
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        if n % 2 == 0:
            long_run_mean = (sorted_vals[n//2-1] + sorted_vals[n//2]) / 2
        else:
            long_run_mean = sorted_vals[n//2]

    logger.debug(f"Mean reversion: last={last_value:.1f} mu={long_run_mean:.1f} kappa={kappa}")

    forecast = {}
    if use_log and last_value > 0 and long_run_mean > 0:
        ln_mu   = math.log(long_run_mean)
        ln_curr = math.log(last_value)
        for i in range(1, forecast_years + 1):
            ln_next = ln_curr + kappa * (ln_mu - ln_curr)
            forecast[last_year + i] = math.exp(ln_next)
            ln_curr = ln_next
    else:
        curr = last_value
        for i in range(1, forecast_years + 1):
            nxt = curr + kappa * (long_run_mean - curr)
            forecast[last_year + i] = max(nxt, 0.0)
            curr = nxt

    return forecast


def rw_drift_clamped(
    history: Dict[int, float],
    forecast_years: int = 5,
    ewa_halflife: float = 5.0,
    percentile_lo: float = 0.10,
    percentile_hi: float = 0.90,
) -> Dict[int, float]:
    """
    Random Walk с EWA-дрейфом + clamp в исторический диапазон [P10, P90].

    Используется как fallback когда mean reversion не подходит.
    Clamp не даёт прогнозу уйти за исторические экстремумы.
    """
    if not history or len(history) < 2:
        return {}

    sorted_years = sorted(history.keys())
    values = [history[y] for y in sorted_years]
    last_year  = sorted_years[-1]
    last_value = values[-1]

    # EWA темп роста
    alpha = 1.0 - math.exp(-math.log(2) / ewa_halflife)
    growth_rates = []
    for i in range(1, len(values)):
        if values[i-1] > 0:
            growth_rates.append(math.log(values[i] / values[i-1]))

    if not growth_rates:
        return {}

    ewa_growth = growth_rates[0]
    for g in growth_rates[1:]:
        ewa_growth = alpha * g + (1 - alpha) * ewa_growth

    # Исторический диапазон [P10, P90]
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    lo = sorted_vals[max(0, int(n * percentile_lo))]
    hi = sorted_vals[min(n-1, int(n * percentile_hi))]

    forecast = {}
    curr = last_value
    for i in range(1, forecast_years + 1):
        nxt = curr * math.exp(ewa_growth)
        nxt = max(lo, min(hi, nxt))  # clamp
        forecast[last_year + i] = nxt
        curr = nxt

    return forecast


def select_best_forecast(
    history: Dict[int, float],
    method: str = "mean_reversion",
    forecast_years: int = 5,
    **kwargs,
) -> Dict[int, float]:
    """
    Диспетчер моделей прогнозирования.

    Args:
        method: mean_reversion | rw_drift | ewa
        **kwargs: параметры для выбранной модели
    """
    if method == "mean_reversion":
        return mean_reversion_forecast(history, forecast_years, **kwargs)
    elif method == "rw_drift":
        return rw_drift_clamped(history, forecast_years, **kwargs)
    elif method == "ewa":
        return _ewa_forecast_local(history, forecast_years,
                                   halflife=kwargs.get("halflife", 3.0))
    else:
        logger.warning(f"Неизвестный метод: {method}, используем mean_reversion")
        return mean_reversion_forecast(history, forecast_years)


def _ewa_forecast_local(
    history: Dict[int, float],
    forecast_years: int = 5,
    halflife: float = 3.0,
) -> Dict[int, float]:
    """EWA прогноз темпа роста. Используется как fallback для макро-факторов."""
    if not history or len(history) < 2:
        return {}

    sorted_years = sorted(history.keys())
    values = [history[y] for y in sorted_years]

    growth_rates = []
    for i in range(1, len(values)):
        if values[i - 1] and abs(values[i - 1]) > 1e-9:
            growth_rates.append(values[i] / values[i - 1] - 1)

    if not growth_rates:
        return {}

    alpha = 1.0 - math.exp(-math.log(2) / halflife)
    ewa_growth = growth_rates[0]
    for g in growth_rates[1:]:
        ewa_growth = alpha * g + (1 - alpha) * ewa_growth

    last_year = sorted_years[-1]
    last_value = values[-1]
    forecast: Dict[int, float] = {}
    val = last_value
    for yr in range(last_year + 1, last_year + forecast_years + 1):
        val = val * (1 + ewa_growth)
        forecast[yr] = val

    return forecast
