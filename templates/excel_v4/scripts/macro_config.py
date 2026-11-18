"""Загрузчик единого SSOT макросценариев (config/macro_scenarios.yaml).

Используется книгами excel_v4 (fill_data.py) и Python engine (engine/macro/scenario_config.py).
Винтаж значений — в meta.vintage файла конфигурации.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "macro_scenarios.yaml"


@lru_cache(maxsize=1)
def load_macro_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_company_config(company: str) -> dict:
    cfg = load_macro_config()
    return cfg.get(company, {})


def get_scenarios(company: str) -> dict:
    """{scenario: {factor: {values, source, tag}}} — плоская нормализация."""
    raw = get_company_config(company).get("scenarios", {})
    return {sc: {f: d for f, d in factors.items()} for sc, factors in raw.items()}


def get_hist_actuals(company: str) -> dict:
    """{year: {factor: value}} — фактические исторические значения для строк сценариев."""
    raw = get_company_config(company).get("hist_actuals", {})
    return {int(y): {f: v for f, v in factors.items()} for y, factors in raw.items()}


def get_engine_factors(company: str) -> dict:
    """{factor: {values, source, tag}} — факторы только для engine (нет в книге)."""
    return get_company_config(company).get("engine", {})


def get_ols_supplement() -> dict:
    """{factor: {year: value}} — номинальные годовые средние LME для OLS-блока 2018-2025."""
    return load_macro_config().get("ols_supplement", {})


def get_lme_al_history() -> dict:
    """{year: value} — номинальная история LME Aluminium (исправление driver CSV)."""
    raw = load_macro_config().get("lme_al_history", {}).get("values", {})
    return {int(y): float(v) for y, v in raw.items()}


def get_alumina_lme_ratio() -> float:
    return float(get_company_config("rusal").get("alumina_lme_ratio", {}).get("value", 0.134))
