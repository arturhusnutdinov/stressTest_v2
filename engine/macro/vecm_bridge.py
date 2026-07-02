"""
VECM Bridge — подключает математическое ядро engine/macro/vecm.py к новому Repository.

Архитектура:
  Repository (v2) → VecmBridge → engine/macro/vecm.py (математика) → Repository (v2)

IO-слой полностью заменён на MacroDBAdapter / Repository.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


def _check_dependencies() -> Dict[str, bool]:
    """Проверяем доступность зависимостей VECM."""
    deps = {}
    for pkg in ["statsmodels", "pandas", "numpy"]:
        try:
            __import__(pkg)
            deps[pkg] = True
        except ImportError:
            deps[pkg] = False
    try:
        import pmdarima
        deps["pmdarima"] = True
    except ImportError:
        deps["pmdarima"] = False
    return deps


def _load_factor_series(repo, factor_names: List[str]) -> Dict[str, Any]:
    """
    Загружает исторические ряды факторов из Repository.
    Возвращает {factor_name: pd.Series(index=year)}.
    """
    try:
        import pandas as pd
    except ImportError:
        return {}

    result = {}
    for name in factor_names:
        data = repo.get_macro_factor(name)
        if data and len(data) >= 5:
            s = pd.Series(data).sort_index()
            s.index = s.index.astype(int)
            result[name] = s
        else:
            logger.debug(f"  {name}: недостаточно данных ({len(data)} точек)")
    return result


def run_vecm_for_factors(
    repo,
    company_id: str,
    factor_names: List[str],
    scenario_id: int,
    forecast_years: int = 5,
    cfg: Optional[Dict] = None,
) -> Dict[str, Dict[int, float]]:
    """
    Запускает VECM/ARIMA прогноз для набора факторов.

    Алгоритм:
    1. Загружает исторические ряды из Repository
    2. Пытается запустить VECM через engine.macro.vecm._fit_vecm
    3. При неудаче → univariate fallback (_choose_univariate_fallback)
    4. Возвращает {factor_name: {year: value}}

    Args:
        repo:          Repository (v2)
        company_id:    ID компании
        factor_names:  список факторов для прогноза
        scenario_id:   ID сценария
        forecast_years: горизонт прогноза
        cfg:           конфиг из macro_ecm.yaml

    Returns:
        {factor_name: {year: value}} — прогнозы
    """
    # Set adapter for io.py and vecm.py to use
    from .db_adapter import MacroDBAdapter
    _adapter = MacroDBAdapter(repo, company_id, scenario_id)
    from . import io as _io_mod
    _io_mod.set_adapter(_adapter)
    from . import vecm as _vecm_mod
    _vecm_mod.set_db_adapter(_adapter)

    deps = _check_dependencies()
    if not deps.get("statsmodels") or not deps.get("pandas"):
        logger.warning("statsmodels/pandas недоступны — VECM невозможен")
        return {}

    import pandas as pd
    import numpy as np

    # Загружаем исторические ряды
    factor_series = _load_factor_series(repo, factor_names)
    if not factor_series:
        logger.warning("Нет данных для VECM")
        return {}

    logger.info(f"  VECM: {len(factor_series)} факторов загружено")

    # Находим общий временной диапазон
    common_years = None
    for s in factor_series.values():
        yrs = set(s.index)
        common_years = yrs if common_years is None else common_years & yrs
    if not common_years or len(common_years) < 8:
        logger.warning(f"Недостаточно общих лет: {len(common_years or set())}")
        return {}

    common_years = sorted(common_years)
    last_year = max(common_years)
    forecast_index = list(range(last_year + 1, last_year + forecast_years + 1))

    forecasts: Dict[str, Dict[int, float]] = {}

    # Попытка VECM (мультивариантная)
    if len(factor_series) >= 2:
        forecasts = _try_vecm(
            factor_series, common_years, forecast_index, cfg or {}
        )

    # Univariate fallback для факторов без прогноза
    missing = [f for f in factor_series if f not in forecasts]
    if missing:
        logger.info(f"  Univariate fallback для {len(missing)} факторов: {missing}")
        for factor_name in missing:
            s = factor_series[factor_name]
            fc = _univariate_forecast(s, forecast_index, cfg or {})
            if fc:
                forecasts[factor_name] = fc

    return forecasts


def _try_vecm(
    factor_series: Dict[str, Any],
    common_years: List[int],
    forecast_index: List[int],
    cfg: Dict,
) -> Dict[str, Dict[int, float]]:
    """Попытка VECM через engine.macro.vecm._fit_vecm."""
    try:
        import pandas as pd
        import numpy as np

        from engine.macro.vecm import _fit_vecm

        # Собираем матрицу в log-пространстве
        ln_data = {}
        for name, s in factor_series.items():
            s_common = s.loc[common_years].replace(0, np.nan).dropna()
            if len(s_common) >= 8:
                ln_data[name] = np.log(s_common)

        if len(ln_data) < 2:
            return {}

        Y = pd.DataFrame(ln_data).dropna()
        if len(Y) < 8:
            return {}

        logger.info(f"  VECM: матрица {Y.shape} ({Y.index[0]}–{Y.index[-1]})")

        # Параметры из конфига
        p_min = int(cfg.get("p_min", 1))
        p_max = int(cfg.get("p_max", 3))
        alpha = float(cfg.get("alpha", 0.05))

        # Подбираем VECM
        fit = _fit_vecm(Y, det="ci", p_min=p_min, p_max=p_max, alpha=alpha)
        if fit is None or fit.get("model") is None:
            logger.info("  VECM: не удалось подобрать модель")
            return {}

        model = fit["model"]
        rank  = fit["rank"]
        p     = fit["p"]
        logger.info(f"  VECM: rank={rank} p={p} aic={fit.get('aic', float('nan')):.2f}")

        # Если rank слишком высокий для малых выборок — ограничиваем
        n_vars = Y.shape[1]
        n_obs  = Y.shape[0]
        max_safe_rank = max(1, min(rank, n_vars - 1, n_obs // 8))
        if rank > max_safe_rank:
            logger.warning(f"  VECM rank={rank} снижен до {max_safe_rank} (n_obs={n_obs})")
            from statsmodels.tsa.vector_ar.vecm import VECM as SMVecm
            try:
                sm_model = SMVecm(Y, k_ar_diff=p, coint_rank=max_safe_rank, deterministic="ci")
                model = sm_model.fit(method="ml")
                rank = max_safe_rank
            except Exception:
                pass

        # Прогноз
        steps = len(forecast_index)
        fc_ln = model.predict(steps=steps)  # shape: (steps, n_factors)

        forecasts = {}
        for i, name in enumerate(Y.columns):
            s_orig = factor_series[name]
            last_val = float(s_orig.loc[common_years[-1]])
            fc_vals = {}
            for j, yr in enumerate(forecast_index):
                try:
                    val = float(np.exp(fc_ln[j, i]))
                    # Sanity check: не более 2x роста или 50% падения за горизонт
                    max_growth = last_val * (1.5 ** (j / max(steps, 1) + 1))
                    min_val    = last_val * (0.3 ** (j / max(steps, 1) + 1))
                    if min_val < val < max_growth:
                        fc_vals[yr] = val
                except (IndexError, ValueError):
                    pass
            if len(fc_vals) == steps:
                forecasts[name] = fc_vals
                logger.info(f"  VECM forecast {name}: {[round(v) for v in list(fc_vals.values())[:3]]}")

        return forecasts

    except ImportError as e:
        logger.debug(f"vecm._fit_vecm недоступен: {e}")
        return {}
    except Exception as e:
        logger.warning(f"VECM ошибка: {e}")
        return {}


_COMMODITY_FACTORS = {
    "steel_price_hrc", "steel_ppi_iron_steel", "hot_rolled_steel_ppi",
    "brent", "brent_usd", "coal_price", "iron_ore_price",
    "lme_aluminum", "lme_al", "copper_price",
}

_MACRO_FACTORS = {
    "gdp_us", "gdp_world", "gdp_growth_us", "gdp_growth_world",
    "cpi_us", "cpi_global", "ppi_us", "ppi_metals",
    "industrial_production_us", "pmi_us", "pmi_manufacturing",
    "fed_funds_rate", "10y_treasury", "unemployment_us",
    "steel_capacity_utilization",
}

# Нестабильные FX/currency факторы — исключаем из VECM
_EXCLUDE_FROM_VECM = {"fx_usdrub", "rub_usd", "dxy"}


def auto_group_factors(
    factor_names: List[str],
    group_size: int = 3,
) -> tuple:
    """
    Разбивает факторы на два потока:
    1. vecm_groups  — макро факторы для VECM (GDP, CPI, industrial production)
    2. mr_factors   — commodity факторы для Mean Reversion (HRC, SPPI, brent)

    Обоснование разделения:
    - Commodity (цены на сталь, нефть): цикличные, mean-reverting,
      нет стабильной коинтеграции с макро в коротких выборках
    - Macro (GDP, CPI): трендовые, коинтегрированы между собой,
      VECM работает надёжно

    Returns:
        (vecm_groups: Dict[str, List[str]], mr_factors: List[str], ewa_factors: List[str])
    """
    COMMODITY = {
        "steel_price_hrc", "steel_ppi_iron_steel", "hot_rolled_steel_ppi",
        "brent", "brent_usd", "coal_price", "iron_ore_price",
        "lme_aluminum", "lme_al", "copper_price",
    }
    MACRO = {
        "gdp_us", "gdp_world", "gdp_china", "cpi_us", "ppi_us",
        "industrial_production_us",
    }
    # FX исключаем из VECM — слишком волатильны для коротких выборок
    EXCLUDE_VECM = {"fx_usdrub", "rub_usd", "dxy"}

    commodity_factors = [f for f in factor_names if f in COMMODITY]
    macro_factors     = [f for f in factor_names if f in MACRO]
    ewa_factors       = [f for f in factor_names
                         if f not in COMMODITY and f not in MACRO
                         and f not in EXCLUDE_VECM]
    exclude_factors   = [f for f in factor_names if f in EXCLUDE_VECM]

    # Только макро-факторы идут в VECM группы
    vecm_groups: Dict[str, List[str]] = {}
    for i in range(0, len(macro_factors), group_size):
        chunk = macro_factors[i:i + group_size]
        vecm_groups[f"macro_{i // group_size + 1}"] = chunk

    logger.info(
        f"  Потоки: VECM={len(macro_factors)} макро, "
        f"MR={len(commodity_factors)} commodity, "
        f"EWA={len(ewa_factors)} прочих, "
        f"skip={exclude_factors}"
    )

    return vecm_groups, commodity_factors, ewa_factors


def run_full_macro_forecast(
    repo,
    company_id: str,
    all_factor_names: List[str],
    scenario_id: int,
    scenario_name: str = "base",
    forecast_years: int = 5,
    cfg: Optional[Dict] = None,
) -> Dict[str, Dict[int, float]]:
    """
    Полный макро-прогноз — три потока:

    1. VECM для макро факторов (GDP, CPI, industrial production)
       Коинтегрированы, надёжный VECM на 8+ наблюдениях

    2. Mean Reversion для commodity (HRC, SPPI, brent)
       Цикличные цены, MR экономически обоснован
       kappa зависит от сценария: base=0.15, bear=0.5, bull=RWdrift

    3. EWA для прочих (неклассифицированные факторы)
       Нейтральный fallback

    Returns:
        {factor_name: {year: value}}
    """
    from .commodity_models import mean_reversion_forecast, rw_drift_clamped

    # Set adapter for io.py and vecm.py to use
    from .db_adapter import MacroDBAdapter
    _adapter = MacroDBAdapter(repo, company_id, scenario_id)
    from . import io as _io_mod
    _io_mod.set_adapter(_adapter)
    from . import vecm as _vecm_mod
    _vecm_mod.set_db_adapter(_adapter)

    all_forecasts: Dict[str, Dict[int, float]] = {}

    # Определяем kappa и метод для commodity по сценарию
    scenario_lower = (scenario_name or "base").lower()
    if any(k in scenario_lower for k in ["bear", "stress", "severe", "down"]):
        commodity_method = "mean_reversion"
        commodity_kappa  = 0.5
    elif any(k in scenario_lower for k in ["bull", "up", "optimistic"]):
        commodity_method = "rw_drift"
        commodity_kappa  = None
    else:
        commodity_method = "mean_reversion"
        commodity_kappa  = 0.15

    # Автоматическое разделение на потоки
    vecm_groups, commodity_factors, ewa_factors = auto_group_factors(
        all_factor_names, group_size=3
    )

    # ── Поток 1: VECM для макро ───────────────────────────────────────────────
    if vecm_groups:
        n_macro = sum(len(v) for v in vecm_groups.values())
        logger.info(f"  Поток 1: VECM для {n_macro} макро-факторов")
        vecm_fc = run_vecm_by_groups(
            repo=repo,
            company_id=company_id,
            factor_groups=vecm_groups,
            scenario_id=scenario_id,
            forecast_years=forecast_years,
            cfg=cfg,
        )
        all_forecasts.update(vecm_fc)
        logger.info(f"  VECM: {len(vecm_fc)} факторов спрогнозировано")

    # ── Поток 2: Mean Reversion для commodity ─────────────────────────────────
    if commodity_factors:
        logger.info(
            f"  Поток 2: {commodity_method}(kappa={commodity_kappa}) "
            f"для {len(commodity_factors)} commodity"
        )
        for factor_name in commodity_factors:
            history = repo.get_macro_factor(factor_name)
            if len(history) < 3:
                continue
            if commodity_method == "mean_reversion":
                fc = mean_reversion_forecast(history, forecast_years, kappa=commodity_kappa)
            else:
                fc = rw_drift_clamped(history, forecast_years,
                                      ewa_halflife=8.0, percentile_lo=0.5, percentile_hi=0.95)
            if fc:
                all_forecasts[factor_name] = fc
                vals = [round(v) for v in list(fc.values())[:3]]
                logger.info(f"    {factor_name}: {vals}")

    # ── Поток 3: EWA для прочих ───────────────────────────────────────────────
    if ewa_factors:
        logger.info(f"  Поток 3: EWA для {len(ewa_factors)} прочих факторов")
        from .commodity_models import select_best_forecast
        for factor_name in ewa_factors:
            history = repo.get_macro_factor(factor_name)
            if len(history) < 3:
                continue
            fc = select_best_forecast(history, method="ewa",
                                      forecast_years=forecast_years, halflife=5.0)
            if fc:
                all_forecasts[factor_name] = fc

    return all_forecasts


def run_vecm_by_groups(
    repo,
    company_id: str,
    factor_groups: Dict[str, List[str]],
    scenario_id: int,
    forecast_years: int = 5,
    cfg: Optional[Dict] = None,
) -> Dict[str, Dict[int, float]]:
    """
    Запускает VECM по группам факторов (≤group_size каждая).

    Решает ограничение Johansen: максимум 12 переменных (оптимально ≤4).
    Каждая группа обрабатывается независимо через run_vecm_for_factors.

    Args:
        repo:          Repository (v2)
        company_id:    ID компании
        factor_groups: {group_name: [factor_names]} — dict из auto_group_factors или YAML
        scenario_id:   ID сценария
        forecast_years: горизонт прогноза
        cfg:           конфиг из macro_ecm.yaml (секция vecm)

    Returns:
        {factor_name: {year: value}} — объединённые прогнозы всех групп
    """
    all_forecasts: Dict[str, Dict[int, float]] = {}
    total_groups = len(factor_groups)

    for i, (group_name, factor_names) in enumerate(factor_groups.items(), 1):
        if not factor_names:
            continue
        logger.info(f"  Группа {i}/{total_groups} [{group_name}]: {factor_names}")
        try:
            group_forecasts = run_vecm_for_factors(
                repo=repo,
                company_id=company_id,
                factor_names=factor_names,
                scenario_id=scenario_id,
                forecast_years=forecast_years,
                cfg=cfg,
            )
            if group_forecasts:
                all_forecasts.update(group_forecasts)
                logger.info(f"    → {len(group_forecasts)}/{len(factor_names)} факторов спрогнозировано")
            else:
                logger.info(f"    → 0/{len(factor_names)} (fallback будет использован)")
        except Exception as e:
            logger.warning(f"    Группа {group_name} ошибка: {e}")

    return all_forecasts


def _univariate_forecast(
    series: Any,
    forecast_index: List[int],
    cfg: Dict,
) -> Dict[int, float]:
    """
    Univariate прогноз одного ряда.
    Порядок попыток: ARIMA(0,1,1) → ETS → RW-drift.
    """
    import numpy as np

    steps = len(forecast_index)

    try:
        from engine.macro.vecm import (
            _forecast_arima011_ln,
            _forecast_ets_ln,
            _forecast_rw_drift_ln,
        )
        import pandas as pd

        methods = [
            ("arima011", _forecast_arima011_ln),
            ("ets",      _forecast_ets_ln),
            ("rw_drift", _forecast_rw_drift_ln),
        ]

        last_val = float(series.iloc[-1])

        for method_name, fn in methods:
            try:
                fc_series = fn(series, steps)
                if fc_series is None or fc_series.isna().any():
                    continue
                result = {}
                for i, yr in enumerate(forecast_index):
                    val = float(fc_series.iloc[i])
                    if 0.05 * last_val < val < 20 * last_val:
                        result[yr] = val
                if len(result) == steps:
                    logger.debug(f"    {method_name}: OK")
                    return result
            except Exception as e:
                logger.debug(f"    {method_name}: {e}")
                continue

    except ImportError:
        pass

    # Pure Python fallback — EWA RW-drift в log-пространстве
    try:
        import math
        vals = [float(v) for v in series.values if v > 0]
        if len(vals) < 3:
            return {}
        growth_rates = [math.log(vals[i] / vals[i - 1]) for i in range(1, len(vals))]
        alpha = 0.3
        drift = growth_rates[0]
        for g in growth_rates[1:]:
            drift = alpha * g + (1 - alpha) * drift
        drift = max(-0.15, min(0.15, drift))
        result = {}
        val = vals[-1]
        for yr in forecast_index:
            val = val * math.exp(drift)
            result[yr] = val
        return result
    except Exception:
        return {}
