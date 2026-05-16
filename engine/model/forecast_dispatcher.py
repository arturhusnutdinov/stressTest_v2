"""
ForecastDispatcher — диспетчер методов прогнозирования.

Применяет ForecastMethod из YAML к конкретной статье IS/BS/CF.
Вызывается из core.py для статей где метод явно задан в forecast_methods.

Приоритет:
1. forecast_methods в YAML → ForecastDispatcher
2. use_* флаги (corkscrew/days/etc.) → существующие блоки в core.py
3. Дефолтная логика core.py

Это позволяет постепенно мигрировать статьи на новую систему
без полной переписки core.py.
"""
from __future__ import annotations

import math
import logging
from typing import TYPE_CHECKING, Optional, Dict, Any

if TYPE_CHECKING:
    from .inputs import YearState, HistoricState, ModelConfig, ForecastMethodConfig

logger = logging.getLogger(__name__)


class ForecastDispatcher:
    """
    Применяет ForecastMethod к одной статье для одного года.

    Использование в core.py:
        dispatcher = ForecastDispatcher(historic, config)

        # В _solve_other_is:
        val = dispatcher.apply('is', 'earnings_from_investees', state, prev)
        if val is not None:
            state.earnings_from_investees = val
    """

    def __init__(self, historic, config):
        self._h = historic
        self._c = config

    def apply(
        self,
        statement: str,   # 'is' | 'bs' | 'cf'
        metric: str,
        state,            # YearState текущий
        prev,             # YearState предыдущий
    ) -> Optional[float]:
        """
        Применяет метод прогнозирования для статьи.

        Returns:
            float если метод задан и применён
            None  если метод не задан → caller использует дефолтную логику
        """
        fm = self._c.get_forecast_method(statement, metric)
        if fm is None:
            return None

        from .inputs import ForecastMethod
        method = fm.method

        try:
            sign = getattr(fm, 'sign', 1.0) or 1.0

            if method == ForecastMethod.EWA:
                val = self._apply_ewa(metric, statement, fm, state, prev)
            elif method == ForecastMethod.LAST:
                val = self._apply_last(metric, statement, prev)
            elif method == ForecastMethod.ZERO:
                return 0.0
            elif method == ForecastMethod.DRIVER:
                val = self._apply_driver(metric, fm, state, prev)
            elif method == ForecastMethod.MACRO:
                val = self._apply_macro(metric, fm, state, prev)
            elif method == ForecastMethod.CORK:
                return None  # Cork обрабатывается отдельными блоками в core.py
            elif method == ForecastMethod.PLUG:
                return None  # Plug обрабатывается в _solve_cash_plug
            elif method == ForecastMethod.CALC:
                val = self._apply_calc(metric, fm, state)
            elif method == ForecastMethod.LINK:
                val = self._apply_link(fm, state)
            elif method == ForecastMethod.DAYS:
                return None  # Days обрабатывается в WCBlock
            else:
                logger.debug(f"  ForecastDispatcher: неизвестный метод {method} для {metric}")
                return None

            return val * sign if val is not None else None
        except Exception as e:
            logger.debug(f"  ForecastDispatcher: ошибка {metric}/{method}: {e}")
            return None

    # ── EWA ──────────────────────────────────────────────────────────────────

    def _apply_ewa(self, metric: str, statement: str, fm, state, prev) -> Optional[float]:
        """EWA от исторических значений."""
        halflife = getattr(fm, 'ewa_halflife_years', None) or 3.0

        # Получаем исторический ряд
        hist = self._get_history(statement, metric)
        if not hist or len(hist) < 2:
            # Fallback: carry с decay
            prev_val = self._get_prev_val(metric, prev)
            if prev_val is not None:
                return prev_val * 0.97  # лёгкий decay
            return None

        # EWA по истории
        alpha = 1.0 - math.exp(-math.log(2) / halflife)
        vals = [hist[y] for y in sorted(hist.keys())]
        ewa = vals[0]
        for v in vals[1:]:
            ewa = alpha * v + (1 - alpha) * ewa

        return ewa

    # ── LAST ─────────────────────────────────────────────────────────────────

    def _apply_last(self, metric: str, statement: str, prev) -> Optional[float]:
        """Carry forward последнего значения."""
        prev_val = self._get_prev_val(metric, prev)
        if prev_val is not None:
            return prev_val

        # Из истории — последний год
        hist = self._get_history(statement, metric)
        if hist:
            return hist[max(hist.keys())]
        return None

    # ── DRIVER ───────────────────────────────────────────────────────────────

    def _apply_driver(self, metric: str, fm, state, prev) -> Optional[float]:
        """% от базовой статьи."""
        driver_base = getattr(fm, 'driver_base', 'revenue') or 'revenue'
        driver_ratio = getattr(fm, 'driver_ratio', None)

        # Получаем базовое значение
        base_val = getattr(state, driver_base, None)
        if base_val is None or base_val == 0:
            return None

        # Ratio из конфига или из препроцессора
        ratio = None
        if driver_ratio and driver_ratio != 'history':
            try:
                ratio = float(driver_ratio)
            except (TypeError, ValueError):
                pass

        if ratio is None:
            # Из препроцессора: ищем {metric}_ratio или {metric}_pct
            for pp_group in self._h.preprocess.values():
                if not isinstance(pp_group, dict):
                    continue
                for key in [f"{metric}_ratio", f"{metric}_pct",
                            f"{metric}_to_{driver_base}"]:
                    val = pp_group.get(f"{key}_recommended")
                    if isinstance(val, dict):
                        val = val.get(-1)
                    if val is not None:
                        ratio = float(val)
                        break
                if ratio is not None:
                    break

        if ratio is None:
            # Вычисляем из истории
            hist_m = self._get_history('is', metric) or self._get_history('bs', metric)
            hist_b = self._get_history('is', driver_base) or self._get_history('bs', driver_base)
            if hist_m and hist_b:
                common = set(hist_m) & set(hist_b)
                if common:
                    ratios = [hist_m[y] / hist_b[y] for y in common
                              if hist_b[y] and abs(hist_b[y]) > 1e-6]
                    if ratios:
                        ratio = sum(ratios) / len(ratios)

        if ratio is None:
            return None

        return base_val * ratio

    # ── MACRO ─────────────────────────────────────────────────────────────────

    def _apply_macro(self, metric: str, fm, state, prev) -> Optional[float]:
        """OLS/EWA на макро-факторы (для Revenue — уже реализовано в _solve_revenue)."""
        macro_factors = getattr(fm, 'macro_factors', []) or []

        if not macro_factors:
            return None

        # Берём первый фактор и применяем chain-link
        factor_name = macro_factors[0]
        fc_series = self._h.macro_forecasts.get(factor_name, {})

        if not fc_series:
            return None

        f_curr = fc_series.get(state.year)
        f_prev = fc_series.get(state.year - 1)
        prev_val = self._get_prev_val(metric, prev)

        if f_curr and f_prev and f_prev > 0 and prev_val:
            growth = math.log(f_curr / f_prev)
            beta = 1.0  # дефолт
            return prev_val * math.exp(beta * growth)

        return None

    # ── CALC ──────────────────────────────────────────────────────────────────

    def _apply_calc(self, metric: str, fm, state) -> Optional[float]:
        """Вычисляемая статья по формуле."""
        formula = getattr(fm, 'calc_formula', None)
        if not formula:
            return None

        try:
            context = {k: v for k, v in state.__dict__.items()
                       if isinstance(v, (int, float))}
            result = eval(formula, {"__builtins__": {}}, context)
            return float(result)
        except Exception as e:
            logger.debug(f"  CALC {metric}: ошибка формулы '{formula}': {e}")
            return None

    # ── LINK ──────────────────────────────────────────────────────────────────

    def _apply_link(self, fm, state) -> Optional[float]:
        """Связь с другим отчётом."""
        link_field = getattr(fm, 'link_field', None)
        if not link_field:
            return None
        return getattr(state, link_field, None)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_history(self, statement: str, metric: str) -> Dict[int, float]:
        """Получает исторический ряд метрики."""
        if statement == 'is':
            return {y: d.get(metric, 0) for y, d in self._h.is_data.items()
                    if d.get(metric) is not None}
        elif statement == 'bs':
            return {y: d.get(metric, 0) for y, d in self._h.bs_data.items()
                    if d.get(metric) is not None}
        elif statement == 'cf':
            return {y: d.get(metric, 0) for y, d in self._h.cf_data.items()
                    if d.get(metric) is not None}
        return {}

    def _get_prev_val(self, metric: str, prev) -> Optional[float]:
        """Получает предыдущее значение метрики из YearState."""
        return getattr(prev, metric, None)
