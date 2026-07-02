"""
DB-адаптер для макро-модуля v2.
Заменяет старый DataMart на Repository.
Интерфейс намеренно совместим с mart.* вызовами из vecm.py/core.py.
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


class MacroDBAdapter:
    """
    Тонкая обёртка над Repository с интерфейсом совместимым со старым DataMart.
    Используется внутри vecm.py и core.py вместо get_data_mart().
    """

    def __init__(self, repo, company_id: str, scenario_id: int) -> None:
        self._repo = repo
        self._company = company_id
        self._scenario_id = scenario_id

    # ── чтение макро-факторов ─────────────────────────────────────────────────

    def get_macro_factor(self, factor_name: str) -> Dict[int, float]:
        """Возвращает {year: value} исторического ряда."""
        return self._repo.get_macro_factor(factor_name, scope="global")

    def get_macro_factor_company(self, factor_name: str) -> Dict[int, float]:
        """Company-специфичный ряд (fallback на global)."""
        data = self._repo.get_macro_factor(factor_name, scope="company",
                                            company_id=self._company)
        if not data:
            data = self._repo.get_macro_factor(factor_name, scope="global")
        return data

    # ── сохранение прогнозов ──────────────────────────────────────────────────

    def save_macro_forecast(
        self,
        factor_name: str,
        data: Dict[int, float],
        method: str = "",
    ) -> None:
        """Сохранить прогноз одного фактора."""
        if not data:
            return
        self._repo.upsert_macro_forecasts(
            company_id=self._company,
            scenario_id=self._scenario_id,
            data={factor_name: data},
            method=method,
        )
        logger.debug(f"macro_forecast saved: {factor_name} ({len(data)} pts, {method})")

    def save_macro_forecasts_bulk(
        self,
        forecasts: Dict[str, Dict[int, float]],
        method: str = "",
    ) -> None:
        """Сохранить прогнозы нескольких факторов за один вызов."""
        if not forecasts:
            return
        self._repo.upsert_macro_forecasts(
            company_id=self._company,
            scenario_id=self._scenario_id,
            data=forecasts,
            method=method,
        )

    # ── диагностика (no-op в v2 — пишем только в лог) ────────────────────────

    def save_ecm_diagnostics(self, *args, **kwargs) -> None:
        logger.debug(f"ecm_diagnostics: {kwargs.get('factor_name', '')} — skipped (v2)")

    def save_actual_vs_fitted(self, *args, **kwargs) -> None:
        logger.debug("actual_vs_fitted — skipped (v2)")

    def save_forecast_diagnostics(self, *args, **kwargs) -> None:
        logger.debug("forecast_diagnostics — skipped (v2)")

    def save_ecm_equation(self, *args, **kwargs) -> None:
        logger.debug("ecm_equation — skipped (v2)")

    def save_ecm_forecast_diag(self, *args, **kwargs) -> None:
        logger.debug("ecm_forecast_diag — skipped (v2)")

    def save_macro_anomaly_report(self, *args, **kwargs) -> None:
        logger.debug("macro_anomaly_report — skipped (v2)")

    # ── совместимость с DataMart интерфейсом ──────────────────────────────────

    def close(self) -> None:
        pass  # Repository управляется снаружи через context manager

    def get_company_id(self, company: str) -> Optional[int]:
        row = self._repo.get_company(company)
        return row["company_id"] if row else None


def get_macro_adapter(repo, company_id: str, scenario_name: str = "base") -> MacroDBAdapter:
    """
    Создать адаптер для макро-модуля.
    Аналог get_data_mart() из старого кода.
    """
    scenario_id = repo.ensure_scenario(company_id, scenario_name, type_=scenario_name)
    return MacroDBAdapter(repo, company_id, scenario_id)
