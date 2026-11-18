"""Применение SSOT макросценариев (templates/excel_v4/config/macro_scenarios.yaml)
к macro_forecasts БД engine.

Принцип «одна база»: base engine = стартовые точки книг (те же значения, те же
источники). Запускается ПОСЛЕ VECM/external/fallback — перезаписывает базовые
пути факторов, которые есть в конфиге. ECM/VECM-методы остаются для факторов
вне конфига и для стресс-сценариев engine.

Маппинг: имя фактора книги → имя(имена) фактора engine (дедупликация рядов:
USD/RUB пишет и в usd_rub, и в fx_usdrub; Brent — в brent и brent_usd).
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_YAML_PATH = Path(__file__).resolve().parents[2] / "templates" / "excel_v4" / "config" / "macro_scenarios.yaml"

# Книга → engine (дедуплирующиеся ряды)
BOOK_TO_ENGINE = {
    "LME Aluminium": ["lme_aluminium"],
    "USD/RUB": ["usd_rub", "fx_usdrub"],
    "USD/CNY": ["usd_cny"],
    "Brent": ["brent", "brent_usd"],
    "CPI RU": ["cpi_ru"],
    "PPI RU": ["ppi_ru"],
    "GDP World": ["gdp_world"],
}


def _fractions_to_chain_index(values: list[float], base: float = 100.0) -> list[float]:
    """Доли (0.07 = +7%) → годовой индекс base=100 (107.0, 105.5, …) как в ветке VECM."""
    return [round(base * (1.0 + float(v)), 2) for v in values]


def _load() -> dict:
    with open(_YAML_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def apply_scenario_config(adapter, company_id: str, scenario_name: str = "base") -> list[str]:
    """Перезаписывает base-прогнозы факторов из YAML. Возвращает список применённых факторов."""
    cfg = _load()
    vintage = cfg.get("meta", {}).get("vintage", "?")
    fc_years = cfg.get("meta", {}).get("fc_years", [2026, 2027, 2028])
    co_cfg = cfg.get(company_id, {})
    applied: list[str] = []

    def _save(factor: str, values: list, source: str):
        fc = {yr: float(v) for yr, v in zip(fc_years, values)}
        method = f"scenario_base(yaml {vintage})"
        adapter.save_macro_forecast(factor, fc, method=method)
        applied.append(factor)
        logger.info("  SSOT %s %s: %s ← %s", company_id, factor,
                    [round(v, 2) for v in values], source[:60])

    # 1) Факторы книги (base)
    base_scen = co_cfg.get("scenarios", {}).get(scenario_name, {})
    for book_f, fdata in base_scen.items():
        for eng_f in BOOK_TO_ENGINE.get(book_f, []):
            vals = fdata["values"]
            if eng_f in ("cpi_ru", "ppi_ru"):
                # книга хранит доли, engine потребляет цепной индекс base=100 (как VECM-ветка)
                vals = _fractions_to_chain_index(vals)
            _save(eng_f, vals, fdata.get("source", ""))

    # 2) LME Alumina для engine: в книге = формула Al × CP-отношение, здесь — явный путь
    if "LME Aluminium" in base_scen and company_id == "rusal":
        ratio = float(co_cfg.get("alumina_lme_ratio", {}).get("value", 0.134))
        al_vals = base_scen["LME Aluminium"]["values"]
        _save("lme_alumina", [round(v * ratio, 1) for v in al_vals],
              f"LME Al × {ratio} (CP.alumina_lme_ratio, факт 2025)")

    # 2) Факторы только engine (ставка ЦБ, Euribor, ВВП)
    for eng_f, fdata in co_cfg.get("engine", {}).items():
        _save(eng_f, fdata["values"], fdata.get("source", ""))

    return applied


def get_lme_al_history() -> dict[int, float]:
    """Номинальная история LME Aluminium (исправление заниженного ряда БД)."""
    cfg = _load()
    raw = cfg.get("lme_al_history", {}).get("values", {})
    return {int(y): float(v) for y, v in raw.items()}
