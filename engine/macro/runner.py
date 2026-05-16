"""
Макро-модуль v2 — точка входа.
Запускает VECM/ARIMA прогноз макро-факторов и сохраняет в data_mart_v2.db.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MacroResult:
    company_id: str
    success: bool = False
    factors_forecast: List[str] = field(default_factory=list)
    methods_used: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Макро: {self.company_id}",
            f"  Статус: {'OK' if self.success else 'FAIL'}",
            f"  Факторов: {len(self.factors_forecast)}",
        ]
        if self.methods_used:
            for f, m in list(self.methods_used.items())[:5]:
                lines.append(f"  {f}: {m}")
        if self.errors:
            lines += [f"  ✗ {e}" for e in self.errors[:3]]
        return "\n".join(lines)


def run_macro(
    company_id: str,
    repo,
    config_path: Optional[Path] = None,
    scenario_name: str = "base",
    forecast_years: int = 5,
) -> MacroResult:
    """
    Запустить макро-прогноз для компании.

    Порядок:
    1. Читает macro_ecm.yaml
    2. Загружает исторические ряды из БД
    3. Запускает VECM/ARIMA по блокам
    4. Сохраняет прогноз в macro_forecasts через Repository

    Args:
        company_id:    ID компании
        repo:          Repository (должен быть уже подключён)
        config_path:   путь к macro_ecm.yaml
        scenario_name: имя сценария
        forecast_years: горизонт прогноза в годах
    """
    result = MacroResult(company_id=company_id)

    # Разрешаем путь к конфигу
    from engine import ROOT as root
    if config_path is None:
        config_path = root / "companies" / company_id / "configs" / "macro_ecm.yaml"

    if not config_path.exists():
        msg = f"macro_ecm.yaml не найден: {config_path}"
        result.errors.append(msg)
        logger.warning(msg)
        return result

    try:
        from .db_adapter import get_macro_adapter
        adapter = get_macro_adapter(repo, company_id, scenario_name)

        logger.info(f"Запуск макро-прогноза для {company_id} (сценарий: {scenario_name})...")
        # run_full_macro_forecast обрабатывает все сценарии:
        # commodity → MR с kappa по сценарию, macro → VECM, прочие → EWA
        _run_with_adapter(company_id, adapter, config_path, root, result, forecast_years, scenario_name)

    except Exception as e:
        result.errors.append(str(e))
        logger.exception(f"Ошибка макро-модуля: {e}")

    result.success = len(result.errors) == 0
    return result


def _run_with_adapter(
    company_id: str,
    adapter,
    config_path: Path,
    root: Path,
    result: MacroResult,
    forecast_years: int = 5,
    scenario_name: str = "base",
) -> None:
    """Запуск полного макро-прогноза: VECM (макро) + MR (commodity) + EWA (прочие)."""
    import yaml
    from .vecm_bridge import _check_dependencies

    # Проверяем зависимости
    deps = _check_dependencies()
    logger.info(f"  Зависимости: statsmodels={deps.get('statsmodels')} pmdarima={deps.get('pmdarima')}")

    with open(config_path) as f:
        cfg = yaml.safe_load(f) or {}

    # Собираем все факторы из конфига
    factors_cfg = cfg.get("factors", {})
    yaml_groups = cfg.get("groups", {})

    all_factors: set = set()
    if isinstance(factors_cfg, dict):
        all_factors.update(factors_cfg.keys())
    elif isinstance(factors_cfg, list):
        for f in factors_cfg:
            if isinstance(f, dict):
                all_factors.add(f.get('id') or f.get('name', ''))
            else:
                all_factors.add(str(f))

    for grp_factors in yaml_groups.values():
        if isinstance(grp_factors, list):
            all_factors.update(grp_factors)
        elif isinstance(grp_factors, dict):
            all_factors.update(grp_factors.keys())

    if not all_factors:
        # Берём все доступные факторы из БД
        rows = adapter._repo.query(
            "SELECT DISTINCT factor_name FROM macro_factors WHERE scope='global'"
        )
        all_factors = {r["factor_name"] for r in rows}

    logger.info(f"  Факторов в конфиге: {len(all_factors)}")

    # Получаем scenario_id
    scenario_id = adapter._scenario_id

    if deps.get("statsmodels") and deps.get("pandas"):
        logger.info("  Запуск полного макро-прогноза (VECM + MR + EWA)...")
        try:
            from .vecm_bridge import run_full_macro_forecast

            forecasts = run_full_macro_forecast(
                repo=adapter._repo,
                company_id=company_id,
                all_factor_names=list(all_factors),
                scenario_id=scenario_id,
                scenario_name=scenario_name or "base",
                forecast_years=forecast_years,
                cfg=cfg.get("vecm", {}),
            )

            _COMMODITY_KW = ["steel", "brent", "coal", "iron", "aluminum", "lme", "hrc", "ppi_iron"]
            for factor_name, fc_data in forecasts.items():
                is_commodity = any(kw in factor_name.lower() for kw in _COMMODITY_KW)
                method = (f"mean_reversion(scenario={scenario_name})" if is_commodity
                          else "vecm_groups")
                adapter.save_macro_forecast(factor_name, fc_data, method=method)
                result.factors_forecast.append(factor_name)
                result.methods_used[factor_name] = method

            # Факторы из конфига, не покрытые VECM/MR — заполняем fallback
            missing = all_factors - set(forecasts.keys())
            if missing:
                logger.info(f"  Gap-fill fallback для {len(missing)} факторов: {sorted(missing)}")
                _fill_missing_with_fallback(missing, adapter, result, forecast_years)

            logger.info(f"  Итого: {len(result.factors_forecast)} факторов спрогнозировано")
            return

        except Exception as e:
            logger.warning(f"  Ошибка: {e}, переходим к fallback")

    # Полный fallback
    _run_fallback(company_id, adapter._repo, adapter, config_path, forecast_years, result)


def _fill_missing_with_fallback(
    factor_names,
    adapter,
    result: MacroResult,
    forecast_years: int,
) -> None:
    """Заполняет оставшиеся факторы через scenario-aware fallback."""
    from .commodity_models import select_best_forecast

    for factor_name in factor_names:
        history = adapter.get_macro_factor(factor_name)
        if len(history) < 3:
            continue
        is_commodity = any(kw in factor_name.lower()
                           for kw in ["steel", "brent", "coal", "iron", "aluminum",
                                      "copper", "gas", "hrc", "ppi_iron"])
        if is_commodity:
            fc = select_best_forecast(history, method="mean_reversion",
                                      forecast_years=forecast_years, kappa=0.15)
            method = "mean_reversion(kappa=0.15)"
        else:
            fc = select_best_forecast(history, method="ewa",
                                      forecast_years=forecast_years, halflife=5.0)
            method = "ewa(halflife=5)"
        if fc:
            adapter.save_macro_forecast(factor_name, fc, method=method)
            result.factors_forecast.append(factor_name)
            result.methods_used[factor_name] = method


def _run_fallback(
    company_id: str,
    repo,
    adapter,
    config_path,
    forecast_years: int,
    result: MacroResult,
    scenario_name: str = "base",
) -> None:
    """EWA/MeanReversion fallback если VECM недоступен."""
    from .commodity_models import select_best_forecast

    rows = repo.query(
        "SELECT DISTINCT factor_name FROM macro_factors WHERE scope='global' ORDER BY factor_name"
    )
    factors = [r["factor_name"] for r in rows]

    if not factors:
        result.errors.append("Нет макро-факторов в БД")
        return

    logger.info(f"  Fallback прогноз для {len(factors)} факторов (сценарий: {scenario_name})...")

    scenario_lower = (scenario_name or "base").lower()

    for factor_name in factors:
        history = adapter.get_macro_factor(factor_name)
        if len(history) < 3:
            continue

        is_commodity = any(kw in factor_name.lower()
                           for kw in ["steel", "brent", "coal", "iron", "aluminum",
                                      "copper", "gas", "hrc", "ppi_iron", "lme"])
        is_macro = any(kw in factor_name.lower()
                       for kw in ["gdp", "cpi", "ppi", "production", "pmi", "dxy"])

        if is_commodity:
            # kappa зависит от сценария:
            # base → κ=0.15 (медленная нормализация, нейтральный)
            # bear/stress → κ=0.5 (быстрый возврат к медиане)
            # bull → rw_drift (удержание на высоком уровне)
            if any(k in scenario_lower for k in ["bear", "stress", "severe", "down"]):
                kappa = 0.5
            elif any(k in scenario_lower for k in ["bull", "up", "optimistic"]):
                forecast = select_best_forecast(
                    history, method="rw_drift",
                    forecast_years=forecast_years,
                    ewa_halflife=8.0,
                    percentile_lo=0.50,
                    percentile_hi=0.95,
                )
                used_method = "rw_drift_clamped(P50-P95)"
                if forecast:
                    adapter.save_macro_forecast(factor_name, forecast, method=used_method)
                    result.factors_forecast.append(factor_name)
                    result.methods_used[factor_name] = used_method
                continue
            else:
                kappa = 0.15  # base — медленная нормализация

            forecast = select_best_forecast(
                history, method="mean_reversion",
                forecast_years=forecast_years,
                kappa=kappa,
            )
            used_method = f"mean_reversion(kappa={kappa})"
        elif is_macro:
            forecast = select_best_forecast(
                history, method="ewa",
                forecast_years=forecast_years,
                halflife=5.0,
            )
            used_method = "ewa(halflife=5)"
        else:
            forecast = select_best_forecast(
                history, method="rw_drift",
                forecast_years=forecast_years,
            )
            used_method = "rw_drift_clamped"

        if forecast:
            adapter.save_macro_forecast(factor_name, forecast, method=used_method)
            result.factors_forecast.append(factor_name)
            result.methods_used[factor_name] = used_method

