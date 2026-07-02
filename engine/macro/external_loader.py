"""
External macro loader — интеграция с modelMacro (квартальная ECM, 13 ур-й).

Загружает макро-прогнозы и отраслевые драйверы из внешней макро-модели,
конвертирует quarterly→annual и сохраняет в macro_forecasts через Repository.

Режим: override — перезаписывает встроенный VECM/MR для совпадающих факторов,
остальные (LME Al, Alumina, power price) прогнозируются как раньше.
"""
from __future__ import annotations

import csv
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Маппинг переменных: modelMacro → stressTest_v2 ──────────────────────────

DEFAULT_VARIABLE_MAP: Dict[str, str] = {
    "POIL":    "brent",
    "RUBUSD":  "usd_rub",
    "R":       "cbr_key_rate",
    "KEY":     "cbr_key_rate_policy",
}

# Переменные-уровни, из которых нужно вычислить YoY индекс
# (CPI level → cpi_ru как индекс base=100)
LEVEL_TO_INDEX_MAP: Dict[str, str] = {
    "CPI":  "cpi_ru",
    "PY":   "ppi_ru",   # GDP deflator как proxy PPI
}

# Переменные-логарифмы, которые нужно exp() для получения уровня
LOG_VARIABLES: Dict[str, str] = {
    "Y_real":  "gdp_ru",
}

# Агрегация quarterly → annual
AGGREGATION_METHODS: Dict[str, str] = {
    "brent":                "mean",     # средняя цена за год
    "usd_rub":              "mean",     # средний курс
    "cpi_ru":               "q4_level", # Q4 уровень (индекс)
    "ppi_ru":               "q4_level", # Q4 уровень (индекс)
    "cbr_key_rate":         "q4",       # ставка на конец года
    "cbr_key_rate_policy":  "q4",       # policy rate на конец года
    "gdp_ru":               "sum",      # ВВП = сумма за 4 квартала
}

# Маппинг сценариев: modelMacro → stressTest_v2
DEFAULT_SCENARIO_MAP: Dict[str, str] = {
    "baseline":      "base",
    "high_oil":      "upside",
    "low_oil":       "bear",
    "collapse":      "severe",
    "uae_bearish":   "sanctions_shock",
    "uae_moderate":  "energy_spike",
    "uae_high":      "bull",
}

# Отраслевые драйверы: sector_tag → какие метрики извлекать
SECTOR_DRIVER_DEFS = {
    "gva_growth": {
        "file": "data/processed/sector/gva_by_sector.csv",
        "value_col": "gva_nominal_bln",
        "date_col": "date",
        "sector_col": "sector_tag",
        "method": "yoy_growth",  # compute YoY growth from levels
        "factor_template": "gva_growth_{sector}",
    },
    "ipi": {
        "file": "data/processed/sector/ipi_by_sector.csv",
        "value_col": "ipi_yoy",
        "date_col": "date",
        "sector_col": "sector_tag",
        "method": "mean",  # avg monthly → annual
        "factor_template": "ipi_{sector}",
    },
    "wages": {
        "file": "data/processed/sector/wages_by_sector.csv",
        "value_col": "wage_rub",
        "date_col": "date",
        "sector_col": "sector_tag",
        "method": "mean",
        "factor_template": "sector_wage_{sector}",
    },
    "npl": {
        "file": "data/processed/sector/credit_npl_by_sector.csv",
        "value_col": "overdue_ratio",
        "date_col": "date",
        "sector_col": "sector_tag",
        "method": "last",  # последнее значение в году
        "factor_template": "sector_npl_{sector}",
    },
    "leverage": {
        "file": "data/processed/sector/leverage_by_sector.csv",
        "value_col": "leverage_ratio",
        "date_col": "date",
        "sector_col": "sector_tag",
        "method": "last",
        "factor_template": "sector_leverage_{sector}",
    },
    "ppi": {
        "file": "data/processed/sector/ppi_by_sector.csv",
        "value_col": "ppi_mom",
        "date_col": "date",
        "sector_col": "sector_tag",
        "method": "mean",  # avg monthly MoM → annual PPI index
        "factor_template": "ppi_{sector}",
    },
}


@dataclass
class ExternalLoadResult:
    """Результат загрузки внешних макро-данных."""
    factors_loaded: List[str] = field(default_factory=list)
    methods_used: Dict[str, str] = field(default_factory=dict)
    scenarios_mapped: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0 and len(self.factors_loaded) > 0


# ── Утилиты парсинга дат ─────────────────────────────────────────────────────

def _parse_quarter(q: str) -> Tuple[int, int]:
    """Parse '2026Q2' → (2026, 2). Raises ValueError on bad format."""
    q = q.strip()
    year = int(q[:4])
    qn = int(q[5])
    return year, qn


def _parse_month_date(d: str) -> Tuple[int, int]:
    """Parse '2024-03' or '2024-03-01' → (2024, 3)."""
    d = d.strip()
    parts = d.split("-")
    return int(parts[0]), int(parts[1])


# ── Квартал → Год агрегация ──────────────────────────────────────────────────

def _aggregate_quarterly_to_annual(
    quarterly: Dict[Tuple[int, int], float],
    method: str,
) -> Dict[int, float]:
    """
    Агрегирует квартальные данные {(year, qn): value} → {year: value}.

    Методы:
      mean:      avg(Q1..Q4)
      sum:       sum(Q1..Q4)
      q4:        значение Q4
      q4_level:  значение Q4 (для индексов CPI/PPI)
      last:      последний доступный квартал
    """
    by_year: Dict[int, List[Tuple[int, float]]] = defaultdict(list)
    for (yr, qn), val in quarterly.items():
        by_year[yr].append((qn, val))

    result: Dict[int, float] = {}
    for yr, vals in sorted(by_year.items()):
        vals.sort(key=lambda x: x[0])
        if method == "mean":
            result[yr] = sum(v for _, v in vals) / len(vals)
        elif method == "sum":
            if len(vals) >= 4:
                result[yr] = sum(v for _, v in vals)
            else:
                # Annualize: (sum / available_quarters) × 4
                result[yr] = sum(v for _, v in vals) / len(vals) * 4
        elif method in ("q4", "q4_level"):
            q4_vals = [v for qn, v in vals if qn == 4]
            if q4_vals:
                result[yr] = q4_vals[0]
            else:
                # Fallback: last available quarter
                result[yr] = vals[-1][1]
        elif method == "last":
            result[yr] = vals[-1][1]
        else:
            result[yr] = sum(v for _, v in vals) / len(vals)

    return result


def _aggregate_monthly_to_annual(
    monthly: Dict[Tuple[int, int], float],
    method: str,
) -> Dict[int, float]:
    """
    Агрегирует месячные данные {(year, month): value} → {year: value}.
    """
    by_year: Dict[int, List[Tuple[int, float]]] = defaultdict(list)
    for (yr, mn), val in monthly.items():
        by_year[yr].append((mn, val))

    result: Dict[int, float] = {}
    for yr, vals in sorted(by_year.items()):
        vals.sort(key=lambda x: x[0])
        if method == "mean":
            result[yr] = sum(v for _, v in vals) / len(vals)
        elif method == "sum":
            result[yr] = sum(v for _, v in vals)
        elif method == "last":
            result[yr] = vals[-1][1]
        elif method == "yoy_growth":
            result[yr] = sum(v for _, v in vals) / len(vals)
        else:
            result[yr] = sum(v for _, v in vals) / len(vals)

    return result


# ══════════════════════════════════════════════════════════════════════════════
# MACRO LOADER
# ══════════════════════════════════════════════════════════════════════════════

def load_external_macro(
    source_path: Path,
    scenario_name: str,
    forecast_start_year: int,
    forecast_years: int = 5,
    variable_map: Optional[Dict[str, str]] = None,
    scenario_map: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, Dict[int, float]], ExternalLoadResult]:
    """
    Загрузить макро-прогнозы из modelMacro scenario_results.csv.

    Args:
        source_path:  корень проекта modelMacro
        scenario_name: целевой сценарий stressTest_v2 (base, bear, severe...)
        forecast_start_year: первый год прогноза (2026)
        forecast_years: горизонт (5)
        variable_map: пользовательский маппинг {modelMacro_var: st2_factor}
        scenario_map: пользовательский маппинг {modelMacro_scenario: st2_scenario}

    Returns:
        (forecasts, result) — {factor_name: {year: value}}, загрузочный отчёт
    """
    result = ExternalLoadResult()
    var_map = {**DEFAULT_VARIABLE_MAP, **(variable_map or {})}
    scen_map = {**DEFAULT_SCENARIO_MAP, **(scenario_map or {})}

    # Обратный маппинг: stressTest_v2 scenario → modelMacro scenario
    reverse_scen = {v: k for k, v in scen_map.items()}
    ext_scenario = reverse_scen.get(scenario_name)
    if not ext_scenario:
        # Если точного маппинга нет, ищем baseline
        ext_scenario = "baseline"
        result.warnings.append(
            f"Нет маппинга для сценария '{scenario_name}', используем baseline"
        )
    result.scenarios_mapped[ext_scenario] = scenario_name

    # Читаем CSV
    csv_path = Path(source_path) / "verify" / "scenario_results.csv"
    if not csv_path.exists():
        result.errors.append(f"scenario_results.csv не найден: {csv_path}")
        return {}, result

    # Парсим CSV → quarterly series по нужным переменным
    needed_vars = set(var_map.keys()) | set(LEVEL_TO_INDEX_MAP.keys()) | set(LOG_VARIABLES.keys())
    # quarterly[variable][(year, qn)] = value
    quarterly: Dict[str, Dict[Tuple[int, int], float]] = defaultdict(dict)

    try:
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["scenario"] != ext_scenario:
                    continue
                var = row["variable"]
                if var not in needed_vars:
                    continue
                try:
                    yr, qn = _parse_quarter(row["quarter"])
                    val = float(row["value"])
                    quarterly[var][(yr, qn)] = val
                except (ValueError, KeyError):
                    continue
    except Exception as e:
        result.errors.append(f"Ошибка чтения CSV: {e}")
        return {}, result

    if not quarterly:
        result.errors.append(f"Нет данных для сценария '{ext_scenario}' в {csv_path}")
        return {}, result

    # Конвертируем → annual forecasts
    forecasts: Dict[str, Dict[int, float]] = {}
    forecast_end = forecast_start_year + forecast_years - 1

    def _filter_forecast_years(annual: Dict[int, float]) -> Dict[int, float]:
        return {yr: v for yr, v in annual.items()
                if forecast_start_year <= yr <= forecast_end}

    # 1. Прямой маппинг (POIL→brent, RUBUSD→usd_rub, R→cbr_key_rate)
    for ext_var, st2_factor in var_map.items():
        if ext_var not in quarterly:
            continue
        agg_method = AGGREGATION_METHODS.get(st2_factor, "mean")
        annual = _aggregate_quarterly_to_annual(quarterly[ext_var], agg_method)
        fc = _filter_forecast_years(annual)
        if fc:
            forecasts[st2_factor] = fc
            result.factors_loaded.append(st2_factor)
            result.methods_used[st2_factor] = f"external_ecm({ext_scenario}:{ext_var}→{agg_method})"

    # 2. CPI/PPI уровни → индексы
    for ext_var, st2_factor in LEVEL_TO_INDEX_MAP.items():
        if ext_var not in quarterly:
            continue
        agg_method = AGGREGATION_METHODS.get(st2_factor, "q4_level")
        annual = _aggregate_quarterly_to_annual(quarterly[ext_var], agg_method)
        fc = _filter_forecast_years(annual)
        if fc:
            forecasts[st2_factor] = fc
            result.factors_loaded.append(st2_factor)
            result.methods_used[st2_factor] = f"external_ecm({ext_scenario}:{ext_var}→index)"

    # 3. Y_real (log → level, sum quarterly)
    for ext_var, st2_factor in LOG_VARIABLES.items():
        if ext_var not in quarterly:
            continue
        annual = _aggregate_quarterly_to_annual(quarterly[ext_var], "sum")
        fc = _filter_forecast_years(annual)
        if fc:
            forecasts[st2_factor] = fc
            result.factors_loaded.append(st2_factor)
            result.methods_used[st2_factor] = f"external_ecm({ext_scenario}:{ext_var}→sum)"

    logger.info(
        f"  External macro: {len(forecasts)} факторов из {ext_scenario} "
        f"({', '.join(sorted(forecasts.keys()))})"
    )
    return forecasts, result


# ══════════════════════════════════════════════════════════════════════════════
# SECTOR LOADER
# ══════════════════════════════════════════════════════════════════════════════

def load_external_sector(
    source_path: Path,
    sector_tags: List[str],
    forecast_start_year: int,
    forecast_years: int = 5,
    drivers: Optional[List[str]] = None,
) -> Tuple[Dict[str, Dict[int, float]], ExternalLoadResult]:
    """
    Загрузить отраслевые драйверы из modelMacro sector CSVs.

    Args:
        source_path:  корень проекта modelMacro
        sector_tags:  список тегов отраслей (mining, manuf, ...)
        forecast_start_year: первый год прогноза
        forecast_years: горизонт
        drivers:      список драйверов для загрузки (None = все доступные)

    Returns:
        (forecasts, result) — {factor_name: {year: value}}, загрузочный отчёт
    """
    result = ExternalLoadResult()
    forecasts: Dict[str, Dict[int, float]] = {}
    source = Path(source_path)

    driver_names = drivers or list(SECTOR_DRIVER_DEFS.keys())

    for drv_name in driver_names:
        drv_def = SECTOR_DRIVER_DEFS.get(drv_name)
        if not drv_def:
            result.warnings.append(f"Неизвестный драйвер: {drv_name}")
            continue

        csv_path = source / drv_def["file"]
        if not csv_path.exists():
            result.warnings.append(f"Файл не найден: {csv_path}")
            continue

        # Читаем CSV
        date_col = drv_def["date_col"]
        value_col = drv_def["value_col"]
        sector_col = drv_def["sector_col"]

        # {sector_tag: {(year, period): value}}
        raw_data: Dict[str, Dict[Tuple[int, int], float]] = defaultdict(dict)

        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    stag = row.get(sector_col, "").strip()
                    if stag not in sector_tags:
                        continue
                    val_str = row.get(value_col, "").strip()
                    if not val_str:
                        continue
                    try:
                        val = float(val_str)
                    except ValueError:
                        continue

                    date_str = row.get(date_col, "").strip()
                    try:
                        if "Q" in date_str:
                            yr, period = _parse_quarter(date_str)
                        else:
                            yr, period = _parse_month_date(date_str)
                    except (ValueError, IndexError):
                        continue

                    raw_data[stag][(yr, period)] = val
        except Exception as e:
            result.warnings.append(f"Ошибка чтения {csv_path}: {e}")
            continue

        # Агрегируем → annual, формируем factor name
        agg_method = drv_def["method"]
        for stag in sector_tags:
            if stag not in raw_data:
                continue

            factor_name = drv_def["factor_template"].format(sector=stag)

            if "Q" in str(list(raw_data[stag].keys())[0]) if raw_data[stag] else False:
                annual = _aggregate_quarterly_to_annual(raw_data[stag], agg_method)
            else:
                # Detect: quarterly (period 1-4) vs monthly (period 1-12)
                max_period = max(p for _, p in raw_data[stag].keys()) if raw_data[stag] else 1
                if max_period <= 4:
                    annual = _aggregate_quarterly_to_annual(raw_data[stag], agg_method)
                else:
                    annual = _aggregate_monthly_to_annual(raw_data[stag], agg_method)

            # Для GVA: пересчёт levels → YoY growth
            if agg_method == "yoy_growth" and len(annual) >= 2:
                years_sorted = sorted(annual.keys())
                growth: Dict[int, float] = {}
                for i in range(1, len(years_sorted)):
                    prev_yr, curr_yr = years_sorted[i - 1], years_sorted[i]
                    if annual[prev_yr] > 0:
                        growth[curr_yr] = (annual[curr_yr] / annual[prev_yr]) - 1.0
                annual = growth

            if annual:
                forecasts[factor_name] = annual
                result.factors_loaded.append(factor_name)
                result.methods_used[factor_name] = f"external_sector({drv_name}:{stag})"

    if forecasts:
        logger.info(
            f"  External sector: {len(forecasts)} драйверов для отраслей "
            f"{sector_tags}"
        )
    return forecasts, result


# ══════════════════════════════════════════════════════════════════════════════
# UNIFIED ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ExternalConfig:
    """Конфигурация внешнего макро-источника из YAML."""
    enabled: bool = False
    source_path: str = ""
    mode: str = "override"  # override | supplement

    # Макро
    variable_map: Dict[str, str] = field(default_factory=dict)
    scenario_map: Dict[str, str] = field(default_factory=dict)

    # Отрасли
    company_sector_map: Dict[str, List[str]] = field(default_factory=dict)
    sector_drivers: Optional[List[str]] = None

    @classmethod
    def from_yaml(cls, cfg: dict) -> "ExternalConfig":
        """Parse macro_forecast.external section from project.yaml."""
        ext = cfg.get("macro_forecast", {}).get("external", {})
        if not ext or not ext.get("enabled", False):
            return cls(enabled=False)

        macro_cfg = ext.get("macro", {})
        sector_cfg = ext.get("sector", {})

        return cls(
            enabled=True,
            source_path=ext.get("source_path", ""),
            mode=ext.get("mode", "override"),
            variable_map=macro_cfg.get("variable_map", {}),
            scenario_map=macro_cfg.get("scenario_map", {}),
            company_sector_map=sector_cfg.get("company_sector_map", {}),
            sector_drivers=sector_cfg.get("drivers"),
        )


def load_all_external(
    config: ExternalConfig,
    company_id: str,
    scenario_name: str,
    forecast_start_year: int,
    forecast_years: int = 5,
) -> Tuple[Dict[str, Dict[int, float]], ExternalLoadResult]:
    """
    Единая точка входа: загружает макро + отраслевые драйверы.

    Returns:
        (all_forecasts, combined_result)
    """
    combined_result = ExternalLoadResult()

    if not config.enabled:
        return {}, combined_result

    source = Path(config.source_path)
    if not source.exists():
        combined_result.errors.append(f"Путь modelMacro не найден: {source}")
        return {}, combined_result

    all_forecasts: Dict[str, Dict[int, float]] = {}

    # 1. Макро-факторы
    macro_fc, macro_res = load_external_macro(
        source_path=source,
        scenario_name=scenario_name,
        forecast_start_year=forecast_start_year,
        forecast_years=forecast_years,
        variable_map=config.variable_map or None,
        scenario_map=config.scenario_map or None,
    )
    all_forecasts.update(macro_fc)
    combined_result.factors_loaded.extend(macro_res.factors_loaded)
    combined_result.methods_used.update(macro_res.methods_used)
    combined_result.scenarios_mapped.update(macro_res.scenarios_mapped)
    combined_result.warnings.extend(macro_res.warnings)
    combined_result.errors.extend(macro_res.errors)

    # 2. Отраслевые драйверы
    sector_tags = config.company_sector_map.get(company_id, [])
    if sector_tags:
        sector_fc, sector_res = load_external_sector(
            source_path=source,
            sector_tags=sector_tags,
            forecast_start_year=forecast_start_year,
            forecast_years=forecast_years,
            drivers=config.sector_drivers,
        )
        all_forecasts.update(sector_fc)
        combined_result.factors_loaded.extend(sector_res.factors_loaded)
        combined_result.methods_used.update(sector_res.methods_used)
        combined_result.warnings.extend(sector_res.warnings)
        combined_result.errors.extend(sector_res.errors)

    return all_forecasts, combined_result
